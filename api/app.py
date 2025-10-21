from flask import Flask, request
import telebot, os, sqlite3, json, time, random, re
from telebot import types
from dotenv import load_dotenv
from collections import defaultdict
import logging
from datetime import datetime, timedelta
from threading import Lock, Thread
import html

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    filename='bot.log',
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Global locks and caches
flood_locks = defaultdict(Lock)
user_messages = defaultdict(list)
MENU_CACHE = {}
bot.temp_data = {}  # For state management

# DATABASE SETUP (ALL TABLES WITH INDEXES)
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Core tables
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (chat_id TEXT, feature TEXT, subfeature TEXT, data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS responses 
                 (chat_id TEXT, type TEXT, key TEXT, response TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS schedules 
                 (chat_id TEXT, type TEXT, time TEXT, text TEXT, active INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blocks 
                 (chat_id TEXT, type TEXT, item TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS warns 
                 (chat_id TEXT, user_id TEXT, warns INTEGER, reason TEXT, timestamp TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (chat_id TEXT, action TEXT, user_id TEXT, reason TEXT, timestamp TEXT)''')
    
    # Additional features
    c.execute('''CREATE TABLE IF NOT EXISTS analytics 
                 (chat_id TEXT, user_id TEXT, action TEXT, timestamp TEXT, metadata TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS triggers 
                 (chat_id TEXT, keyword TEXT, response TEXT, regex INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS welcome 
                 (chat_id TEXT, welcome_msg TEXT, leave_msg TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS flood_settings 
                 (chat_id TEXT, flood_limit INTEGER, action TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS broadcasts 
                 (chat_id TEXT, message TEXT, sent INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS blacklists 
                 (chat_id TEXT, word TEXT, regex INTEGER)''')
    
    # Advanced features
    c.execute('''CREATE TABLE IF NOT EXISTS permissions 
                 (chat_id TEXT, user_id TEXT, role TEXT, commands TEXT, duration TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS custom_commands 
                 (chat_id TEXT, trigger TEXT, response TEXT, target TEXT, permissions TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS polls 
                 (chat_id TEXT, poll_id TEXT, question TEXT, options TEXT, anonymous INTEGER, timer INTEGER, results TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS notes 
                 (chat_id TEXT, tag TEXT, content TEXT, expire TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS rss_feeds 
                 (chat_id TEXT, url TEXT, keywords TEXT, interval TEXT, format TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions 
                 (chat_id TEXT, user_id TEXT, plan TEXT, duration TEXT, active INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS federations 
                 (chat_id TEXT, linked_group TEXT, sync_actions TEXT, share_logs INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS captchas 
                 (chat_id TEXT, type TEXT, difficulty TEXT, time_limit INTEGER, fail_action TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS message_dump 
                 (chat_id TEXT, deleted_msg TEXT, user_id TEXT, timestamp TEXT, dump_channel TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS plugins 
                 (chat_id TEXT, plugin_name TEXT, config TEXT, active INTEGER)''')
    
    # Indexes for performance
    for table in ['settings', 'responses', 'schedules', 'blocks', 'warns', 'logs', 'analytics', 'triggers', 'welcome', 'flood_settings', 
                  'broadcasts', 'blacklists', 'permissions', 'custom_commands', 'polls', 'notes', 'rss_feeds', 'subscriptions', 
                  'federations', 'captchas', 'message_dump', 'plugins']:
        c.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_chat ON {table}(chat_id)')
    
    conn.commit()
    conn.close()

init_db()

# UTILITY FUNCTIONS
def sanitize_input(text):
    """Sanitize input to prevent SQL injection and Telegram formatting issues."""
    if not text:
        raise ValueError("Input cannot be empty")
    text = html.escape(text.strip())  # Escape HTML characters
    if len(text) > 4096:  # Telegram message limit
        raise ValueError("Input too long (max 4096 characters)")
    return text

def validate_url(url):
    """Validate URL format."""
    url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
    return bool(url_pattern.match(url))

def validate_time_format(time_str):
    """Validate time format (e.g., 1d, 2h, 30m)."""
    time_pattern = re.compile(r'^\d+[smhd]$')
    return bool(time_pattern.match(time_str))

def validate_regex(regex_str):
    """Validate regex pattern."""
    try:
        re.compile(regex_str)
        return True
    except re.error:
        return False

def parse_time(text): 
    try:
        total = sum(int(v) * {'s':1,'m':60,'h':3600,'d':86400}[u] for v,u in re.findall(r'(\d+)([smhd])', text.lower()))
        return total if total > 0 else 300
    except: 
        return 300

def parse_number(text): 
    try: 
        return max(1, int(text))
    except: 
        return 3

def is_creator_or_admin(bot, chat_id, user_id):
    """Check if user is creator or has admin/mod role."""
    if str(chat_id).startswith('-'):
        try:
            status = bot.get_chat_member(chat_id, user_id).status
            if status == 'creator':
                return True
            conn = sqlite3.connect('bot.db')
            c = conn.cursor()
            c.execute("SELECT role FROM permissions WHERE chat_id=? AND user_id=?", (chat_id, str(user_id)))
            role = c.fetchone()
            conn.close()
            return role and role[0] in ['ADMIN', 'MOD']
        except:
            return False
    return True

def safe_db_operation(query, params, operation="execute"):
    """Safely execute database operations with error handling."""
    try:
        conn = sqlite3.connect('bot.db', timeout=10)
        c = conn.cursor()
        if operation == "execute":
            c.execute(query, params)
        elif operation == "fetch":
            c.execute(query, params)
            return c.fetchall()
        conn.commit()
        return True
    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def get_all_settings(chat_id):
    if chat_id in MENU_CACHE: 
        return MENU_CACHE[chat_id]
    settings = {}
    rows = safe_db_operation("SELECT feature, subfeature, data FROM settings WHERE chat_id=?", (chat_id,), "fetch")
    if rows:
        settings = {f"{r[0]}_{r[1]}": json.loads(r[2]) for r in rows}
    MENU_CACHE[chat_id] = settings
    return settings

def safe_json(data): 
    return json.loads(data) if data else {'status': 'off'}

def cleanup_temp_data():
    """Remove expired temp_data entries."""
    now = time.time()
    for key in list(bot.temp_data.keys()):
        if 'timeout' in bot.temp_data[key] and now > bot.temp_data[key]['timeout']:
            del bot.temp_data[key]

# Run cleanup periodically
Thread(target=lambda: [cleanup_temp_data() or time.sleep(60) for _ in iter(int, 1)], daemon=True).start()

# FLOOD PROTECTION
def check_flood(chat_id, user_id):
    """Check and handle flood control based on flood_settings."""
    rows = safe_db_operation("SELECT flood_limit, action FROM flood_settings WHERE chat_id=?", (chat_id,), "fetch")
    limit = rows[0][0] if rows else 5
    action = rows[0][1] if rows else 'delete'
    
    with flood_locks[(chat_id, user_id)]:
        now = time.time()
        msgs = [t for t in user_messages[(chat_id, user_id)] if now - t < 60]
        user_messages[(chat_id, user_id)] = msgs + [now]
        
        if len(msgs) >= limit:
            log_activity(chat_id, user_id, f"flood_{action}", {'limit': limit})
            return action
    return False

# ANALYTICS
def log_activity(chat_id, user_id, action, metadata=None):
    safe_db_operation("INSERT INTO analytics VALUES (?, ?, ?, ?, ?)", 
                     (chat_id, str(user_id), action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), json.dumps(metadata or {})))

def get_analytics(chat_id, period='week'):
    delta = 7 if period == 'week' else 30
    ago = (datetime.now() - timedelta(days=delta)).strftime("%Y-%m-%d")
    rows = safe_db_operation("SELECT COUNT(*), COUNT(DISTINCT user_id) FROM analytics WHERE chat_id=? AND timestamp > ?", 
                            (chat_id, ago), "fetch")
    total, users = rows[0] if rows else (0, 0)
    return f"📊 {total} actions, {users} users ({period})"

# TRIGGERS
def check_triggers(chat_id, text):
    if (chat_id, 'triggers') in MENU_CACHE: 
        triggers = MENU_CACHE[(chat_id, 'triggers')]
    else:
        triggers = safe_db_operation("SELECT keyword, response, regex FROM triggers WHERE chat_id=?", (chat_id,), "fetch")
        MENU_CACHE[(chat_id, 'triggers')] = triggers
    for kw, resp, regex in triggers:
        if regex and re.search(kw, text, re.IGNORECASE) or kw.lower() in text.lower():
            return resp
    return None

# WELCOME
def get_welcome(chat_id, is_welcome=True):
    row = safe_db_operation("SELECT welcome_msg, leave_msg FROM welcome WHERE chat_id=?", (chat_id,), "fetch")
    default = "Welcome!" if is_welcome else "Goodbye!"
    return row[0][0] if is_welcome and row and row[0][0] else row[0][1] if row and row[0][1] else default

# BLACKLIST
def check_blacklist(chat_id, text):
    if (chat_id, 'blacklists') in MENU_CACHE: 
        bl = MENU_CACHE[(chat_id, 'blacklists')]
    else:
        bl = safe_db_operation("SELECT word, regex FROM blacklists WHERE chat_id=?", (chat_id,), "fetch")
        MENU_CACHE[(chat_id, 'blacklists')] = bl
    for word, regex in bl:
        if regex and re.search(word, text, re.IGNORECASE) or word.lower() in text.lower():
            return True
    return False

# CAPTCHA
def generate_captcha():
    """Generate a simple math captcha."""
    a, b = random.randint(1, 10), random.randint(1, 10)
    answer = a + b
    question = f"What is {a} + {b}?"
    options = [str(answer), str(answer + random.randint(1, 5)), str(answer - random.randint(1, 5)), str(random.randint(1, 20))]
    random.shuffle(options)
    return {'question': question, 'answer': str(answer), 'options': options}

# START COMMAND
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = str(message.chat.id)
    user = message.from_user
    log_activity(chat_id, user.id, 'start')
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔧 Settings", callback_data='main'),
        types.InlineKeyboardButton("📋 Commands", callback_data='show_commands')
    )
    
    if message.chat.type == 'private':
        markup.add(
            types.InlineKeyboardButton("➕ Add to Group", url=f"t.me/{bot.get_me().username}?startgroup=true"),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='help')
        )
        text = f"👋 {user.first_name}, Ultimate Advanced Bot!"
        sent_message = bot.reply_to(message, text, reply_markup=markup)
    else:
        markup.add(
            types.InlineKeyboardButton("📊 Analytics", callback_data='analytics_menu'),
            types.InlineKeyboardButton("🎯 Triggers", callback_data='triggers_menu'),
            types.InlineKeyboardButton("👋 Welcome", callback_data='welcome_menu'),
            types.InlineKeyboardButton("🛡️ Anti-Flood", callback_data='flood_menu'),
            types.InlineKeyboardButton("📢 Broadcast", callback_data='broadcast_menu'),
            types.InlineKeyboardButton("🚫 Blacklists", callback_data='blacklist_menu')
        )
        text = "🤖 Advanced Group Bot Active!"
        sent_message = bot.send_message(chat_id, text, reply_markup=markup)
    
    # Auto-delete after 2s
    time.sleep(2)
    try:
        bot.delete_message(chat_id, sent_message.message_id)
    except:
        pass

# STATUS COMMAND
@bot.message_handler(commands=['status'])
def status_command(message):
    chat_id = str(message.chat.id)
    if message.chat.type == 'private' or not is_creator_or_admin(bot, chat_id, message.from_user.id):
        return bot.reply_to(message, "Group creator or admin only!")
    
    settings = get_all_settings(chat_id)
    status_text = "🔧 ADVANCED SETTINGS:\n"
    
    checks = {
        'moderation_antinsfw': '🔍 Anti-NSFW',
        'moderation_captcha': '🛡️ CAPTCHA', 
        'moderation_lock_links': '🔗 Links',
        'moderation_lock_media': '📸 Media',
        'moderation_lock_stickers': '😀 Stickers',
        'moderation_lock_forwards': '📤 Forwards',
        'analytics': '📊 Analytics',
        'flood_settings': '🛡️ Anti-Flood',
        'blacklists': '🚫 Filters'
    }
    
    for key, name in checks.items():
        status = safe_json(settings.get(key, '{}'))['status']
        status_text += f"{name}: {'✅' if status == 'on' else '❌'}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔧 Full Menu", callback_data='group_menu'),
        types.InlineKeyboardButton("📋 Commands", callback_data='show_commands')
    )
    bot.reply_to(message, status_text, reply_markup=markup)

# CONTENT HANDLER
@bot.message_handler(content_types=['text'])
def content_handler(message):
    chat_id = str(message.chat.id)
    text = sanitize_input(message.text)
    user_id = str(message.from_user.id)
    log_activity(chat_id, user_id, 'message', {'text': text})
    
    # Save message to dump if enabled
    settings = get_all_settings(chat_id)
    if safe_json(settings.get('message_dump', '{}'))['status'] == 'on':
        rows = safe_db_operation("SELECT dump_channel FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
        if rows:
            safe_db_operation("INSERT INTO message_dump VALUES (?, ?, ?, ?, ?)", 
                            (chat_id, text, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rows[0][0]))
    
    # ANTI-FLOOD
    flood_action = check_flood(chat_id, user_id)
    if flood_action:
        bot.delete_message(chat_id, message.message_id)
        if flood_action == 'mute':
            bot.restrict_chat_member(chat_id, user_id, permissions={'can_send_messages': False})
            bot.reply_to(message, "🛑 You are muted for flooding!")
        elif flood_action == 'ban':
            bot.kick_chat_member(chat_id, user_id)
            bot.reply_to(message, "🛑 You are banned for flooding!")
        else:
            bot.reply_to(message, "🛑 Slow down! Message deleted.")
        return
    
    # BLACKLIST
    if check_blacklist(chat_id, text):
        bot.delete_message(chat_id, message.message_id)
        log_activity(chat_id, user_id, 'blacklist_hit')
        return bot.reply_to(message, "🚫 Blocked!")
    
    # TRIGGERS
    trigger = check_triggers(chat_id, text)
    if trigger:
        return bot.reply_to(message, trigger)
    
    # ORIGINAL LOCKS
    if message.entities and any(e.type == 'url' for e in message.entities) and safe_json(settings.get('moderation_lock_links', '{}'))['status'] == 'on':
        bot.delete_message(chat_id, message.message_id)
        return bot.reply_to(message, "🔗 Links locked!")
    
    # HANDLE TEMP DATA INPUTS
    if chat_id in bot.temp_data:
        action = bot.temp_data[chat_id].get('action')
        if action:
            handlers = {
                'grant_role': handle_grant_input,
                'triggers_add': handle_triggers_add,
                'triggers_edit': handle_triggers_edit_delete,
                'triggers_delete': handle_triggers_edit_delete,
                'welcome_set': handle_welcome_set,
                'flood_set_limit': handle_flood_set_limit,
                'flood_enable': handle_flood_enable,
                'broadcast_send': handle_broadcast_send,
                'broadcast_groups': handle_broadcast_groups,
                'blacklist_add': handle_blacklist_add,
                'customcmd_create': handle_customcmd_create,
                'customcmd_edit': handle_customcmd_edit,
                'poll_new': handle_poll_new,
                'note_save': handle_note_save,
                'rss_add': handle_rss_add,
                'sub_grant': handle_sub_grant,
                'fed_link': handle_fed_link,
                'captcha_set': handle_captcha_set,
                'dump_set': handle_dump_set,
                'plugin_install': handle_plugin_install
            }
            if action in handlers:
                handlers[action](message)
                return

# HANDLERS
def handle_triggers_edit_delete(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    action = bot.temp_data[chat_id]['action']
    keyword = sanitize_input(message.text)
    
    if action == 'triggers_edit' and 'sub_action' not in bot.temp_data[chat_id]:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['keyword'] = keyword
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        bot.reply_to(message, f"✏️ Send new response for trigger '{keyword}':")
        return
    
    if action == 'triggers_edit' and bot.temp_data[chat_id].get('sub_action') == 'edit_response':
        new_response = sanitize_input(message.text)
        keyword = bot.temp_data[chat_id]['keyword']
        if len(new_response) > 1000:
            return bot.reply_to(message, "❌ Response too long!")
        if safe_db_operation("UPDATE triggers SET response=? WHERE chat_id=? AND keyword=?", 
                           (new_response, chat_id, keyword)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, f"✅ Trigger '{keyword}' updated!")
        else:
            bot.reply_to(message, "❌ Error updating trigger!")
    
    elif action == 'triggers_delete':
        if safe_db_operation("DELETE FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, keyword)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Trigger deleted!")
        else:
            bot.reply_to(message, "❌ Trigger not found!")

def handle_flood_enable(message):
    chat_id = str(message.chat.id)
    status = 'on' if message.text.lower() == 'on' else 'off'
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, 'flood', 'status', ?)", 
                       (chat_id, json.dumps({'status': status}))):
        bot.reply_to(message, f"✅ Flood {'enabled' if status == 'on' else 'disabled'}!")
    else:
        bot.reply_to(message, "❌ Error updating flood settings!")

def handle_broadcast_groups(message):
    chat_id = str(message.chat.id)
    bot.reply_to(message, "👥 All groups selected!")  # Placeholder

def handle_customcmd_edit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    if 'sub_action' in bot.temp_data[chat_id]:
        trigger = bot.temp_data[chat_id]['trigger']
        new_response = sanitize_input(message.text)
        if len(new_response) > 1000:
            return bot.reply_to(message, "❌ Response too long!")
        if safe_db_operation("UPDATE custom_commands SET response=? WHERE chat_id=? AND trigger=?", 
                           (new_response, chat_id, trigger)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, f"✅ Command /{trigger} updated!")
        else:
            bot.reply_to(message, "❌ Error updating command!")
    else:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['trigger'] = sanitize_input(message.text.strip('/ '))
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        bot.reply_to(message, f"✏️ Send new response for /{message.text}:")

# NEW MEMBER
@bot.message_handler(content_types=['new_chat_members'])
def new_member_welcome(message):
    chat_id = str(message.chat.id)
    for user in message.new_chat_members:
        welcome = get_welcome(chat_id)
        bot.send_message(chat_id, f"{welcome} @{user.username or user.first_name}!")
        log_activity(chat_id, user.id, 'join')
        
        # CAPTCHA
        settings = get_all_settings(chat_id)
        if safe_json(settings.get('moderation_captcha', '{}'))['status'] == 'on':
            captcha = generate_captcha()
            bot.temp_data[f"{chat_id}_{user.id}"] = {'action': 'captcha_verify', 'answer': captcha['answer'], 'timeout': time.time() + 300}
            markup = types.InlineKeyboardMarkup(row_width=2)
            for i in range(0, len(captcha['options']), 2):
                markup.add(
                    types.InlineKeyboardButton(captcha['options'][i], callback_data=f"captcha_{captcha['options'][i]}_{user.id}"),
                    types.InlineKeyboardButton(captcha['options'][i+1], callback_data=f"captcha_{captcha['options'][i+1]}_{user.id}") if i+1 < len(captcha['options']) else types.InlineKeyboardButton(" ", callback_data="noop")
                )
            bot.send_message(chat_id, f"🛡️ @{user.username or user.first_name}, solve: {captcha['question']} (5 min)", reply_markup=markup)

# CAPTCHA VERIFICATION
@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_verify(call):
    chat_id = str(call.message.chat.id)
    _, answer, user_id = call.data.split('_')
    key = f"{chat_id}_{user_id}"
    if key not in bot.temp_data:
        bot.answer_callback_query(call.id, "❌ Captcha expired!")
        return
    data = bot.temp_data[key]
    if time.time() > data['timeout']:
        bot.answer_callback_query(call.id, "❌ Captcha timed out!")
        bot.kick_chat_member(chat_id, user_id)
        del bot.temp_data[key]
        return
    if answer == data['answer']:
        bot.answer_callback_query(call.id, "✅ Verified!")
        bot.delete_message(chat_id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "❌ Wrong answer!")
        bot.kick_chat_member(chat_id, user_id)
    del bot.temp_data[key]

# LEFT MEMBER
@bot.message_handler(content_types=['left_chat_member'])
def left_member(message):
    chat_id = str(message.chat.id)
    user = message.left_chat_member
    leave = get_welcome(chat_id, False)
    bot.send_message(chat_id, f"{leave} @{user.username or user.first_name}")
    log_activity(chat_id, user.id, 'leave')

# SETTINGS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'main')
def settings_menu(call):
    bot.answer_callback_query(call.id, "⚙️ Loading...", show_alert=False)
    chat_id = str(call.message.chat.id)
    
    text = "🔧 MAIN MENU\n\n" \
           "🛡️ Verify: User verification settings\n" \
           "👋 Welcome: Greetings for new members\n" \
           "📬 Triggers: Auto-responses to keywords\n" \
           "⏰ Schedule: Timed messages\n" \
           "🔒 Moderation: Locks and penalties\n" \
           "🧹 Clean: Auto-delete rules\n" \
           "🚫 Block: Block lists\n" \
           "🌐 Lang: Language settings\n" \
           "⚙️ Advanced: Extra tools"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("🛡️ Verify", 'verify'), ("👋 Welcome", 'welcome_menu'),
        ("📬 Triggers", 'triggers_menu'), ("⏰ Schedule", 'scheduled'),
        ("🔒 Moderation", 'group_menu'), ("🧹 Clean", 'autoclean'),
        ("🚫 Block", 'block'), ("🌐 Lang", 'lang'),
        ("⚙️ Advanced", 'advanced_menu'), ("📋 Commands", 'show_commands')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

# GROUP MENU
@bot.callback_query_handler(func=lambda call: call.data == 'group_menu')
def group_menu(call):
    if not is_creator_or_admin(bot, str(call.message.chat.id), call.from_user.id):
        return bot.edit_message_text("Creator or admin only!", call.message.chat.id, call.message.message_id)
    
    chat_id = str(call.message.chat.id)
    
    text = "🏛️ GROUP MANAGEMENT\n\n" \
           "🔒 Locks: Restrict content types\n" \
           "🛡️ CAPTCHA: Verify new users\n" \
           "📊 Analytics: Group stats\n" \
           "🎯 Triggers: Keyword responses\n" \
           "👋 Welcome: Join/leave messages\n" \
           "🛡️ Flood: Anti-spam limits\n" \
           "📢 Broadcast: Mass messages\n" \
           "🚫 Blacklists: Word filters\n" \
           "👑 Permissions: User roles\n" \
           "⚙️ Commands: Custom cmds\n" \
           "📊 Polls: Advanced voting\n" \
           "📝 Notes: Tagged notes\n" \
           "📰 RSS: Feed updates\n" \
           "💰 Subs: User plans\n" \
           "🔗 Federation: Linked groups\n" \
           "🎲 Captcha: Verification types\n" \
           "💾 Dump: Deleted msg logs\n" \
           "🔌 Plugins: Extra modules"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("🔒 Locks", 'moderation_lock'), ("🛡️ CAPTCHA", 'moderation_captcha'),
        ("📊 Analytics", 'analytics_menu'), ("🎯 Triggers", 'triggers_menu'),
        ("👋 Welcome", 'welcome_menu'), ("🛡️ Flood", 'flood_menu'),
        ("📢 Broadcast", 'broadcast_menu'), ("🚫 Blacklists", 'blacklist_menu'),
        ("👑 Permissions", 'permissions_menu'), ("⚙️ Commands", 'customcmd_menu'),
        ("📊 Polls", 'polls_menu'), ("📝 Notes", 'notes_menu'),
        ("📰 RSS", 'rss_menu'), ("💰 Subs", 'subs_menu'),
        ("🔗 Federation", 'fed_menu'), ("🎲 Captcha", 'captcha_menu'),
        ("💾 Dump", 'dump_menu'), ("🔌 Plugins", 'plugins_menu')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

# ANALYTICS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'analytics_menu')
def analytics_menu(call):
    bot.answer_callback_query(call.id, "📊 Loading...")
    chat_id = str(call.message.chat.id)
    stats = get_analytics(chat_id)
    
    text = f"📊 ANALYTICS MENU\n\n{stats}\n\n" \
           "📈 Weekly: Last 7 days stats\n" \
           "📉 Monthly: Last 30 days stats\n" \
           "📤 Report: Export data"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Weekly", callback_data='analytics_week'),
        types.InlineKeyboardButton("📉 Monthly", callback_data='analytics_month'),
        types.InlineKeyboardButton("📤 Report", callback_data='analytics_report'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('analytics_'))
def analytics_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'week':
        stats = get_analytics(chat_id, 'week')
    elif action == 'month':
        stats = get_analytics(chat_id, 'month')
    elif action == 'report':
        stats = "📤 Report sent to logs (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Weekly", callback_data='analytics_week'),
        types.InlineKeyboardButton("📉 Monthly", callback_data='analytics_month'),
        types.InlineKeyboardButton("📤 Report", callback_data='analytics_report'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='analytics_menu')
    )
    bot.edit_message_text(stats, chat_id, call.message.message_id, reply_markup=markup)

# TRIGGERS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'triggers_menu')
def triggers_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🎯 TRIGGERS MENU\n\n" \
           "➕ Add: Create new trigger\n" \
           "📝 List: View all triggers\n" \
           "✏️ Edit: Modify existing\n" \
           "🗑️ Delete: Remove trigger"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add", callback_data='triggers_add'),
        types.InlineKeyboardButton("📝 List", callback_data='triggers_list'),
        types.InlineKeyboardButton("✏️ Edit", callback_data='triggers_edit'),
        types.InlineKeyboardButton("🗑️ Delete", callback_data='triggers_delete')
    )
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('triggers_'))
def triggers_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'add':
        text = "➕ Add Trigger Type:\n\n" \
               "📝 Keyword: Simple word match\n" \
               "⚡ Regex: Advanced pattern"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📝 Keyword", callback_data='triggers_add_keyword'),
            types.InlineKeyboardButton("⚡ Regex", callback_data='triggers_add_regex'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu'),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action in ['add_keyword', 'add_regex']:
        bot.temp_data[chat_id] = {'action': 'triggers_add', 'regex': 1 if 'regex' in action else 0, 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='triggers_menu'),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
        )
        bot.edit_message_text("Send: keyword|response\nE.g., hello|Hi there!", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        triggers = safe_db_operation("SELECT keyword, response FROM triggers WHERE chat_id=?", (chat_id,), "fetch")
        text = "📝 TRIGGERS LIST:\n" + "\n".join(f"• {kw}: {resp}" for kw, resp in triggers) or "No triggers."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Add", callback_data='triggers_add'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'edit' or action == 'delete':
        bot.temp_data[chat_id] = {'action': f'triggers_{action}', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='triggers_menu'),
            types.InlineKeyboardButton("📝 List", callback_data='triggers_list')
        )
        bot.edit_message_text(f"Send keyword to {action}:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'help':
        text = "🎯 Triggers Help:\n\n- Add: Create keyword or regex triggers\n- Edit/Delete: Modify or remove\n- Format: keyword|response"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu'),
            types.InlineKeyboardButton("➕ Add", callback_data='triggers_add')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_triggers_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    data = bot.temp_data[chat_id]
    try:
        kw, resp = message.text.split('|', 1)
        kw = sanitize_input(kw.strip())
        resp = sanitize_input(resp.strip())
        if data['regex'] and not validate_regex(kw):
            return bot.reply_to(message, "❌ Invalid regex pattern!")
        if len(kw) > 100 or len(resp) > 1000:
            return bot.reply_to(message, "❌ Keyword or response too long!")
        if safe_db_operation("SELECT 1 FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, kw), "fetch"):
            return bot.reply_to(message, "❌ Trigger already exists!")
        if safe_db_operation("INSERT INTO triggers VALUES (?, ?, ?, ?)", (chat_id, kw, resp, data['regex'])):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Trigger added!")
        else:
            bot.reply_to(message, "❌ Error adding trigger!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# WELCOME MENU
@bot.callback_query_handler(func=lambda call: call.data == 'welcome_menu')
def welcome_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "👋 WELCOME MESSAGES\n\n" \
           "👋 Set Welcome: Greeting for joins\n" \
           "👋 Preview: See current\n" \
           "🚪 Set Leave: Farewell for leaves"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👋 Set Welcome", callback_data='welcome_set'),
        types.InlineKeyboardButton("👋 Preview", callback_data='welcome_preview'),
        types.InlineKeyboardButton("🚪 Set Leave", callback_data='leave_set'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['welcome_set', 'leave_set'])
def welcome_action(call):
    action = call.data
    chat_id = str(call.message.chat.id)
    bot.temp_data[chat_id] = {'action': action, 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Cancel", callback_data='welcome_menu'),
        types.InlineKeyboardButton("👋 Preview", callback_data='welcome_preview')
    )
    bot.edit_message_text(f"Send new {'welcome' if 'welcome' in action else 'leave'} message:", chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'welcome_preview')
def welcome_preview(call):
    chat_id = str(call.message.chat.id)
    welcome, leave = get_welcome(chat_id), get_welcome(chat_id, False)
    text = f"👋 Welcome: {welcome}\n🚪 Leave: {leave}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👋 Set Welcome", callback_data='welcome_set'),
        types.InlineKeyboardButton("🚪 Set Leave", callback_data='leave_set')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_welcome_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    action = bot.temp_data[chat_id]['action']
    msg = sanitize_input(message.text)
    if len(msg) < 1:
        return bot.reply_to(message, "❌ Message cannot be empty!")
    if safe_db_operation("INSERT OR REPLACE INTO welcome VALUES (?, ?, ?)", 
                       (chat_id, msg if 'welcome' in action else None, msg if 'leave' in action else None)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, "✅ Message set!")
    else:
        bot.reply_to(message, "❌ Error setting message!")

# ANTI-FLOOD MENU
@bot.callback_query_handler(func=lambda call: call.data == 'flood_menu')
def flood_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🛡️ ANTI-FLOOD MENU\n\n" \
           "🛡️ Enable: Turn on/off\n" \
           "⚙️ Set Limit: Msgs per min\n" \
           "📊 Stats: Flood incidents"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛡️ Enable", callback_data='flood_enable'),
        types.InlineKeyboardButton("⚙️ Set Limit", callback_data='flood_limit'),
        types.InlineKeyboardButton("📊 Stats", callback_data='flood_stats'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('flood_'))
def flood_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'enable':
        bot.temp_data[chat_id] = {'action': 'flood_enable', 'timeout': time.time() + 300}
        text = "🛡️ Send 'on' or 'off' to enable/disable flood protection:"
    elif action == 'limit':
        bot.temp_data[chat_id] = {'action': 'flood_set_limit', 'timeout': time.time() + 300}
        text = "⚙️ Send new limit (e.g., 5):"
    elif action == 'stats':
        text = "📊 Flood stats: 0 incidents (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='flood_menu'),
        types.InlineKeyboardButton("📊 Stats", callback_data='flood_stats')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_flood_set_limit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        limit = parse_number(message.text)
        if limit < 1 or limit > 50:
            return bot.reply_to(message, "❌ Limit must be between 1 and 50!")
        if safe_db_operation("INSERT OR REPLACE INTO flood_settings VALUES (?, ?, ?)", (chat_id, limit, 'delete')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, f"✅ Limit set to {limit}!")
        else:
            bot.reply_to(message, "❌ Error setting limit!")
    except ValueError:
        bot.reply_to(message, "❌ Invalid number!")

# BROADCAST MENU
@bot.callback_query_handler(func=lambda call: call.data == 'broadcast_menu')
def broadcast_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "📢 BROADCAST MENU\n\n" \
           "📢 Send Now: Immediate msg\n" \
           "👥 Select Groups: Target groups\n" \
           "📋 Preview: See msg"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 Send Now", callback_data='broadcast_send'),
        types.InlineKeyboardButton("👥 Select Groups", callback_data='broadcast_groups'),
        types.InlineKeyboardButton("📋 Preview", callback_data='broadcast_preview'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_'))
def broadcast_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'send':
        bot.temp_data[chat_id] = {'action': 'broadcast_send', 'timeout': time.time() + 300}
        text = "📢 Send message to broadcast:"
    elif action == 'groups':
        bot.temp_data[chat_id] = {'action': 'broadcast_groups', 'timeout': time.time() + 300}
        text = "👥 Send group IDs (comma-separated):"
    elif action == 'preview':
        text = "📋 Preview: Sample msg (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='broadcast_menu'),
        types.InlineKeyboardButton("📢 Send Now", callback_data='broadcast_send')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_broadcast_send(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    msg = sanitize_input(message.text)
    if safe_db_operation("INSERT INTO broadcasts VALUES (?, ?, ?)", (chat_id, msg, 1)):
        bot.send_message(chat_id, f"Broadcast: {msg}")
        del bot.temp_data[chat_id]
        bot.reply_to(message, "✅ Broadcast sent!")
    else:
        bot.reply_to(message, "❌ Error sending broadcast!")

# BLACKLIST MENU
@bot.callback_query_handler(func=lambda call: call.data == 'blacklist_menu')
def blacklist_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🚫 BLACKLISTS MENU\n\n" \
           "➕ Add Word: Simple word filter\n" \
           "⚡ Add Regex: Pattern filter\n" \
           "📝 List: View filters\n" \
           "🗑️ Remove: Delete filter"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Word", callback_data='blacklist_add_word'),
        types.InlineKeyboardButton("⚡ Add Regex", callback_data='blacklist_add_regex'),
        types.InlineKeyboardButton("📝 List", callback_data='blacklist_list'),
        types.InlineKeyboardButton("🗑️ Remove", callback_data='blacklist_remove')
    )
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='blacklist_help')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('blacklist_'))
def blacklist_action(call):
    action = call.data.split('_')[1:]
    chat_id = str(call.message.chat.id)
    
    if action[0] == 'add' and action[1] in ['word', 'regex']:
        bot.temp_data[chat_id] = {'action': 'blacklist_add', 'regex': 1 if 'regex' in action else 0, 'timeout': time.time() + 300}
        text = "➕ Send word/regex to add:"
    elif action[0] == 'list':
        words = safe_db_operation("SELECT word FROM blacklists WHERE chat_id=?", (chat_id,), "fetch")
        text = "📝 BLACKLIST:\n" + "\n".join(f"• {w[0]}" for w in words) or "No blacklists."
    elif action[0] == 'remove':
        bot.temp_data[chat_id] = {'action': 'blacklist_remove', 'timeout': time.time() + 300}
        text = "🗑️ Send word to remove:"
    elif action[0] == 'help':
        text = "🚫 Blacklist Help:\n\n- Add: Block specific words or regex\n- Remove: Unblock words\n- Case-insensitive"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='blacklist_menu'),
        types.InlineKeyboardButton("📝 List", callback_data='blacklist_list')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_blacklist_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    data = bot.temp_data[chat_id]
    word = sanitize_input(message.text)
    try:
        if data['regex'] and not validate_regex(word):
            return bot.reply_to(message, "❌ Invalid regex pattern!")
        if len(word) > 100:
            return bot.reply_to(message, "❌ Word too long!")
        if safe_db_operation("SELECT 1 FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word), "fetch"):
            return bot.reply_to(message, "❌ Word already blacklisted!")
        if safe_db_operation("INSERT INTO blacklists VALUES (?, ?, ?)", (chat_id, word, data['regex'])):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Blacklist added!")
        else:
            bot.reply_to(message, "❌ Error adding blacklist!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# ADVANCED MENU
@bot.callback_query_handler(func=lambda call: call.data == 'advanced_menu')
def advanced_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "⚙️ ADVANCED TOOLS\n\n" \
           "👑 Permissions: Role management\n" \
           "⚙️ Custom Cmds: User-defined commands\n" \
           "📊 Polls: Voting systems\n" \
           "📝 Notes: Tagged reminders\n" \
           "📰 RSS: Feed subscriptions\n" \
           "💰 Subscriptions: User plans\n" \
           "🔗 Federation: Group linking\n" \
           "🎲 Captcha Types: Verification options\n" \
           "💾 Message Dump: Deleted logs\n" \
           "🔌 Plugins: Extra features"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("👑 Permissions", 'permissions_menu'), ("⚙️ Custom Cmds", 'customcmd_menu'),
        ("📊 Polls", 'polls_menu'), ("📝 Notes", 'notes_menu'),
        ("📰 RSS", 'rss_menu'), ("💰 Subscriptions", 'subs_menu'),
        ("🔗 Federation", 'fed_menu'), ("🎲 Captcha Types", 'captcha_menu'),
        ("💾 Message Dump", 'dump_menu'), ("🔌 Plugins", 'plugins_menu')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

# PERMISSIONS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'permissions_menu')
def permissions_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "👑 PERMISSIONS MENU\n\n" \
           "👑 Grant Role: Assign mod/admin\n" \
           "📋 List Roles: View assigned\n" \
           "⚙️ Set Commands: Role permissions\n" \
           "⏰ Set Duration: Time-limited roles"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👑 Grant Role", callback_data='perm_grant'),
        types.InlineKeyboardButton("📋 List Roles", callback_data='perm_list'),
        types.InlineKeyboardButton("⚙️ Set Commands", callback_data='perm_commands'),
        types.InlineKeyboardButton("⏰ Set Duration", callback_data='perm_duration')
    )
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='perm_help')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('perm_'))
def permissions_action(call):
    action = call.data.split('_')[1:]
    chat_id = str(call.message.chat.id)
    
    if action[0] == 'grant':
        text = "👑 Select Role:\n\n" \
               "Mod: Basic moderation\n" \
               "Admin: Full control"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("Mod", callback_data='perm_grant_mod'),
            types.InlineKeyboardButton("Admin", callback_data='perm_grant_admin'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu'),
            types.InlineKeyboardButton("📋 List Roles", callback_data='perm_list')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action[0] == 'grant' and action[1] in ['mod', 'admin']:
        role = action[1].upper()
        bot.temp_data[chat_id] = {'action': 'grant_role', 'role': role, 'timeout': time.time() + 300}
        
        text = f"👑 Grant {role} Role\n\n" \
               "Send User ID or @username.\n" \
               "Or reply to their message."
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='perm_grant'),
            types.InlineKeyboardButton("📋 List Roles", callback_data='perm_list')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action[0] == 'list':
        rows = safe_db_operation("SELECT user_id, role, duration FROM permissions WHERE chat_id=?", (chat_id,), "fetch")
        text = "📋 ROLES:\n" + "\n".join(f"• ID {uid}: {role} ({dur})" for uid, role, dur in rows) or "No roles."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("👑 Grant Role", callback_data='perm_grant'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action[0] == 'commands' or action[0] == 'duration':
        bot.temp_data[chat_id] = {'action': f'perm_{action[0]}', 'timeout': time.time() + 300}
        text = f"Send {'commands (comma sep)' if action[0] == 'commands' else 'duration (e.g., 1d)'} for role:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu'),
            types.InlineKeyboardButton("📋 List Roles", callback_data='perm_list')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action[0] == 'help':
        text = "👑 Permissions Help:\n\n- Grant: Assign mod/admin roles\n- Commands: Set allowed commands\n- Duration: Time-limited roles"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu'),
            types.InlineKeyboardButton("👑 Grant Role", callback_data='perm_grant')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_grant_input(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    data = bot.temp_data[chat_id]
    role = data['role']
    
    if message.reply_to_message:
        user_id = str(message.reply_to_message.from_user.id)
        user_name = message.reply_to_message.from_user.first_name
    else:
        user_id = sanitize_input(message.text.replace('@', ''))
        user_name = "User"
    
    if safe_db_operation('INSERT OR REPLACE INTO permissions VALUES (?, ?, ?, ?, ?)', 
                       (chat_id, user_id, role, 'all', 'permanent')):
        del bot.temp_data[chat_id]
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📋 List Roles", callback_data='perm_list'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu')
        )
        bot.reply_to(message, f"✅ {role} granted to {user_name} (ID: {user_id})!", reply_markup=markup)
    else:
        bot.reply_to(message, "❌ Error granting role!")

# CUSTOM COMMANDS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'customcmd_menu')
def customcmd_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "⚙️ CUSTOM COMMANDS MENU\n\n" \
           "➕ Create: New command\n" \
           "📝 List: View commands\n" \
           "✏️ Edit: Modify command"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Create", callback_data='cmd_create'),
        types.InlineKeyboardButton("📝 List", callback_data='cmd_list'),
        types.InlineKeyboardButton("✏️ Edit", callback_data='cmd_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cmd_'))
def customcmd_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'create':
        bot.temp_data[chat_id] = {'action': 'customcmd_create', 'timeout': time.time() + 300}
        text = "➕ Send: /trigger|response"
    elif action == 'list':
        cmds = safe_db_operation("SELECT trigger, response FROM custom_commands WHERE chat_id=?", (chat_id,), "fetch")
        text = "📝 COMMANDS:\n" + "\n".join(f"• /{t}: {r}" for t, r in cmds) or "No commands."
    elif action == 'edit':
        bot.temp_data[chat_id] = {'action': 'customcmd_edit', 'timeout': time.time() + 300}
        text = "✏️ Send trigger to edit:"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='customcmd_menu'),
        types.InlineKeyboardButton("➕ Create", callback_data='cmd_create')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_customcmd_create(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        trig, resp = message.text.split('|', 1)
        trig = sanitize_input(trig.strip('/ '))
        resp = sanitize_input(resp.strip())
        if len(trig) > 50 or len(resp) > 1000:
            return bot.reply_to(message, "❌ Trigger or response too long!")
        if safe_db_operation("SELECT 1 FROM custom_commands WHERE chat_id=? AND trigger=?", (chat_id, trig), "fetch"):
            return bot.reply_to(message, "❌ Command already exists!")
        if safe_db_operation("INSERT INTO custom_commands VALUES (?, ?, ?, ?, ?)", (chat_id, trig, resp, 'all', 'all')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Custom command added!")
        else:
            bot.reply_to(message, "❌ Error adding command!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# POLLS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'polls_menu')
def polls_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "📊 POLLS MENU\n\n" \
           "📊 New Poll: Create poll\n" \
           "⚙️ Settings: Poll options\n" \
           "📋 Active: View polls"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 New Poll", callback_data='poll_new'),
        types.InlineKeyboardButton("⚙️ Settings", callback_data='poll_settings'),
        types.InlineKeyboardButton("📋 Active", callback_data='poll_active'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('poll_'))
def polls_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'new':
        bot.temp_data[chat_id] = {'action': 'poll_new', 'timeout': time.time() + 300}
        text = "📊 Send: question|option1,option2|anonymous(0/1)|timer(min)"
    elif action == 'settings':
        text = "⚙️ Poll settings updated (placeholder)."
    elif action == 'active':
        text = "📋 Active polls: None (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='polls_menu'),
        types.InlineKeyboardButton("📊 New Poll", callback_data='poll_new')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_poll_new(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        q, opts, anon, timer = message.text.split('|')
        q = sanitize_input(q.strip())
        opts = sanitize_input(opts.strip())
        anon = int(anon)
        timer = int(timer)
        if anon not in [0, 1] or timer < 1:
            return bot.reply_to(message, "❌ Invalid anonymous or timer value!")
        poll_id = str(random.randint(1000, 9999))
        if safe_db_operation("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (chat_id, poll_id, q, opts, anon, timer, '{}')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, f"✅ Poll {poll_id} created!")
        else:
            bot.reply_to(message, "❌ Error creating poll!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# NOTES MENU
@bot.callback_query_handler(func=lambda call: call.data == 'notes_menu')
def notes_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "📝 NOTES MENU\n\n" \
           "➕ Save Note: Add tagged note\n" \
           "🔍 Search: Find notes\n" \
           "📤 Share: Send note"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Save Note", callback_data='note_save'),
        types.InlineKeyboardButton("🔍 Search", callback_data='note_search'),
        types.InlineKeyboardButton("📤 Share", callback_data='note_share'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('note_'))
def notes_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'save':
        bot.temp_data[chat_id] = {'action': 'note_save', 'timeout': time.time() + 300}
        text = "➕ Send: #tag|content|expire(1d)"
    elif action == 'search':
        bot.temp_data[chat_id] = {'action': 'note_search', 'timeout': time.time() + 300}
        text = "🔍 Send tag to search:"
    elif action == 'share':
        text = "📤 Note shared (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='notes_menu'),
        types.InlineKeyboardButton("➕ Save Note", callback_data='note_save')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_note_save(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        tag, content, expire = message.text.split('|')
        tag = sanitize_input(tag.strip('# '))
        content = sanitize_input(content.strip())
        expire = sanitize_input(expire.strip())
        if not validate_time_format(expire):
            return bot.reply_to(message, "❌ Invalid expire format (e.g., 1d)!")
        if safe_db_operation("INSERT INTO notes VALUES (?, ?, ?, ?)", (chat_id, tag, content, expire)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Note saved!")
        else:
            bot.reply_to(message, "❌ Error saving note!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# RSS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'rss_menu')
def rss_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "📰 RSS MENU\n\n" \
           "➕ Add Feed: New URL\n" \
           "📝 List: View feeds\n" \
           "✏️ Edit: Modify feed"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Feed", callback_data='rss_add'),
        types.InlineKeyboardButton("📝 List", callback_data='rss_list'),
        types.InlineKeyboardButton("✏️ Edit", callback_data='rss_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('rss_'))
def rss_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'add':
        bot.temp_data[chat_id] = {'action': 'rss_add', 'timeout': time.time() + 300}
        text = "➕ Send: url|keywords|interval(1h)|format"
    elif action == 'list':
        text = "📝 RSS feeds: None (placeholder)."
    elif action == 'edit':
        text = "✏️ Edit feed (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='rss_menu'),
        types.InlineKeyboardButton("➕ Add Feed", callback_data='rss_add')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_rss_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        url, kw, interval, fmt = message.text.split('|')
        url = sanitize_input(url.strip())
        kw = sanitize_input(kw.strip())
        interval = sanitize_input(interval.strip())
        fmt = sanitize_input(fmt.strip())
        if not validate_url(url):
            return bot.reply_to(message, "❌ Invalid URL!")
        if not validate_time_format(interval):
            return bot.reply_to(message, "❌ Invalid interval format (e.g., 1h)!")
        if safe_db_operation("INSERT INTO rss_feeds VALUES (?, ?, ?, ?, ?)", (chat_id, url, kw, interval, fmt)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ RSS added!")
        else:
            bot.reply_to(message, "❌ Error adding RSS!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# SUBSCRIPTIONS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'subs_menu')
def subs_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "💰 SUBSCRIPTIONS MENU\n\n" \
           "➕ Grant Plan: Assign to user\n" \
           "📝 List: View subs\n" \
           "✏️ Edit: Modify plan"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Grant Plan", callback_data='sub_grant'),
        types.InlineKeyboardButton("📝 List", callback_data='sub_list'),
        types.InlineKeyboardButton("✏️ Edit", callback_data='sub_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def subs_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'grant':
        bot.temp_data[chat_id] = {'action': 'sub_grant', 'timeout': time.time() + 300}
        text = "➕ Send: user_id|plan|duration(1m)"
    elif action == 'list':
        text = "📝 Subs: None (placeholder)."
    elif action == 'edit':
        text = "✏️ Edit sub (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='subs_menu'),
        types.InlineKeyboardButton("➕ Grant Plan", callback_data='sub_grant')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_sub_grant(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        uid, plan, dur = message.text.split('|')
        uid = sanitize_input(uid.strip())
        plan = sanitize_input(plan.strip())
        dur = sanitize_input(dur.strip())
        if not validate_time_format(dur):
            return bot.reply_to(message, "❌ Invalid duration format (e.g., 1m)!")
        if safe_db_operation("INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?)", (chat_id, uid, plan, dur, 1)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Subscription granted!")
        else:
            bot.reply_to(message, "❌ Error granting subscription!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# FEDERATION MENU
@bot.callback_query_handler(func=lambda call: call.data == 'fed_menu')
def fed_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🔗 FEDERATION MENU\n\n" \
           "🔗 Link Group: Connect groups\n" \
           "📝 List: View links\n" \
           "⚙️ Sync: Action sync settings"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔗 Link Group", callback_data='fed_link'),
        types.InlineKeyboardButton("📝 List", callback_data='fed_list'),
        types.InlineKeyboardButton("⚙️ Sync", callback_data='fed_sync'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fed_'))
def fed_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'link':
        bot.temp_data[chat_id] = {'action': 'fed_link', 'timeout': time.time() + 300}
        text = "🔗 Send linked group ID:"
    elif action == 'list':
        text = "📝 Federations: None (placeholder)."
    elif action == 'sync':
        text = "⚙️ Sync settings updated (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='fed_menu'),
        types.InlineKeyboardButton("🔗 Link Group", callback_data='fed_link')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_fed_link(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    linked = sanitize_input(message.text)
    if safe_db_operation("INSERT INTO federations VALUES (?, ?, ?, ?)", (chat_id, linked, 'all', 1)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, "✅ Group linked!")
    else:
        bot.reply_to(message, "❌ Error linking group!")

# CAPTCHA MENU (CONTINUED)
@bot.callback_query_handler(func=lambda call: call.data == 'captcha_menu')
def captcha_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🎲 CAPTCHA MENU\n\n" \
           "⚙️ Set Type: Math/text/image\n" \
           "📊 Difficulty: Easy/hard\n" \
           "⏰ Time Limit: Fail timeout\n" \
           "🛑 Fail Action: Kick/mute"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ Set Type", callback_data='captcha_set_type'),
        types.InlineKeyboardButton("📊 Difficulty", callback_data='captcha_difficulty'),
        types.InlineKeyboardButton("⏰ Time Limit", callback_data='captcha_time'),
        types.InlineKeyboardButton("🛑 Fail Action", callback_data='captcha_fail_action'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='captcha_help')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'set_type':
        text = "⚙️ Select CAPTCHA Type:\n\n" \
               "🔢 Math: Simple equations\n" \
               "📝 Text: Word-based\n" \
               "🖼️ Image: Visual challenge"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔢 Math", callback_data='captcha_type_math'),
            types.InlineKeyboardButton("📝 Text", callback_data='captcha_type_text'),
            types.InlineKeyboardButton("🖼️ Image", callback_data='captcha_type_image'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'type_math' or action == 'type_text' or action == 'type_image':
        captcha_type = action.split('_')[2]
        bot.temp_data[chat_id] = {'action': 'captcha_set', 'sub_action': 'type', 'value': captcha_type, 'timeout': time.time() + 300}
        text = f"✅ CAPTCHA type set to {captcha_type}. Set difficulty or save:"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📊 Difficulty", callback_data='captcha_difficulty'),
            types.InlineKeyboardButton("💾 Save", callback_data='captcha_save'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='captcha_help')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'difficulty':
        bot.temp_data[chat_id] = {'action': 'captcha_set', 'sub_action': 'difficulty', 'timeout': time.time() + 300}
        text = "📊 Send difficulty (easy/medium/hard):"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("💾 Save", callback_data='captcha_save')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'time':
        bot.temp_data[chat_id] = {'action': 'captcha_set', 'sub_action': 'time_limit', 'timeout': time.time() + 300}
        text = "⏰ Send time limit (e.g., 5m):"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("💾 Save", callback_data='captcha_save')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'fail_action':
        bot.temp_data[chat_id] = {'action': 'captcha_set', 'sub_action': 'fail_action', 'timeout': time.time() + 300}
        text = "🛑 Send fail action (kick/mute):"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("💾 Save", callback_data='captcha_save')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'save':
        if chat_id in bot.temp_data and 'captcha_config' in bot.temp_data[chat_id]:
            config = bot.temp_data[chat_id]['captcha_config']
            if safe_db_operation("INSERT OR REPLACE INTO captchas VALUES (?, ?, ?, ?, ?)", 
                               (chat_id, config.get('type', 'math'), config.get('difficulty', 'easy'), 
                                config.get('time_limit', 300), config.get('fail_action', 'kick'))):
                del bot.temp_data[chat_id]
                text = "✅ CAPTCHA settings saved!"
            else:
                text = "❌ Error saving CAPTCHA settings!"
        else:
            text = "❌ No CAPTCHA settings to save!"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("⚙️ Set Type", callback_data='captcha_set_type')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'help':
        text = "🎲 CAPTCHA Help:\n\n- Set Type: Choose math/text/image\n- Difficulty: Easy/medium/hard\n- Time Limit: Fail timeout\n- Fail Action: Kick or mute"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
            types.InlineKeyboardButton("⚙️ Set Type", callback_data='captcha_set_type')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_captcha_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data or 'sub_action' not in bot.temp_data[chat_id]:
        return
    sub_action = bot.temp_data[chat_id]['sub_action']
    value = sanitize_input(message.text)
    
    if chat_id not in bot.temp_data:
        bot.temp_data[chat_id] = {'action': 'captcha_set', 'captcha_config': {}}
    bot.temp_data[chat_id]['captcha_config'] = bot.temp_data[chat_id].get('captcha_config', {})
    
    if sub_action == 'difficulty':
        if value.lower() not in ['easy', 'medium', 'hard']:
            return bot.reply_to(message, "❌ Invalid difficulty! Use easy/medium/hard.")
        bot.temp_data[chat_id]['captcha_config']['difficulty'] = value.lower()
    elif sub_action == 'time_limit':
        if not validate_time_format(value):
            return bot.reply_to(message, "❌ Invalid time format (e.g., 5m)!")
        bot.temp_data[chat_id]['captcha_config']['time_limit'] = parse_time(value)
    elif sub_action == 'fail_action':
        if value.lower() not in ['kick', 'mute']:
            return bot.reply_to(message, "❌ Invalid action! Use kick/mute.")
        bot.temp_data[chat_id]['captcha_config']['fail_action'] = value.lower()
    
    text = f"✅ {sub_action.replace('_', ' ').title()} set to {value}. Save or continue:"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💾 Save", callback_data='captcha_save'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='captcha_menu'),
        types.InlineKeyboardButton("⚙️ Set Type", callback_data='captcha_set_type'),
        types.InlineKeyboardButton("📊 Difficulty", callback_data='captcha_difficulty')
    )
    bot.send_message(chat_id, text, reply_markup=markup)

# MESSAGE DUMP MENU
@bot.callback_query_handler(func=lambda call: call.data == 'dump_menu')
def dump_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "💾 MESSAGE DUMP MENU\n\n" \
           "🛑 Enable: Turn on/off\n" \
           "📤 Channel: Set dump channel\n" \
           "📝 View: See dumped messages"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛑 Enable", callback_data='dump_enable'),
        types.InlineKeyboardButton("📤 Channel", callback_data='dump_channel'),
        types.InlineKeyboardButton("📝 View", callback_data='dump_view'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dump_'))
def dump_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'enable':
        bot.temp_data[chat_id] = {'action': 'dump_set', 'sub_action': 'enable', 'timeout': time.time() + 300}
        text = "🛑 Send 'on' or 'off' to enable/disable message dump:"
    elif action == 'channel':
        bot.temp_data[chat_id] = {'action': 'dump_set', 'sub_action': 'channel', 'timeout': time.time() + 300}
        text = "📤 Send channel ID for message dump:"
    elif action == 'view':
        rows = safe_db_operation("SELECT deleted_msg, user_id, timestamp FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
        text = "📝 DUMPED MESSAGES:\n" + "\n".join(f"• {row[2]} by {row[1]}: {row[0]}" for row in rows) or "No dumped messages."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='dump_menu'),
        types.InlineKeyboardButton("🛑 Enable", callback_data='dump_enable')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_dump_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data or 'sub_action' not in bot.temp_data[chat_id]:
        return
    sub_action = bot.temp_data[chat_id]['sub_action']
    value = sanitize_input(message.text)
    
    if sub_action == 'enable':
        if value.lower() not in ['on', 'off']:
            return bot.reply_to(message, "❌ Invalid input! Use 'on' or 'off'.")
        if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, 'message_dump', 'status', ?)", 
                           (chat_id, json.dumps({'status': value.lower()}))):
            del bot.temp_data[chat_id]
            bot.reply_to(message, f"✅ Message dump {'enabled' if value.lower() == 'on' else 'disabled'}!")
        else:
            bot.reply_to(message, "❌ Error updating dump settings!")
    elif sub_action == 'channel':
        if not value.startswith('-'):
            return bot.reply_to(message, "❌ Invalid channel ID!")
        if safe_db_operation("INSERT OR REPLACE INTO message_dump VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, '', '', datetime.now().strftime("%Y-%m-%d %H:%M:%S"), value)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Dump channel set!")
        else:
            bot.reply_to(message, "❌ Error setting dump channel!")

# PLUGINS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'plugins_menu')
def plugins_menu(call):
    chat_id = str(call.message.chat.id)
    
    text = "🔌 PLUGINS MENU\n\n" \
           "➕ Install: Add new plugin\n" \
           "📝 List: View plugins\n" \
           "⚙️ Config: Plugin settings"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Install", callback_data='plugin_install'),
        types.InlineKeyboardButton("📝 List", callback_data='plugin_list'),
        types.InlineKeyboardButton("⚙️ Config", callback_data='plugin_config'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('plugin_'))
def plugins_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'install':
        bot.temp_data[chat_id] = {'action': 'plugin_install', 'timeout': time.time() + 300}
        text = "➕ Send plugin name and config (name|config):"
    elif action == 'list':
        rows = safe_db_operation("SELECT plugin_name, config FROM plugins WHERE chat_id=?", (chat_id,), "fetch")
        text = "📝 PLUGINS:\n" + "\n".join(f"• {row[0]}: {row[1]}" for row in rows) or "No plugins."
    elif action == 'config':
        bot.temp_data[chat_id] = {'action': 'plugin_config', 'timeout': time.time() + 300}
        text = "⚙️ Send plugin name to configure:"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='plugins_menu'),
        types.InlineKeyboardButton("➕ Install", callback_data='plugin_install')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_plugin_install(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        name, config = message.text.split('|')
        name = sanitize_input(name.strip())
        config = sanitize_input(config.strip())
        if safe_db_operation("INSERT INTO plugins VALUES (?, ?, ?, ?)", (chat_id, name, config, 1)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, "✅ Plugin installed!")
        else:
            bot.reply_to(message, "❌ Error installing plugin!")
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# MODERATION LOCKS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'moderation_lock')
def moderation_lock_menu(call):
    chat_id = str(call.message.chat.id)
    settings = get_all_settings(chat_id)
    
    text = "🔒 MODERATION LOCKS\n\n" \
           f"🔗 Links: {'✅' if safe_json(settings.get('moderation_lock_links', '{}'))['status'] == 'on' else '❌'}\n" \
           f"📸 Media: {'✅' if safe_json(settings.get('moderation_lock_media', '{}'))['status'] == 'on' else '❌'}\n" \
           f"😀 Stickers: {'✅' if safe_json(settings.get('moderation_lock_stickers', '{}'))['status'] == 'on' else '❌'}\n" \
           f"📤 Forwards: {'✅' if safe_json(settings.get('moderation_lock_forwards', '{}'))['status'] == 'on' else '❌'}"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔗 Links", callback_data='lock_links'),
        types.InlineKeyboardButton("📸 Media", callback_data='lock_media'),
        types.InlineKeyboardButton("😀 Stickers", callback_data='lock_stickers'),
        types.InlineKeyboardButton("📤 Forwards", callback_data='lock_forwards'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='lock_help')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lock_'))
def lock_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    bot.temp_data[chat_id] = {'action': f'lock_{action}', 'timeout': time.time() + 300}
    text = f"🔒 Send 'on' or 'off' to {'enable' if action == 'links' else 'restrict'} {action}:"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='moderation_lock'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='lock_help')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

@bot.message_handler(func=lambda message: message.chat.id in bot.temp_data and bot.temp_data[str(message.chat.id)].get('action', '').startswith('lock_'))
def handle_lock_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    action = bot.temp_data[chat_id]['action'].split('_')[1]
    value = sanitize_input(message.text).lower()
    
    if value not in ['on', 'off']:
        return bot.reply_to(message, "❌ Invalid input! Use 'on' or 'off'.")
    
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, ?, ?, ?)", 
                       (chat_id, 'moderation', f'lock_{action}', json.dumps({'status': value}))):
        del bot.temp_data[chat_id]
        bot.reply_to(message, f"✅ {action.capitalize()} lock {'enabled' if value == 'on' else 'disabled'}!")
    else:
        bot.reply_to(message, f"❌ Error setting {action} lock!")

# SHOW COMMANDS
@bot.callback_query_handler(func=lambda call: call.data == 'show_commands')
def show_commands(call):
    chat_id = str(call.message.chat.id)
    
    text = "📋 AVAILABLE COMMANDS\n\n" \
           "/start - Start bot\n" \
           "/status - Group settings\n" \
           "/warn @user reason - Warn user\n" \
           "/unwarn @user - Remove warn\n" \
           "/ban @user reason - Ban user\n" \
           "/unban @user - Unban user\n" \
           "/mute @user time reason - Mute user\n" \
           "/unmute @user - Unmute user\n" \
           "/settings - Open settings"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔧 Settings", callback_data='main'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

# WEBHOOK SETUP
@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return '', 200

if __name__ == '__main__':
bot.remove_webhook()
bot.set_webhook(url='https://throogpt.vercel.app/webhook')
    app.run(host='0.0.0.0', port=5000)
