 from flask import Flask, request
import telebot, os, sqlite3, json, time, random, re
from telebot import types
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

conn = sqlite3.connect('data.db', check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS settings (chat_id INT PRIMARY KEY, data TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS permissions (chat_id INT, command TEXT, allowed TEXT, PRIMARY KEY (chat_id, command))''')
conn.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INT, user_id INT, warns INT DEFAULT 0, xp INT DEFAULT 0, PRIMARY KEY (chat_id, user_id))''')
conn.execute('''CREATE TABLE IF NOT EXISTS captcha (chat_id INT, user_id INT, answer INT, message_id INT, PRIMARY KEY (chat_id, user_id))''')
conn.commit()

# Spam detection
spam_users = defaultdict(lambda: defaultdict(list))

def spam_check(user_id, chat_id):
    settings = get_settings(chat_id)
    if not settings.get('antispam', False): return False
    now = time.time()
    spam_users[chat_id][user_id] = [t for t in spam_users[chat_id].get(user_id, []) if now - t < 10]
    spam_users[chat_id][user_id].append(now)
    return len(spam_users[chat_id][user_id]) > settings.get('flood_limit', 5)

def get_settings(chat_id):
    cursor = conn.execute("SELECT data FROM settings WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    return json.loads(row[0]) if row else {}

def save_settings(chat_id, data):
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", 
                 (chat_id, json.dumps(data)))
    conn.commit()

def get_permission(chat_id, command):
    cursor = conn.execute("SELECT allowed FROM permissions WHERE chat_id=? AND command=?", (chat_id, command))
    row = cursor.fetchone()
    return row[0] if row else 'admins'

def is_allowed(chat_id, user_id, command):
    allowed = get_permission(chat_id, command)
    if allowed == 'everyone': return True
    member = bot.get_chat_member(chat_id, user_id)
    return member.status in ['administrator', 'creator']

def add_warn(chat_id, user_id):
    cursor = conn.execute("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = cursor.fetchone()
    warns = row[0] + 1 if row else 1
    conn.execute("INSERT OR REPLACE INTO users (chat_id, user_id, warns) VALUES (?, ?, ?)", (chat_id, user_id, warns))
    conn.commit()
    return warns

def add_xp(chat_id, user_id, amount=1):
    cursor = conn.execute("SELECT xp FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = cursor.fetchone()
    xp = row[0] + amount if row else amount
    conn.execute("INSERT OR REPLACE INTO users (chat_id, user_id, xp) VALUES (?, ?, ?)", (chat_id, user_id, xp))
    conn.commit()

def send_log(chat_id, text):
    settings = get_settings(chat_id)
    log_channel = settings.get('log_channel')
    if log_channel:
        bot.send_message(log_channel, text)

class Buttons:
    @staticmethod
    def main():
        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = [('🚫 AntiSpam', 'antispam'), ('👋 Welcome/Captcha', 'welcome'), 
                ('🔒 Ban/Mute/Kick', 'ban'), ('📜 Rules', 'rules'),
                ('🔐 Locks', 'locks'), ('📝 Filters/Notes', 'filters'),
                ('🚫 Blacklist', 'blacklist'), ('⚠️ Warnings', 'warnings'),
                ('📌 Pin', 'pin'), ('📈 Leveling', 'leveling'),
                ('🧹 AutoClean', 'autoclean'), ('⚙️ Permissions', 'perms'),
                ('📋 Logs', 'logs'), ('❌ OFF All', 'off')]
        for t, d in btns: markup.add(types.InlineKeyboardButton(t, callback_data=d))
        return markup

    @staticmethod
    def settings(feature):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton('ON', callback_data=f'{feature}_on'),
                   types.InlineKeyboardButton('OFF', callback_data=f'{feature}_off'))
        markup.add(types.InlineKeyboardButton('Customize', callback_data=f'{feature}_custom'))
        markup.add(types.InlineKeyboardButton('Back', callback_data='main'))
        return markup

    @staticmethod
    def perms():
        markup = types.InlineKeyboardMarkup(row_width=2)
        cmds = ['antispam', 'welcome', 'ban', 'rules', 'locks', 'filters', 'blacklist', 'warnings', 'pin', 'leveling', 'autoclean']
        for cmd in cmds:
            markup.add(types.InlineKeyboardButton(f'Set {cmd}', callback_data=f'perm_{cmd}'))
        markup.add(types.InlineKeyboardButton('Back', callback_data='main'))
        return markup

    @staticmethod
    def perm_options(command):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton('Admins Only', callback_data=f'permset_{command}_admins'),
                   types.InlineKeyboardButton('Everyone', callback_data=f'permset_{command}_everyone'))
        markup.add(types.InlineKeyboardButton('Back', callback_data='perms'))
        return markup

    @staticmethod
    def captcha(user_id, chat_id, nums):
        markup = types.InlineKeyboardMarkup(row_width=3)
        options = [nums[0], nums[1], random.randint(1,20)]
        random.shuffle(options)
        for opt in options:
            markup.add(types.InlineKeyboardButton(str(opt), callback_data=f'captcha_{opt}'))
        return markup

@bot.message_handler(commands=['start', 'settings'])
def start(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'settings'): return
    bot.send_message(m.chat.id, "🤖 **Advanced Bot Settings** 🎉\nChoose feature:", reply_markup=Buttons.main())

@bot.message_handler(commands=['help'])
def help_cmd(m):
    help_text = """
🤖 **Advanced Bot Commands List**:

/start or /settings - Open inline settings menu (if allowed). Desc: Control all features.

/antispam [on/off/limit N] - Toggle anti-spam, set flood limit. Desc: Auto-ban >N msgs/10sec.

/welcome [on/off/set text] - Toggle/set custom welcome with captcha. Desc: Greet + verify new users.

/captcha [on/off] - Toggle captcha for new members. Desc: Math quiz to prove human.

/ban [reply] - Ban user. Desc: Permanent remove.

/mute [reply/time min] - Mute user (optional time). Desc: Restrict messages.

/kick [reply] - Kick user. Desc: Remove but can rejoin.

/promote [reply] - Promote to admin. Desc: Give admin rights.

/demote [reply] - Demote admin. Desc: Remove admin rights.

/rules [set text] - Set/display rules. Desc: Show on join or /rules.

/locks [type on/off] (types: media, links, stickers, polls, forwards, buttons) - Lock content. Desc: Auto-delete.

/filters [add keyword reply_text/regex] - Add auto-reply filter (regex optional). Desc: Reply on match.

/notes [add name text] - Add note. Desc: Save text, get with #name or /get name.

/blacklist [add word/regex] - Add to blacklist. Desc: Auto-delete/ban on match.

/warn [reply/reason] - Warn user. Desc: Track warns, ban after max (set with /warnlimit N).

/warnings [reply] - Check user warns. Desc: View count.

/pin [reply] - Pin message. Desc: Pin replied msg.

/leveling [on/off] - Toggle XP system. Desc: Earn XP per msg, /rank for leaderboard.

/autoclean [on/off] - Toggle auto-clean. Desc: Delete joins/leaves/service msgs.

/setlog [channel_id] - Set log channel. Desc: Send actions logs there.

/setperm [command admins/everyone] - Set command access. Desc: Control who uses.

/help - This list.
    """
    bot.send_message(m.chat.id, help_text)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    chat_id = c.message.chat.id
    if not is_allowed(chat_id, c.from_user.id, 'settings'): return bot.answer_callback_query(c.id, "Not allowed!")
    data = c.data
    settings = get_settings(chat_id)
    
    if data == 'main':
        bot.edit_message_text("Choose feature:", chat_id, c.message.message_id, reply_markup=Buttons.main())
    elif data in ['antispam', 'welcome', 'rules', 'locks', 'filters', 'blacklist', 'warnings', 'pin', 'leveling', 'autoclean', 'ban']:
        bot.edit_message_text(f"Set {data}:", chat_id, c.message.message_id, reply_markup=Buttons.settings(data))
    elif data == 'perms':
        bot.edit_message_text("Set Permissions:", chat_id, c.message.message_id, reply_markup=Buttons.perms())
    elif data == 'logs':
        bot.answer_callback_query(c.id, "Use /setlog [channel_id] to set!")
    elif data.startswith('perm_'):
        command = data.split('_')[1]
        bot.edit_message_text(f"Set for {command}:", chat_id, c.message.message_id, reply_markup=Buttons.perm_options(command))
    elif data.startswith('permset_'):
        parts = data.split('_')
        command, level = parts[1], parts[2]
        conn.execute("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?)", (chat_id, command, level))
        conn.commit()
        bot.answer_callback_query(c.id, f"{command} set to {level}!")
        bot.edit_message_text("Permissions Updated!", chat_id, c.message.message_id, reply_markup=Buttons.perms())
    elif data.endswith('_on') or data.endswith('_off'):
        feature = data.split('_')[0]
        settings[feature] = data.endswith('_on')
        save_settings(chat_id, settings)
        bot.answer_callback_query(c.id, f"{feature.capitalize()} {'ON' if settings[feature] else 'OFF'}!")
    elif data.endswith('_custom'):
        feature = data.split('_')[0]
        bot.answer_callback_query(c.id, f"Use /{feature} [options] to customize!")
    elif data == 'off':
        for key in list(settings.keys()):
            if isinstance(settings[key], bool): settings[key] = False
        save_settings(chat_id, settings)
        bot.answer_callback_query(c.id, "All Features OFF!")
    elif data.startswith('captcha_'):
        answer = int(data.split('_')[1])
        cursor = conn.execute("SELECT answer, message_id FROM captcha WHERE chat_id=? AND user_id=?", (chat_id, c.from_user.id))
        row = cursor.fetchone()
        if row and answer == row[0]:
            bot.restrict_chat_member(chat_id, c.from_user.id, can_send_messages=True)
            bot.delete_message(chat_id, row[1])
            bot.answer_callback_query(c.id, "Verified!")
            conn.execute("DELETE FROM captcha WHERE chat_id=? AND user_id=?", (chat_id, c.from_user.id))
            conn.commit()
        else:
            bot.answer_callback_query(c.id, "Wrong! Try again.")

@bot.message_handler(commands=['antispam'])
def antispam_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'antispam'): return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['antispam'] = True
        elif args[0] == 'off': settings['antispam'] = False
        elif args[0] == 'limit' and len(args) > 1: settings['flood_limit'] = int(args[1])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"AntiSpam: {settings.get('antispam', False)}, Limit: {settings.get('flood_limit', 5)}")

@bot.message_handler(commands=['welcome'])
def welcome_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'welcome'): return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['welcome'] = True
        elif args[0] == 'off': settings['welcome'] = False
        elif args[0] == 'set': settings['welcome_text'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Welcome: {settings.get('welcome', False)}, Text: {settings.get('welcome_text', 'Welcome!')}")

@bot.message_handler(commands=['captcha'])
def captcha_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'welcome'): return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['captcha'] = True
        elif args[0] == 'off': settings['captcha'] = False
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Captcha: {settings.get('captcha', False)}")

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'ban'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.ban_chat_member(m.chat.id, user_id)
        bot.reply_to(m, "User Banned!")
        send_log(m.chat.id, f"User {user_id} banned by {m.from_user.id}")

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'ban'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        until = None
        args = m.text.split()[1:]
        if args and args[0].isdigit(): until = time.time() + int(args[0]) * 60
        bot.restrict_chat_member(m.chat.id, user_id, until_date=until, can_send_messages=False)
        bot.reply_to(m, "User Muted!")
        send_log(m.chat.id, f"User {user_id} muted by {m.from_user.id}")

@bot.message_handler(commands=['kick'])
def kick_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'ban'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.ban_chat_member(m.chat.id, user_id)
        bot.unban_chat_member(m.chat.id, user_id)
        bot.reply_to(m, "User Kicked!")
        send_log(m.chat.id, f"User {user_id} kicked by {m.from_user.id}")

@bot.message_handler(commands=['promote'])
def promote_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'ban'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.promote_chat_member(m.chat.id, user_id, can_change_info=True, can_post_messages=True, can_edit_messages=True,
                                can_delete_messages=True, can_invite_users=True, can_restrict_members=True, can_pin_messages=True,
                                can_promote_members=False)
        bot.reply_to(m, "User Promoted!")
        send_log(m.chat.id, f"User {user_id} promoted by {m.from_user.id}")

@bot.message_handler(commands=['demote'])
def demote_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'ban'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.promote_chat_member(m.chat.id, user_id, can_change_info=False, can_post_messages=False, can_edit_messages=False,
                                can_delete_messages=False, can_invite_users=False, can_restrict_members=False, can_pin_messages=False,
                                can_promote_members=False)
        bot.reply_to(m, "User Demoted!")
        send_log(m.chat.id, f"User {user_id} demoted by {m.from_user.id}")

@bot.message_handler(commands=['rules'])
def rules_cmd(m):
    settings = get_settings(m.chat.id)
    if len(m.text.split()) > 1 and is_allowed(m.chat.id, m.from_user.id, 'rules'):
        args = m.text.split()[1:]
        if args[0] == 'set': settings['rules_text'] = ' '.join(args[1:])
        save_settings(m.chat.id, settings)
    rules = settings.get('rules_text', 'No rules set.')
    bot.reply_to(m, f"Rules: {rules}")

@bot.message_handler(commands=['locks'])
def locks_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'locks'): return
    args = m.text.split()[1:]
    if len(args) < 2: return bot.reply_to(m, "Usage: /locks [type] [on/off] (types: media, links, stickers, polls, forwards, buttons)")
    lock_type, state = args[0], args[1] == 'on'
    settings = get_settings(m.chat.id)
    settings[f'lock_{lock_type}'] = state
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Lock {lock_type}: {state}")

@bot.message_handler(commands=['filters'])
def filters_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'filters'): return
    args = m.text.split()[1:]
    if len(args) < 3 or args[0] != 'add': return bot.reply_to(m, "Usage: /filters add [keyword/regex:] [reply_text]")
    keyword = args[1]
    reply_text = ' '.join(args[2:])
    settings = get_settings(m.chat.id)
    if 'filters' not in settings: settings['filters'] = {}
    settings['filters'][keyword] = reply_text
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Filter added for {keyword}")

@bot.message_handler(commands=['notes'])
def notes_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'filters'): return
    args = m.text.split()[1:]
    if len(args) < 3 or args[0] != 'add': return bot.reply_to(m, "Usage: /notes add [name] [text]")
    name, text = args[1], ' '.join(args[2:])
    settings = get_settings(m.chat.id)
    if 'notes' not in settings: settings['notes'] = {}
    settings['notes'][name] = text
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Note {name} added")

@bot.message_handler(commands=['get'])
def get_note_cmd(m):
    args = m.text.split()[1:]
    if not args: return
    name = args[0]
    settings = get_settings(m.chat.id)
    text = settings.get('notes', {}).get(name)
    if text: bot.reply_to(m, text)

@bot.message_handler(commands=['blacklist'])
def blacklist_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'blacklist'): return
    args = m.text.split()[1:]
    if len(args) < 2 or args[0] != 'add': return bot.reply_to(m, "Usage: /blacklist add [word/regex:]")
    word = args[1]
    settings = get_settings(m.chat.id)
    if 'blacklist' not in settings: settings['blacklist'] = []
    settings['blacklist'].append(word)
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Blacklist added: {word}")

@bot.message_handler(commands=['warn'])
def warn_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'warnings'): return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        warns = add_warn(m.chat.id, user_id)
        max_warns = get_settings(m.chat.id).get('warn_limit', 3)
        bot.reply_to(m, f"User warned ({warns}/{max_warns})!")
        send_log(m.chat.id, f"User {user_id} warned by {m.from_user.id} ({warns}/{max_warns})")
        if warns >= max_warns:
            bot.ban_chat_member(m.chat.id, user_id)
            bot.send_message(m.chat.id, "User banned for max warns!")
            send_log(m.chat.id, f"User {user_id} banned for max warns")

@bot.message_handler(commands=['warnings'])
def warnings_cmd(m):
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
    else:
        user_id = m.from_user.id
    cursor = conn.execute("SELECT warns FROM users WHERE chat_id=? AND user_id=?", (m.chat.id, user_id))
    row = cursor.fetchone()
    warns = row[0] if row else 0
    bot.reply_to(m, f"Warnings: {warns}")

@bot.message_handler(commands=['warnlimit'])
def warnlimit_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'warnings'): return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['warn_limit'] = int(args[0])
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"Warn limit set to {args[0]}")

@bot.message_handler(commands=['pin'])
def pin_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'pin'): return
    if m.reply_to_message:
        bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id)
        bot.reply_to(m, "Message Pinned!")
        send_log(m.chat.id, f"Message pinned by {m.from_user.id}")

@bot.message_handler(commands=['leveling'])
def leveling_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'leveling'): return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['leveling'] = True
        elif args[0] == 'off': settings['leveling'] = False
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"Leveling: {settings.get('leveling', False)}")

@bot.message_handler(commands=['rank'])
def rank_cmd(m):
    cursor = conn.execute("SELECT user_id, xp FROM users WHERE chat_id=? ORDER BY xp DESC LIMIT 10", (m.chat.id,))
    ranks = cursor.fetchall()
    text = "Leaderboard:\n"
    for i, (uid, xp) in enumerate(ranks, 1):
        user = bot.get_chat_member(m.chat.id, uid).user
        text += f"{i}. {user.first_name} - {xp} XP\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=['autoclean'])
def autoclean_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'autoclean'): return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['autoclean'] = True
        elif args[0] == 'off': settings['autoclean'] = False
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"AutoClean: {settings.get('autoclean', False)}")

@bot.message_handler(commands=['setlog'])
def setlog_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'logs'): return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['log_channel'] = args[0]
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"Log channel set to {args[0]}")

@bot.message_handler(commands=['setperm'])
def setperm_cmd(m):
    if not is_allowed(m.chat.id, m.from_user.id, 'perms'): return
    args = m.text.split()[1:]
    if len(args) < 2: return bot.reply_to(m, "Usage: /setperm [command] [admins/everyone]")
    command, level = args[0], args[1]
    conn.execute("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?)", (m.chat.id, command, level))
    conn.commit()
    bot.reply_to(m, f"{command} set to {level}")

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(m):
    chat_id = m.chat.id
    settings = get_settings(chat_id)
    for member in m.new_chat_members:
        user_id = member.id
        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
        if settings.get('welcome', False):
            text = settings.get('welcome_text', 'Welcome!') + "\n" + settings.get('rules_text', '')
            bot.send_message(chat_id, f"{text} @{member.username}")
        if settings.get('captcha', False):
            a, b = random.randint(1,10), random.randint(1,10)
            answer = a + b
            msg = bot.send_message(chat_id, f"Verify: {a} + {b} = ?", reply_markup=Buttons.captcha(user_id, chat_id, [answer, a*b]))
            conn.execute("INSERT OR REPLACE INTO captcha VALUES (?, ?, ?, ?)", (chat_id, user_id, answer, msg.message_id))
            conn.commit()
        send_log(chat_id, f"New member {user_id}")

@bot.message_handler(content_types=['left_chat_member'])
def handle_left(m):
    settings = get_settings(m.chat.id)
    if settings.get('autoclean', False):
        bot.delete_message(m.chat.id, m.message_id)

@bot.message_handler(func=lambda m: True)
def handle_messages(m):
    chat_id = m.chat.id
    user_id = m.from_user.id if m.from_user else None
    settings = get_settings(chat_id)
    text = m.text.lower() if m.text else ''
    
    if user_id:
        # Leveling
        if settings.get('leveling', False) and not m.text.startswith('/'):
            add_xp(chat_id, user_id)
        
        # Anti-spam
        if settings.get('antispam', False) and spam_check(user_id, chat_id):
            bot.ban_chat_member(chat_id, user_id)
            bot.send_message(chat_id, "🚫 SPAMMER BANNED!")
            send_log(chat_id, f"Spammer {user_id} banned")
            return
    
    # Auto clean service msgs
    if settings.get('autoclean', False) and (m.content_type in ['new_chat_members', 'left_chat_member', 'pinned_message'] or m.from_user is None):
        try: bot.delete_message(chat_id, m.message_id)
        except: pass
    
    # Blacklist with regex
    if 'blacklist' in settings and text:
        for pattern in settings['blacklist']:
            if pattern.startswith('regex:'): pattern = pattern[6:]
            if re.search(pattern, text, re.IGNORECASE):
                bot.delete_message(chat_id, m.message_id)
                bot.ban_chat_member(chat_id, user_id)
                bot.send_message(chat_id, "🚫 Blacklisted! User banned.")
                send_log(chat_id, f"Blacklist hit by {user_id}")
                return
    
    # Filters with regex
    if 'filters' in settings and text:
        for keyword, reply in settings['filters'].items():
            if keyword.startswith('regex:'): keyword = keyword[6:]
            if re.search(keyword, text, re.IGNORECASE):
                bot.reply_to(m, reply)
    
    # Locks
    if m.photo and settings.get('lock_media', False): bot.delete_message(chat_id, m.message_id)
    if m.sticker and settings.get('lock_stickers', False): bot.delete_message(chat_id, m.message_id)
    if m.poll and settings.get('lock_polls', False): bot.delete_message(chat_id, m.message_id)
    if m.forward_date and settings.get('lock_forwards', False): bot.delete_message(chat_id, m.message_id)
    if m.entities and any(e.type in ['url', 'text_link'] for e in m.entities) and settings.get('lock_links', False): bot.delete_message(chat_id, m.message_id)
    if m.entities and any(e.type == 'inline_keyboard' for e in m.entities) and settings.get('lock_buttons', False): bot.delete_message(chat_id, m.message_id)
    
    # Anti-channel: if from channel (anonymous)
    if m.sender_chat and settings.get('lock_channels', False): bot.delete_message(chat_id, m.message_id)

    # Notes trigger with #
    if text.startswith('#'):
        name = text[1:]
        note = settings.get('notes', {}).get(name)
        if note: bot.send_message(chat_id, note)

# Webhook
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    return 'OK', 200

@app.route('/')
def home(): return "🤖 Advanced Bot Live!"

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"https://helliobot.onrender.com/{TOKEN}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
