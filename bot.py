from flask import Flask, request
import telebot, os, sqlite3, json, time, random, re
from telebot import types
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timedelta
import threading
import openai

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# SQLite Database Setup
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
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
    conn.commit()
    conn.close()

init_db()

# Utility Functions
def parse_time(text):
    try:
        total_seconds = 0
        matches = re.findall(r'(\d+)([smhd])', text.lower())
        for value, unit in matches:
            value = int(value)
            if unit == 's':
                total_seconds += value
            elif unit == 'm':
                total_seconds += value * 60
            elif unit == 'h':
                total_seconds += value * 3600
            elif unit == 'd':
                total_seconds += value * 86400
        return total_seconds if total_seconds > 0 else 300
    except:
        return 300

def parse_number(text):
    try:
        num = int(text)
        return num if num > 0 else 3
    except:
        return 3

def is_creator(bot, chat_id, user_id):
    if str(chat_id).startswith('-'):
        try:
            member = bot.get_chat_member(chat_id, user_id)
            return member.status == 'creator'
        except:
            return False
    return True

def delete_after_delay(bot, chat_id, message_id, delay=5):
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

def delete_previous(bot, chat_id, message_id, context):
    if 'last_bot_message' in context:
        try:
            bot.delete_message(chat_id, context['last_bot_message'])
        except:
            pass
    try:
        bot.delete_message(chat_id, message_id)
    except:
        pass

def store_message_id(context, message_id):
    context['last_bot_message'] = message_id

# Moderation Penalties
@bot.message_handler(commands=['ban', 'mute', 'kick', 'warn', 'tempban', 'tempmute', 'unwarn', 'warns'])
def moderation_penalties(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    if message.chat.type == 'private':
        sent_message = bot.reply_to(message, "Group mein reply karke use karo!")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return
    if not is_creator(bot, chat_id, message.from_user.id):
        sent_message = bot.reply_to(message, "Sirf group creator use kar sakte hain!")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return
    if not message.reply_to_message and message.text.split()[0][1:].lower() not in ['warns']:
        sent_message = bot.reply_to(message, "User ke message pe reply karo!")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return

    command = message.text.split()[0][1:].lower()
    user_id = str(message.reply_to_message.from_user.id) if message.reply_to_message else None
    username = message.reply_to_message.from_user.username if message.reply_to_message else str(user_id)
    reason = ' '.join(message.text.split()[2:]) if len(message.text.split()) > 2 else "No reason provided"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    try:
        if command == 'ban':
            bot.kick_chat_member(chat_id, user_id)
            sent_message = bot.reply_to(message, f"User @{username} banned!")
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'ban', user_id, reason, timestamp))
        elif command == 'mute':
            bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False))
            sent_message = bot.reply_to(message, f"User @{username} muted!")
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'mute', user_id, reason, timestamp))
        elif command == 'kick':
            bot.kick_chat_member(chat_id, user_id)
            bot.unban_chat_member(chat_id, user_id)
            sent_message = bot.reply_to(message, f"User @{username} kicked!")
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'kick', user_id, reason, timestamp))
        elif command == 'warn':
            c.execute("INSERT OR REPLACE INTO warns (chat_id, user_id, warns, reason, timestamp) VALUES (?, ?, COALESCE((SELECT warns + 1 FROM warns WHERE chat_id=? AND user_id=?), 1), ?, ?)",
                      (chat_id, user_id, chat_id, user_id, reason, timestamp))
            c.execute("SELECT warns FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            warns = c.fetchone()[0]
            c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', 'warns'))
            settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'on', 'limit': 3, 'action': 'ban'}
            sent_message = bot.reply_to(message, f"User @{username} warned ({warns}/{settings['limit']})! Reason: {reason}")
            if warns >= settings['limit']:
                if settings['action'] == 'ban':
                    bot.kick_chat_member(chat_id, user_id)
                    sent_message = bot.reply_to(message, f"User @{username} banned for exceeding warn limit!")
                elif settings['action'] == 'mute':
                    bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False))
                    sent_message = bot.reply_to(message, f"User @{username} muted for exceeding warn limit!")
                c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (chat_id, settings['action'], user_id, f"Exceeded warn limit ({warns})", timestamp))
        elif command == 'tempban':
            duration = parse_time(message.text.split()[2]) if len(message.text.split()) > 2 else 3600
            bot.kick_chat_member(chat_id, user_id, until_date=datetime.now() + timedelta(seconds=duration))
            sent_message = bot.reply_to(message, f"User @{username} banned for {duration} seconds!")
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'tempban', user_id, f"{reason} (Duration: {duration}s)", timestamp))
        elif command == 'tempmute':
            duration = parse_time(message.text.split()[2]) if len(message.text.split()) > 2 else 3600
            bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(seconds=duration))
            sent_message = bot.reply_to(message, f"User @{username} muted for {duration} seconds!")
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'tempmute', user_id, f"{reason} (Duration: {duration}s)", timestamp))
        elif command == 'unwarn':
            c.execute("SELECT warns FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
            warns = c.fetchone()[0] if c.fetchone() else 0
            if warns > 0:
                c.execute("UPDATE warns SET warns = warns - 1 WHERE chat_id=? AND user_id=?", (chat_id, user_id))
                sent_message = bot.reply_to(message, f"Removed 1 warn from @{username}. Remaining: {warns - 1}")
                c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (chat_id, 'unwarn', user_id, reason, timestamp))
            else:
                sent_message = bot.reply_to(message, f"User @{username} has no warns!")
        elif command == 'warns':
            target_user = message.text.split()[1].lstrip('@') if len(message.text.split()) > 1 else str(user_id)
            c.execute("SELECT warns, reason FROM warns WHERE chat_id=? AND user_id=?", (chat_id, target_user))
            result = c.fetchone()
            warns, reason = result if result else (0, "No warns")
            sent_message = bot.reply_to(message, f"User @{target_user} has {warns} warns. Last reason: {reason}")
        conn.commit()
        conn.close()
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    except Exception as e:
        conn.close()
        sent_message = bot.reply_to(message, f"Error: {str(e)}")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()

# Anti-Spam with OpenAI
@bot.message_handler(content_types=['text'])
def anti_spam(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', 'antispam'))
    antispam = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'sensitivity': 5, 'action': 'delete'}
    if antispam['status'] == 'on' and message.text:
        try:
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt=f"Detect if this message is spam or toxic (score 1-10, 1=safe, 10=highly spam/toxic): {message.text}",
                temperature=0.5,
                max_tokens=10
            )
            score = parse_number(response.choices[0].text.strip())
            if score >= antispam['sensitivity']:
                user_id = str(message.from_user.id)
                username = message.from_user.username or str(user_id)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if antispam['action'] == 'delete':
                    bot.delete_message(chat_id, message.message_id)
                    sent_message = bot.reply_to(message, "Spam detected and deleted!")
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'delete', user_id, "Spam detected (OpenAI score: {score})", timestamp))
                elif antispam['action'] == 'warn':
                    c.execute("INSERT OR REPLACE INTO warns (chat_id, user_id, warns, reason, timestamp) VALUES (?, ?, COALESCE((SELECT warns + 1 FROM warns WHERE chat_id=? AND user_id=?), 1), ?, ?)",
                              (chat_id, user_id, chat_id, user_id, "Spam detected", timestamp))
                    c.execute("SELECT warns FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
                    warns = c.fetchone()[0]
                    c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', 'warns'))
                    warn_settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'on', 'limit': 3, 'action': 'ban'}
                    sent_message = bot.reply_to(message, f"User @{username} warned ({warns}/{warn_settings['limit']}) for spam!")
                    if warns >= warn_settings['limit']:
                        if warn_settings['action'] == 'ban':
                            bot.kick_chat_member(chat_id, user_id)
                            sent_message = bot.reply_to(message, f"User @{username} banned for exceeding warn limit!")
                        elif warn_settings['action'] == 'mute':
                            bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False))
                            sent_message = bot.reply_to(message, f"User @{username} muted for exceeding warn limit!")
                        c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                                  (chat_id, warn_settings['action'], user_id, f"Exceeded warn limit ({warns})", timestamp))
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'warn', user_id, "Spam detected", timestamp))
                elif antispam['action'] == 'ban':
                    bot.kick_chat_member(chat_id, user_id)
                    sent_message = bot.reply_to(message, f"User @{username} banned for spam!")
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'ban', user_id, "Spam detected (OpenAI score: {score})", timestamp))
                conn.commit()
                threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        except Exception as e:
            sent_message = bot.reply_to(message, f"Anti-Spam Error: {str(e)}")
            threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    conn.close()

# DrWebBot File Scanning
@bot.message_handler(content_types=['document', 'photo', 'video'])
def file_scanner(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', 'antinsfw'))
    antinsfw = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'action': 'delete'}
    if antinsfw['status'] == 'on':
        try:
            forwarded = bot.forward_message('@DrWebBot', chat_id, message.message_id)
            sent_message = bot.reply_to(message, "File sent to @DrWebBot for scanning...")
            # Placeholder: DrWebBot reply ko handle karne ke liye
            # Tumhe DrWebBot ke response ka wait aur parse karna hoga
            c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (chat_id, 'scan', str(message.from_user.id), "File sent for scanning", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        except Exception as e:
            sent_message = bot.reply_to(message, f"Scanning Error: {str(e)}")
            threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    conn.close()

# Logs with Pagination
@bot.message_handler(commands=['logs'])
def logs_command(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    if message.chat.type == 'private' or not is_creator(bot, chat_id, message.from_user.id):
        sent_message = bot.reply_to(message, "Group mein creator ke roop mein use karo!")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return
    page = parse_number(message.text.split()[1]) if len(message.text.split()) > 1 else 1
    limit = 10
    offset = (page - 1) * limit
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT action, user_id, reason, timestamp FROM logs WHERE chat_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (chat_id, limit, offset))
    logs = c.fetchall()
    conn.close()
    if logs:
        log_text = "\n".join([f"[{t}] {a}: @{u} ({r})" for a, u, r, t in logs])
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("◀️ Previous", callback_data=f'moderation_logs_view_prev_{page}'),
            types.InlineKeyboardButton("Next ▶️", callback_data=f'moderation_logs_view_next_{page}')
        )
        sent_message = bot.reply_to(message, f"Logs Page {page}:\n{log_text}", reply_markup=markup)
    else:
        sent_message = bot.reply_to(message, f"No logs on page {page}!")
    delete_previous(bot, chat_id, message.message_id, context)
    threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()

# Other Moderation Settings
@bot.message_handler(commands=['antispam_on', 'antispam_off', 'antispam_set', 'antinsfw_on', 'antinsfw_off', 'lock', 'unlock', 'captcha_on', 'captcha_off', 'captcha_set'])
def moderation_settings(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    if message.chat.type == 'private' or not is_creator(bot, chat_id, message.from_user.id):
        sent_message = bot.reply_to(message, "Group mein creator ke roop mein use karo!")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return
    command = message.text.split()[0][1:].lower()
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    try:
        if command == 'antispam_on':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'antispam', json.dumps({'status': 'on', 'sensitivity': 5, 'action': 'delete'})))
            sent_message = bot.reply_to(message, "Anti-spam ON!")
        elif command == 'antispam_off':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'antispam', json.dumps({'status': 'off', 'sensitivity': 5, 'action': 'delete'})))
            sent_message = bot.reply_to(message, "Anti-spam OFF!")
        elif command == 'antispam_set':
            sensitivity = parse_number(message.text.split()[1]) if len(message.text.split()) > 1 else 5
            action = message.text.split()[2] if len(message.text.split()) > 2 and message.text.split()[2] in ['delete', 'warn', 'ban'] else 'delete'
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'antispam', json.dumps({'status': 'on', 'sensitivity': sensitivity, 'action': action})))
            sent_message = bot.reply_to(message, f"Anti-spam set: Sensitivity {sensitivity}, Action {action}")
        elif command == 'antinsfw_on':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'antinsfw', json.dumps({'status': 'on', 'action': 'delete'})))
            sent_message = bot.reply_to(message, "Anti-NSFW scanning ON!")
        elif command == 'antinsfw_off':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'antinsfw', json.dumps({'status': 'off', 'action': 'delete'})))
            sent_message = bot.reply_to(message, "Anti-NSFW scanning OFF!")
        elif command == 'lock':
            lock_type = message.text.split()[1] if len(message.text.split()) > 1 else None
            if lock_type in ['links', 'media', 'stickers', 'forwards']:
                c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                          (chat_id, 'moderation', f'lock_{lock_type}', json.dumps({'status': 'on'})))
                sent_message = bot.reply_to(message, f"{lock_type.capitalize()} locked!")
            else:
                sent_message = bot.reply_to(message, "Use: /lock [links/media/stickers/forwards]")
        elif command == 'unlock':
            lock_type = message.text.split()[1] if len(message.text.split()) > 1 else None
            if lock_type in ['links', 'media', 'stickers', 'forwards']:
                c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                          (chat_id, 'moderation', f'lock_{lock_type}', json.dumps({'status': 'off'})))
                sent_message = bot.reply_to(message, f"{lock_type.capitalize()} unlocked!")
            else:
                sent_message = bot.reply_to(message, "Use: /unlock [links/media/stickers/forwards]")
        elif command == 'captcha_on':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'captcha', json.dumps({'status': 'on', 'type': 'math', 'time': 300})))
            sent_message = bot.reply_to(message, "CAPTCHA ON for new members!")
        elif command == 'captcha_off':
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'captcha', json.dumps({'status': 'off', 'type': 'math', 'time': 300})))
            sent_message = bot.reply_to(message, "CAPTCHA OFF!")
        elif command == 'captcha_set':
            captcha_type = message.text.split()[1] if len(message.text.split()) > 1 and message.text.split()[1] in ['math', 'word'] else 'math'
            time = parse_time(message.text.split()[2]) if len(message.text.split()) > 2 else 300
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', 'captcha', json.dumps({'status': 'on', 'type': captcha_type, 'time': time})))
            sent_message = bot.reply_to(message, f"CAPTCHA set: Type {captcha_type}, Time {time}s")
        conn.commit()
        conn.close()
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    except Exception as e:
        conn.close()
        sent_message = bot.reply_to(message, f"Error: {str(e)}")
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()

# Content Locks
@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'forward'])
def content_handler(message):
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    context = defaultdict(dict)
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    try:
        for lock_type in ['links', 'media', 'stickers', 'forwards']:
            c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', f'lock_{lock_type}'))
            lock = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off'}
            if lock['status'] == 'on':
                if lock_type == 'links' and message.entities and any(e.type == 'url' for e in message.entities):
                    bot.delete_message(chat_id, message.message_id)
                    sent_message = bot.reply_to(message, "Links are locked!")
                    threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
                elif lock_type == 'media' and (message.photo or message.video):
                    bot.delete_message(chat_id, message.message_id)
                    sent_message = bot.reply_to(message, "Media is locked!")
                    threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
                elif lock_type == 'stickers' and message.sticker:
                    bot.delete_message(chat_id, message.message_id)
                    sent_message = bot.reply_to(message, "Stickers are locked!")
                    threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
                elif lock_type == 'forwards' and message.forward_from:
                    bot.delete_message(chat_id, message.message_id)
                    sent_message = bot.reply_to(message, "Forwards are locked!")
                    threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    except Exception as e:
        sent_message = bot.reply_to(message, f"Error: {str(e)}")
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    conn.close()

# CAPTCHA for New Members
@bot.message_handler(content_types=['new_chat_members'])
def new_member_captcha(message):
    chat_id = str(message.chat.id)
    context = defaultdict(dict)
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', 'captcha'))
    captcha = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'type': 'math', 'time': 300}
    if captcha['status'] == 'on':
        for user in message.new_chat_members:
            user_id = str(user.id)
            username = user.username or str(user_id)
            if captcha['type'] == 'math':
                num1, num2 = random.randint(1, 10), random.randint(1, 10)
                answer = num1 + num2
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(str(answer), callback_data=f'captcha_{user_id}_{answer}'),
                    types.InlineKeyboardButton(str(answer + 1), callback_data=f'captcha_{user_id}_wrong'),
                    types.InlineKeyboardButton(str(answer - 1), callback_data=f'captcha_{user_id}_wrong')
                )
                sent_message = bot.send_message(chat_id, f"@{username}, solve: {num1} + {num2} = ?", reply_markup=markup)
                bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(seconds=captcha['time']))
                threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id, captcha['time'])).start()
                c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                          (chat_id, 'captcha', user_id, "New member verification", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_response(call):
    chat_id = str(call.message.chat.id)
    context = defaultdict(dict)
    user_id, answer = call.data.split('_')[1:]
    if str(call.from_user.id) == user_id and answer != 'wrong':
        bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=True))
        sent_message = bot.edit_message_text(f"@{call.from_user.username} verified!", chat_id, call.message.message_id)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
    else:
        bot.kick_chat_member(chat_id, user_id)
        sent_message = bot.edit_message_text(f"@{call.from_user.username} failed CAPTCHA!", chat_id, call.message.message_id)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()

# Start Command
@bot.message_handler(commands=['start', 'Start'])
def start(message):
    context = defaultdict(dict)
    chat_id = str(message.chat.id)
    user = message.from_user
    if message.chat.type != 'private':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔧 Open Settings in Private", url=f"t.me/{bot.get_me().username}"))
        sent_message = bot.reply_to(message, "Private mein settings kholo ya group mein commands use karo!", reply_markup=markup)
        delete_previous(bot, chat_id, message.message_id, context)
        threading.Thread(target=delete_after_delay, args=(bot, chat_id, sent_message.message_id)).start()
        return
    text = (f"👋 Hey {user.first_name}, welcome to UltimateBot!\n"
            "🧠 The smartest way to run and grow your Telegram groups!\n"
            "⚡️ Use commands in group or tweak settings here.\n"
            "Add me as admin in your group.")
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔧 Settings Menu", callback_data='main'),
        types.InlineKeyboardButton("➕ Add to Group", url=f"t.me/{bot.get_me().username}?startgroup=true")
    )
    sent_message = bot.reply_to(message, text, reply_markup=markup)
    delete_previous(bot, chat_id, message.message_id, context)
    store_message_id(context, sent_message.message_id)

# Settings Menu
@bot.callback_query_handler(func=lambda call: call.data == 'main')
def settings_menu(call):
    chat_id = str(call.message.chat.id)
    context = defaultdict(dict)
    delete_previous(bot, chat_id, call.message.message_id, context)
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = [
        ("🛡️ Verify", 'verify'), ("👋 Welcome", 'welcome'), ("📬 Auto Response", 'autoresponse'),
        ("⏰ Scheduled", 'scheduled'), ("🔒 Moderation", 'moderation'), ("🧹 Auto Clean", 'autoclean'),
        ("🚫 Block", 'block'), ("🌐 Lang", 'lang'), ("⚙️ Other", 'other')
    ]
    for text, data in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=data))
    sent_message = bot.edit_message_text("Settings Menu:", chat_id, call.message.message_id, reply_markup=markup)
    store_message_id(context, sent_message.message_id)

# Moderation Menu
@bot.callback_query_handler(func=lambda call: call.data.startswith('moderation'))
def moderation_menu(call):
    chat_id = str(call.message.chat.id)
    context = defaultdict(dict)
    if not is_creator(bot, chat_id, call.from_user.id):
        delete_previous(bot, chat_id, call.message.message_id, context)
        sent_message = bot.send_message(chat_id, "Sirf group creator settings access kar sakte hain!")
        store_message_id(context, sent_message.message_id)
        return
    delete_previous(bot, chat_id, call.message.message_id, context)
    data = call.data.split('_')
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()

    if len(data) == 1:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🚫 Anti-Spam", callback_data='moderation_antispam'),
            types.InlineKeyboardButton("🔍 Anti-NSFW", callback_data='moderation_antinsfw'),
            types.InlineKeyboardButton("⚠️ Warns", callback_data='moderation_warns')
        )
        markup.add(
            types.InlineKeyboardButton("👥 Actions", callback_data='moderation_actions'),
            types.InlineKeyboardButton("🔒 Locks", callback_data='moderation_locks'),
            types.InlineKeyboardButton("🛡️ CAPTCHA", callback_data='moderation_captcha')
        )
        markup.add(
            types.InlineKeyboardButton("📜 Logs", callback_data='moderation_logs'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='main')
        )
        sent_message = bot.edit_message_text("Moderation Tools:", chat_id, call.message.message_id, reply_markup=markup)
    elif len(data) == 2:
        tool = data[1]
        c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', tool))
        settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'limit': 3, 'action': 'ban', 'sensitivity': 5, 'type': 'math', 'time': 300}
        status = settings.get('status', 'off')
        buttons = [[types.InlineKeyboardButton(f"{'✅' if status == 'on' else '❌'} {'ON' if status == 'off' else 'OFF'}", callback_data=f'moderation_{tool}_toggle')]]
        if tool == 'antispam' and status == 'on':
            buttons.append([
                types.InlineKeyboardButton("🔢 Sensitivity", callback_data=f'moderation_{tool}_sensitivity'),
                types.InlineKeyboardButton("⚙️ Action", callback_data=f'moderation_{tool}_action')
            ])
        elif tool == 'antinsfw' and status == 'on':
            buttons.append([types.InlineKeyboardButton("⚙️ Action", callback_data=f'moderation_{tool}_action')])
        elif tool == 'warns' and status == 'on':
            buttons.append([
                types.InlineKeyboardButton("🔢 Limit", callback_data=f'moderation_{tool}_setlimit'),
                types.InlineKeyboardButton("⚙️ Action", callback_data=f'moderation_{tool}_action')
            ])
        elif tool == 'actions' and status == 'on':
            buttons.append([
                types.InlineKeyboardButton("🚫 Ban", callback_data=f'moderation_{tool}_ban'),
                types.InlineKeyboardButton("🔇 Mute", callback_data=f'moderation_{tool}_mute'),
                types.InlineKeyboardButton("🦵 Kick", callback_data=f'moderation_{tool}_kick')
            ])
            buttons.append([
                types.InlineKeyboardButton("⏳ Temp Ban", callback_data=f'moderation_{tool}_tempban'),
                types.InlineKeyboardButton("🔇 Temp Mute", callback_data=f'moderation_{tool}_tempmute')
            ])
        elif tool == 'locks' and status == 'on':
            buttons.append([
                types.InlineKeyboardButton("🔗 Links", callback_data=f'moderation_{tool}_links'),
                types.InlineKeyboardButton("📸 Media", callback_data=f'moderation_{tool}_media'),
                types.InlineKeyboardButton("😀 Stickers", callback_data=f'moderation_{tool}_stickers'),
                types.InlineKeyboardButton("📤 Forwards", callback_data=f'moderation_{tool}_forwards')
            ])
        elif tool == 'captcha' and status == 'on':
            buttons.append([
                types.InlineKeyboardButton("📝 Type", callback_data=f'moderation_{tool}_type'),
                types.InlineKeyboardButton("⏰ Time", callback_data=f'moderation_{tool}_time')
            ])
        elif tool == 'logs':
            buttons.append([types.InlineKeyboardButton("📋 View Logs", callback_data=f'moderation_{tool}_view')])
        buttons.append([types.InlineKeyboardButton("⬅️ Back", callback_data='moderation')])
        markup = types.InlineKeyboardMarkup(buttons)
        sent_message = bot.edit_message_text(f"Moderation {tool}:", chat_id, call.message.message_id, reply_markup=markup)
    elif len(data) == 3:
        tool, action = data[1], data[2]
        c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', tool))
        settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'limit': 3, 'action': 'ban', 'sensitivity': 5, 'type': 'math', 'time': 300}
        if action == 'toggle':
            settings['status'] = 'on' if settings['status'] == 'off' else 'off'
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', tool, json.dumps(settings)))
            sent_message = bot.edit_message_text(f"{tool.capitalize()} {'enabled' if settings['status'] == 'on' else 'disabled'}!", chat_id, call.message.message_id)
        elif action == 'sensitivity':
            context['awaiting_input'] = f'moderation_{tool}_sensitivity'
            sent_message = bot.edit_message_text("Send sensitivity (1-10):", chat_id, call.message.message_id)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action == 'setlimit':
            context['awaiting_input'] = f'moderation_{tool}_setlimit'
            sent_message = bot.edit_message_text("Send warn limit (e.g., 3):", chat_id, call.message.message_id)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action == 'action':
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("🚫 Ban", callback_data=f'moderation_{tool}_action_ban'),
                types.InlineKeyboardButton("🔇 Mute", callback_data=f'moderation_{tool}_action_mute'),
                types.InlineKeyboardButton("🦵 Kick", callback_data=f'moderation_{tool}_action_kick')
            )
            markup.add(
                types.InlineKeyboardButton("🗑️ Delete", callback_data=f'moderation_{tool}_action_delete'),
                types.InlineKeyboardButton("⬅️ Back", callback_data=f'moderation_{tool}')
            )
            sent_message = bot.edit_message_text(f"Set action for {tool}:", chat_id, call.message.message_id, reply_markup=markup)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action in ['ban', 'mute', 'kick', 'tempban', 'tempmute']:
            context['awaiting_input'] = f'moderation_{tool}_{action}'
            text = "Send user ID or username (e.g., @username or 123456789):" if action in ['ban', 'mute', 'kick'] else "Send user ID or username and time (e.g., @username 4m):"
            sent_message = bot.edit_message_text(text, chat_id, call.message.message_id)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action in ['links', 'media', 'stickers', 'forwards']:
            c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', f'lock_{action}'))
            lock = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off'}
            lock['status'] = 'on' if lock['status'] == 'off' else 'off'
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', f'lock_{action}', json.dumps(lock)))
            sent_message = bot.edit_message_text(f"{action.capitalize()} {'locked' if lock['status'] == 'on' else 'unlocked'}!", chat_id, call.message.message_id)
        elif action == 'type':
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("📝 Math", callback_data=f'moderation_{tool}_type_math'),
                types.InlineKeyboardButton("🔤 Word", callback_data=f'moderation_{tool}_type_word')
            )
            markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f'moderation_{tool}'))
            sent_message = bot.edit_message_text("Set CAPTCHA type:", chat_id, call.message.message_id, reply_markup=markup)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action == 'time':
            context['awaiting_input'] = f'moderation_{tool}_time'
            sent_message = bot.edit_message_text("Send CAPTCHA time (e.g., 4m 5s):", chat_id, call.message.message_id)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        elif action == 'view':
            page = 1
            limit = 10
            offset = (page - 1) * limit
            c.execute("SELECT action, user_id, reason, timestamp FROM logs WHERE chat_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (chat_id, limit, offset))
            logs = c.fetchall()
            if logs:
                log_text = "\n".join([f"[{t}] {a}: @{u} ({r})" for a, u, r, t in logs])
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("◀️ Previous", callback_data=f'moderation_logs_view_prev_{page}'),
                    types.InlineKeyboardButton("Next ▶️", callback_data=f'moderation_logs_view_next_{page}')
                )
                markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f'moderation_logs'))
                sent_message = bot.edit_message_text(f"Logs Page {page}:\n{log_text}", chat_id, call.message.message_id, reply_markup=markup)
            else:
                sent_message = bot.edit_message_text("No logs found!", chat_id, call.message.message_id)
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data=f'moderation_logs'))
                bot.edit_message_reply_markup(chat_id, sent_message.message_id, reply_markup=markup)
            store_message_id(context, sent_message.message_id)
            conn.close()
            return
        c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                  (chat_id, 'moderation', tool, json.dumps(settings)))
        conn.commit()
        conn.close()
        moderation_menu(call)
    elif len(data) == 4:
        tool, subaction, value = data[1], data[2], data[3]
        c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, 'moderation', tool))
        settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'limit': 3, 'action': 'ban', 'sensitivity': 5, 'type': 'math', 'time': 300}
        if subaction == 'action':
            settings['action'] = value
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', tool, json.dumps(settings)))
            sent_message = bot.edit_message_text(f"Action for {tool} set to {value}!", chat_id, call.message.message_id)
            conn.commit()
        elif subaction == 'type':
            settings['type'] = value
            c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                      (chat_id, 'moderation', tool, json.dumps(settings)))
            sent_message = bot.edit_message_text(f"CAPTCHA type set to {value}!", chat_id, call.message.message_id)
            conn.commit()
        conn.close()
        moderation_menu(call)
    elif len(data) == 5 and data[2] == 'view':
        tool, action, direction, current_page = data[1], data[2], data[3], int(data[4])
        page = current_page + 1 if direction == 'next' else current_page - 1
        if page < 1:
            page = 1
        limit = 10
        offset = (page - 1) * limit
        c.execute("SELECT action, user_id, reason, timestamp FROM logs WHERE chat_id=? ORDER BY timestamp DESC LIMIT ? OFFSET ?", (chat_id, limit, offset))
        logs = c.fetchall()
        if logs:
            log_text = "\n".join([f"[{t}] {a}: @{u} ({r})" for a, u, r, t in logs])
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("◀️ Previous", callback_data=f'moderation_logs_view_prev_{page}'),
                types.InlineKeyboardButton("Next ▶️", callback_data=f'moderation_logs_view_next_{page}')
            )
            markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data='moderation_logs'))
            sent_message = bot.edit_message_text(f"Logs Page {page}:\n{log_text}", chat_id, call.message.message_id, reply_markup=markup)
        else:
            sent_message = bot.edit_message_text(f"No logs on page {page}!", chat_id, call.message.message_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data='moderation_logs'))
            bot.edit_message_reply_markup(chat_id, sent_message.message_id, reply_markup=markup)
        store_message_id(context, sent_message.message_id)
        conn.close()
    store_message_id(context, sent_message.message_id)

# Handle User Inputs
@bot.message_handler(content_types=['text'])
def handle_input(message):
    chat_id = str(message.chat.id)
    user_input = message.text
    context = defaultdict(dict)
    if 'awaiting_input' not in context:
        return
    delete_previous(bot, chat_id, message.message_id, context)
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    try:
        parts = context['awaiting_input'].split('_')
        feature, subfeature, action = parts[0], parts[1], parts[2]
        if feature == 'moderation':
            c.execute("SELECT data FROM settings WHERE chat_id=? AND feature=? AND subfeature=?", (chat_id, feature, subfeature))
            settings = json.loads(c.fetchone()[0]) if c.fetchone() else {'status': 'off', 'limit': 3, 'action': 'ban', 'sensitivity': 5, 'type': 'math', 'time': 300}
            if action == 'sensitivity':
                settings['sensitivity'] = parse_number(user_input)
                sent_message = bot.send_message(chat_id, f"Sensitivity set to {user_input}")
                c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                          (chat_id, feature, subfeature, json.dumps(settings)))
            elif action == 'setlimit':
                settings['limit'] = parse_number(user_input)
                sent_message = bot.send_message(chat_id, f"Warn limit set to {user_input}")
                c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                          (chat_id, feature, subfeature, json.dumps(settings)))
            elif action == 'time':
                settings['time'] = parse_time(user_input)
                sent_message = bot.send_message(chat_id, f"CAPTCHA time set to {user_input}")
                c.execute("INSERT OR REPLACE INTO settings (chat_id, feature, subfeature, data) VALUES (?, ?, ?, ?)",
                          (chat_id, feature, subfeature, json.dumps(settings)))
            elif action in ['ban', 'mute', 'kick', 'tempban', 'tempmute']:
                user_id = user_input.lstrip('@') if user_input.startswith('@') else user_input
                reason = "Manual action via menu"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if action == 'ban':
                    bot.kick_chat_member(chat_id, user_id)
                    sent_message = bot.send_message(chat_id, f"User {user_input} banned!")
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'ban', user_id, reason, timestamp))
                elif action == 'mute':
                    bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False))
                    sent_message = bot.send_message(chat_id, f"User {user_input} muted!")
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'mute', user_id, reason, timestamp))
                elif action == 'kick':
                    bot.kick_chat_member(chat_id, user_id)
                    bot.unban_chat_member(chat_id, user_id)
                    sent_message = bot.send_message(chat_id, f"User {user_input} kicked!")
                    c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                              (chat_id, 'kick', user_id, reason, timestamp))
                elif action in ['tempban', 'tempmute']:
                    parts = user_input.split()
                    user_id = parts[0].lstrip('@') if parts[0].startswith('@') else parts[0]
                    duration = parse_time(parts[1]) if len(parts) > 1 else 3600
                    if action == 'tempban':
                        bot.kick_chat_member(chat_id, user_id, until_date=datetime.now() + timedelta(seconds=duration))
                        sent_message = bot.send_message(chat_id, f"User {user_id} banned for {duration} seconds!")
                        c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                                  (chat_id, 'tempban', user_id, f"{reason} (Duration: {duration}s)", timestamp))
                    elif action == 'tempmute':
                        bot.restrict_chat_member(chat_id, user_id, permissions=types.ChatPermissions(can_send_messages=False), until_date=datetime.now() + timedelta(seconds=duration))
                        sent_message = bot.send_message(chat_id, f"User {user_id} muted for {duration} seconds!")
                        c.execute("INSERT INTO logs (chat_id, action, user_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                                  (chat_id, 'tempmute', user_id, f"{reason} (Duration: {duration}s)", timestamp))
            conn.commit()
            conn.close()
            moderation_menu(types.CallbackQuery(id=str(chat_id), from_user=message.from_user, message=bot.get_chat(chat_id), data=f'moderation_{subfeature}'))
        store_message_id(context, sent_message.message_id)
    except Exception as e:
        conn.close()
        sent_message = bot.send_message(chat_id, f"Error: {str(e)}")
        store_message_id(context, sent_message.message_id)

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
def home():
    return "🤖 Ultimate Bot Live!"

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"https://helliobot.onrender.com/{TOKEN}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)