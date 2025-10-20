from flask import Flask, request
import telebot, os, sqlite3, json, time, random, re
from telebot import types
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Global DB for gban, feds, crypto
global_conn = sqlite3.connect('global.db', check_same_thread=False)
global_conn.execute('CREATE TABLE IF NOT EXISTS gban (user_id INT PRIMARY KEY)')
global_conn.execute('CREATE TABLE IF NOT EXISTS feds (fed_id INT PRIMARY KEY, chats TEXT)')
global_conn.execute('CREATE TABLE IF NOT EXISTS crypto (currency TEXT PRIMARY KEY, price REAL)')
global_conn.commit()

conn = sqlite3.connect('data.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS settings (chat_id INT PRIMARY KEY, data TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS permissions (chat_id INT, command TEXT, allowed TEXT, PRIMARY KEY (chat_id, command))')
conn.execute('CREATE TABLE IF NOT EXISTS users (chat_id INT, user_id INT, warns INT DEFAULT 0, xp INT DEFAULT 0, role TEXT, PRIMARY KEY (chat_id, user_id))')
conn.execute('CREATE TABLE IF NOT EXISTS captcha (chat_id INT, user_id INT, answer TEXT, message_id INT, PRIMARY KEY (chat_id, user_id))')
conn.execute('CREATE TABLE IF NOT EXISTS backups (chat_id INT PRIMARY KEY, data TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS langs (chat_id INT PRIMARY KEY, lang TEXT DEFAULT "en")')
conn.execute('CREATE TABLE IF NOT EXISTS recurring (chat_id INT PRIMARY KEY, messages TEXT)')
conn.execute('CREATE TABLE IF NOT EXISTS staff (chat_id INT PRIMARY KEY, group_id INT)')
conn.commit()

spam_users = defaultdict(lambda: defaultdict(list))

def spam_check(user_id, chat_id):
    settings = get_settings(chat_id)
    if not settings.get('antispam', False): return False
    now = time.time()
    spam_users[chat_id][user_id] = [t for t in spam_users[chat_id].get(user_id, []) if now - t < settings.get('flood_time', 10)]
    spam_users[chat_id][user_id].append(now)
    return len(spam_users[chat_id][user_id]) > settings.get('flood_limit', 5)

def get_settings(chat_id):
    cursor = conn.execute("SELECT data FROM settings WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    return json.loads(row[0]) if row else {}

def save_settings(chat_id, data):
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (chat_id, json.dumps(data)))
    conn.commit()

def get_permission(chat_id, command):
    cursor = conn.execute("SELECT allowed FROM permissions WHERE chat_id=? AND command=?", (chat_id, command))
    row = cursor.fetchone()
    return row[0] if row else 'admins'

def is_allowed(chat_id, user_id, command):
    allowed = get_permission(chat_id, command)
    if allowed == 'everyone': return True
    cursor = conn.execute("SELECT role FROM users WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = cursor.fetchone()
    role = row[0] if row else 'member'
    if allowed == 'role' and role in get_settings(chat_id).get('roles', []): return True
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

def get_lang(chat_id):
    cursor = conn.execute("SELECT lang FROM langs WHERE chat_id=?", (chat_id,))
    row = cursor.fetchone()
    return row[0] if row else 'en'

langs = {
    'en': {
        'welcome': 'Welcome!',
        'banned': 'Banned!',
        'spam': 'SPAMMER BANNED!',
        'rules': 'Rules Set!',
        'lock': 'Locked!',
        'filter': 'Filter Added!',
        'group_only': 'This command works only in groups!',
        'no_perm': 'No permission! '
    },
    'hi': {
        'welcome': 'स्वागत!',
        'banned': 'बैन!',
        'spam': 'स्पैमर बैन!',
        'rules': 'नियम सेट!',
        'lock': 'लॉक!',
        'filter': 'फिल्टर जोड़ा!',
        'group_only': 'यह कमांड केवल ग्रुप में काम करती है!',
        'no_perm': 'कोई अनुमति नहीं!'
    }
}

class Buttons:
    @staticmethod
    def set_perm_option(command):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton('Set to Everyone', callback_data=f'permset_{command}_everyone'))
        markup.add(types.InlineKeyboardButton('Set to Admins', callback_data=f'permset_{command}_admins'))
        return markup

    @staticmethod
    def main():
        markup = types.InlineKeyboardMarkup(row_width=3)
        btns = [
            ('🚫 AntiSpam', 'antispam'), ('👋 Welcome', 'welcome'), ('🔒 Moderation', 'moderation'),
            ('📜 Rules', 'rules'), ('🔐 Locks', 'locks'), ('📝 Notes/Filters', 'notes'),
            ('🚫 Blacklist', 'blacklist'), ('⚠️ Warnings', 'warnings'), ('📌 Pin', 'pin'),
            ('📈 Leveling', 'leveling'), ('🧹 AutoClean', 'autoclean'), ('⚙️ Permissions', 'perms'),
            ('📋 Logs', 'logs'), ('🌐 Federations', 'feds'), ('🔥 GBan', 'gban'),
            ('📂 Backups', 'backups'), ('🔗 Connections', 'connections'), ('🚫 Disable', 'disable'),
            ('🗑️ Purges', 'purges'), ('📄 Restrictions', 'restrictions'), ('🖼️ StickerMode', 'stickermode'),
            ('🏷️ Tags', 'tags'), ('👥 Users', 'users'), ('🌤️ Weather', 'weather'),
            ('📖 Wiki', 'wiki'), ('📹 Youtube', 'youtube'), ('🗜️ Zipping', 'zipping'),
            ('🛡️ AntiNSFW', 'antinsfw'), ('🌙 NightMode', 'nightmode'), ('💬 Goodbye', 'goodbye'),
            ('🔤 Alphabets', 'alphabets'), ('🪙 Crypto', 'crypto'), ('🧠 Roles', 'roles'),
            ('🗣️ Recurring', 'recurring'), ('🕵️ Privacy', 'privacy'), ('📊 Stats', 'stats'),
            ('🛡️ Approve', 'approve'), ('🔍 Checks', 'checks'), ('📢 Staff', 'staff'),
            ('🗨️ Discussion', 'discussion'), ('✨ Magic', 'magic'), ('📏 MaxMsg', 'maxmsg'),
            ('❌ OFF All', 'off')
        ]
        for t, d in btns: markup.add(types.InlineKeyboardButton(t, callback_data=d))
        return markup

    @staticmethod
    def settings(feature):
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(types.InlineKeyboardButton('✅ ON', callback_data=f'{feature}_on'),
                   types.InlineKeyboardButton('❌ OFF', callback_data=f'{feature}_off'),
                   types.InlineKeyboardButton('⚙️ Customize', callback_data=f'{feature}_custom'))
        markup.add(types.InlineKeyboardButton('⬅️ Back', callback_data='main'))
        return markup

    @staticmethod
    def perms():
        markup = types.InlineKeyboardMarkup(row_width=3)
        cmds = ['antispam', 'welcome', 'moderation', 'rules', 'locks', 'notes', 'blacklist', 'warnings', 'pin', 'leveling', 'autoclean', 'feds', 'gban', 'backups', 'connections', 'disable', 'purges', 'restrictions', 'stickermode', 'tags', 'users', 'weather', 'wiki', 'youtube', 'zipping', 'antinsfw', 'nightmode', 'goodbye', 'alphabets', 'crypto', 'roles', 'recurring', 'privacy', 'stats', 'approve', 'checks', 'staff', 'discussion', 'magic', 'maxmsg']
        for cmd in cmds:
            markup.add(types.InlineKeyboardButton(f'⚙️ Set {cmd}', callback_data=f'perm_{cmd}'))
        markup.add(types.InlineKeyboardButton('⬅️ Back', callback_data='main'))
        return markup

    @staticmethod
    def perm_options(command):
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.add(types.InlineKeyboardButton('👑 Admins', callback_data=f'permset_{command}_admins'),
                   types.InlineKeyboardButton('👥 Everyone', callback_data=f'permset_{command}_everyone'),
                   types.InlineKeyboardButton('🧑‍💼 Role', callback_data=f'permset_{command}_role'))
        markup.add(types.InlineKeyboardButton('⬅️ Back', callback_data='perms'))
        return markup

    @staticmethod
    def captcha(user_id, chat_id, question, answers):
        markup = types.InlineKeyboardMarkup(row_width=3)
        random.shuffle(answers)
        for ans in answers:
            markup.add(types.InlineKeyboardButton(str(ans), callback_data=f'captcha_{ans}'))
        return markup

@bot.message_handler(commands=['start', 'settings'])
def start(m):
    lang = get_lang(m.chat.id)
    bot.send_message(m.chat.id, langs[lang]['welcome'] + " 🤖 Ultimate Bot Settings 🎉\nChoose feature:", reply_markup=Buttons.main())

@bot.message_handler(commands=['help'])
def help_cmd(m):
    lang = get_lang(m.chat.id)
    help_text = """
🤖 Ultimate Commands List (Inspired from Rose, GroupHelp, T22 - Easy Use):
/antispam [on/off/limit N/time S] - 🚫 Auto-ban spammers, sub: flood detect, scam filter, crypto alerts.
/welcome [on/off/set text] - 👋 Greet new users, sub: custom msg, rules show.
/captcha [on/off/set quiz] - 🧩 Verify humans, sub: math/quiz tasks.
/ban [reply/reason] - 🔒 Ban user, sub: permanent, with reason.
/mute [reply/time min] - 🔇 Mute, sub: timed, restrict msg.
/kick [reply] - 🦵 Kick, sub: remove but rejoin.
/promote [reply/rights] - 👑 Promote admin, sub: custom rights.
/demote [reply] - 👇 Demote, sub: remove rights.
/rules [on/off/set text] - 📜 Rules, sub: display on join, enforce.
/locks [type on/off] (media/links/stickers/polls/forwards/buttons/channels) - 🔐 Lock content, sub: auto-delete.
/filters [add keyword/regex reply] - 📝 Auto-reply, sub: keywords, regex match.
/notes [add name text] - 📝 Save notes, sub: #name trigger, /get name.
/blacklist [add word/regex] - 🚫 Auto-ban match, sub: words, regex.
/warn [reply/reason] - ⚠️ Warn, sub: track, auto-ban after limit.
/warnlimit [N] - ⚠️ Max warns.
/pin [reply/silent] - 📌 Pin msg, sub: silent pin.
/leveling [on/off] - 📈 XP system, sub: earn per msg, /rank leaderboard.
/autoclean [on/off/types] - 🧹 Delete clutter, sub: joins/leaves/commands/media/topics.
/setlog [channel] - 📋 Log actions.
/setperm [cmd admins/everyone/role] - ⚙️ Permissions, sub: per cmd/role.
/fed [create/join/list/ban] - 🌐 Federations, sub: multi-group ban.
/gban [reply/reason] - 🔥 Global ban, sub: across groups/feds.
/backup [export/import] - 📂 Settings backup, sub: export data, import.
/connect [channel/group] - 🔗 Link channel, sub: post to connected.
/disable [cmd] - 🚫 Disable command.
/purge [reply/from-to] - 🗑️ Delete msgs, sub: from reply to current.
/restrict [reply/read-only] - 📄 Read-only mode.
/stickermode [on/off/delete] - 🖼️ Sticker control, sub: delete stickers.
/tags [all/admins] - 🏷️ Tag all, sub: @all, @admins.
/users [list/stats] - 👥 User list, sub: stats, forget data.
/weather [city] - 🌤️ Weather info.
/wiki [query] - 📖 Wiki search.
/youtube [url/search] - 📹 Download/search video.
/zip [reply/files] - 🗜️ Zip files.
/antinsfw [on/off/sensitivity] - 🛡️ Anti-NSFW filter.
/nightmode [on/off/time] - 🌙 Auto-mute night.
/goodbye [on/off/set text] - 💬 Farewell msg.
/alphabets [on/off/lang] - 🔤 Anti-non-English.
/crypto [currency/price/alert] - 🪙 Crypto prices, sub: alerts, buy bot.
/lang [en/hi/set] - 🌍 Set language.
/roles [create/set hierarchy/assign] - 🧠 Roles, sub: custom, hierarchy.
/recurring [add msg/time] - 🗣️ Repeating msgs.
/privacy [on/off/mode] - 🕵️ User privacy, sub: data control.
/stats [group/user] - 📊 Group stats.
/approve [on/off/mode] - 🛡️ Approve msgs.
/checks [on/off/types] - 🔍 Checks settings.
/staff [set group] - 📢 Staff group.
/discussion [set group] - 🗨️ Discussion link.
/magic [stickers/gifs on/off] - ✨ Magic stickers/GIFs.
/maxmsg [limit N] - 📏 Max msg length.
/raid [tweet incentives] - ⚡ X Raid tool, sub: likes/reposts/replies/bookmarks.
/off - ❌ OFF all.
/help - This list.
    """
    bot.send_message(m.chat.id, help_text)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    chat_id = c.message.chat.id
    if not is_allowed(chat_id, c.from_user.id, 'settings'):
        bot.answer_callback_query(c.id, "Not allowed!")
        return
    data = c.data
    settings = get_settings(chat_id)
    
    if data == 'main':
        bot.edit_message_text("Choose feature:", chat_id, c.message.message_id, reply_markup=Buttons.main())
    elif data in ['antispam', 'welcome', 'moderation', 'rules', 'locks', 'notes', 'blacklist', 'warnings', 'pin', 'leveling', 'autoclean', 'perms', 'logs', 'feds', 'gban', 'backups', 'connections', 'disable', 'purges', 'restrictions', 'stickermode', 'tags', 'users', 'weather', 'wiki', 'youtube', 'zipping', 'antinsfw', 'nightmode', 'goodbye', 'alphabets', 'crypto', 'roles', 'recurring', 'privacy', 'stats', 'approve', 'checks', 'staff', 'discussion', 'magic', 'maxmsg']:
        bot.edit_message_text(f"Set {data}:", chat_id, c.message.message_id, reply_markup=Buttons.settings(data))
    elif data == 'perms':
        bot.edit_message_text("Set Permissions:", chat_id, c.message.message_id, reply_markup=Buttons.perms())
    elif data.startswith('perm_'):
        command = data.split('_')[1]
        bot.edit_message_text(f"Set for {command}:", chat_id, c.message.message_id, reply_markup=Buttons.perm_options(command))
    elif data.startswith('permset_'):
        parts = data.split('_')
        command, level = parts[1], parts[2]
        conn.execute("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?)", (chat_id, command, level))
        conn.commit()
        bot.answer_callback_query(c.id, f"{command} set to {level}!")
        bot.edit_message_text("Updated!", chat_id, c.message.message_id, reply_markup=Buttons.perms())
    elif data.endswith('_on') or data.endswith('_off'):
        feature = data.split('_')[0]
        settings[feature] = data.endswith('_on')
        save_settings(chat_id, settings)
        bot.answer_callback_query(c.id, f"{feature} {'ON' if settings[feature] else 'OFF'}!")
    elif data.endswith('_custom'):
        feature = data.split('_')[0]
        bot.answer_callback_query(c.id, f"Use /{feature} [options] for custom!")
    elif data == 'off':
        for key in list(settings.keys()):
            if isinstance(settings[key], bool): settings[key] = False
        save_settings(chat_id, settings)
        bot.answer_callback_query(c.id, "All OFF!")
    elif data.startswith('captcha_'):
        answer = data.split('_')[1]
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

# Handlers for all features
@bot.message_handler(commands=['antispam'])
def antispam_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'antispam'):
        markup = Buttons.set_perm_option('antispam')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['antispam'] = True
        elif args[0] == 'off': settings['antispam'] = False
        elif args[0] == 'limit' and len(args) > 1: settings['flood_limit'] = int(args[1])
        elif args[0] == 'time' and len(args) > 1: settings['flood_time'] = int(args[1])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🚫 AntiSpam: {settings.get('antispam', False)}, Limit: {settings.get('flood_limit', 5)}, Time: {settings.get('flood_time', 10)}s")

@bot.message_handler(commands=['welcome'])
def welcome_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'welcome'):
        markup = Buttons.set_perm_option('welcome')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['welcome'] = True
        elif args[0] == 'off': settings['welcome'] = False
        elif args[0] == 'set': settings['welcome_text'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"👋 Welcome: {settings.get('welcome', False)}, Text: {settings.get('welcome_text', 'Welcome to the group!')}")

@bot.message_handler(commands=['captcha'])
def captcha_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'captcha'):
        markup = Buttons.set_perm_option('captcha')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['captcha'] = True
        elif args[0] == 'off': settings['captcha'] = False
        elif args[0] == 'set': settings['captcha_quiz'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🧩 Captcha: {settings.get('captcha', False)}, Quiz: {settings.get('captcha_quiz', 'Default math')}")

@bot.message_handler(commands=['ban'])
def ban_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'moderation'):
        markup = Buttons.set_perm_option('moderation')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        reason = ' '.join(m.text.split()[1:]) if len(m.text.split()) > 1 else ''
        bot.ban_chat_member(m.chat.id, user_id)
        bot.reply_to(m, langs[get_lang(m.chat.id)]['banned'] + reason)
        send_log(m.chat.id, f"User {user_id} banned by {m.from_user.id} {reason}")

@bot.message_handler(commands=['mute'])
def mute_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'moderation'):
        markup = Buttons.set_perm_option('moderation')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        until = None
        args = m.text.split()[1:]
        if args and args[0].isdigit(): until = time.time() + int(args[0]) * 60
        bot.restrict_chat_member(m.chat.id, user_id, until_date=until, can_send_messages=False)
        bot.reply_to(m, "🔇 User Muted!")
        send_log(m.chat.id, f"User {user_id} muted by {m.from_user.id}")

@bot.message_handler(commands=['kick'])
def kick_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'moderation'):
        markup = Buttons.set_perm_option('moderation')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.ban_chat_member(m.chat.id, user_id)
        bot.unban_chat_member(m.chat.id, user_id)
        bot.reply_to(m, "🦵 User Kicked!")
        send_log(m.chat.id, f"User {user_id} kicked by {m.from_user.id}")

@bot.message_handler(commands=['promote'])
def promote_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'moderation'):
        markup = Buttons.set_perm_option('moderation')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.promote_chat_member(m.chat.id, user_id, can_change_info=True, can_post_messages=True, can_edit_messages=True, can_delete_messages=True, can_invite_users=True, can_restrict_members=True, can_pin_messages=True, can_promote_members=False)
        bot.reply_to(m, "👑 User Promoted!")
        send_log(m.chat.id, f"User {user_id} promoted by {m.from_user.id}")

@bot.message_handler(commands=['demote'])
def demote_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'moderation'):
        markup = Buttons.set_perm_option('moderation')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.promote_chat_member(m.chat.id, user_id, can_change_info=False, can_post_messages=False, can_edit_messages=False, can_delete_messages=False, can_invite_users=False, can_restrict_members=False, can_pin_messages=False, can_promote_members=False)
        bot.reply_to(m, "👇 User Demoted!")
        send_log(m.chat.id, f"User {user_id} demoted by {m.from_user.id}")

@bot.message_handler(commands=['rules'])
def rules_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'rules'):
        markup = Buttons.set_perm_option('rules')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    settings = get_settings(m.chat.id)
    if len(m.text.split()) > 1:
        args = m.text.split()[1:]
        if args[0] == 'on': settings['rules'] = True
        elif args[0] == 'off': settings['rules'] = False
        elif args[0] == 'set': settings['rules_text'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"📜 Rules: {settings.get('rules_text', 'No rules set.')}")

@bot.message_handler(commands=['locks'])
def locks_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'locks'):
        markup = Buttons.set_perm_option('locks')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if len(args) < 2: return bot.reply_to(m, "Usage: /locks [type] [on/off] (types: media, links, stickers, polls, forwards, buttons, channels)")
    lock_type, state = args[0], args[1] == 'on'
    settings = get_settings(m.chat.id)
    settings[f'lock_{lock_type}'] = state
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🔐 Lock {lock_type}: {state}")

@bot.message_handler(commands=['filters'])
def filters_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'notes'):
        markup = Buttons.set_perm_option('notes')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if len(args) < 3 or args[0] != 'add': return bot.reply_to(m, "Usage: /filters add [keyword/regex:] [reply_text]")
    keyword = args[1]
    reply_text = ' '.join(args[2:])
    settings = get_settings(m.chat.id)
    if 'filters' not in settings: settings['filters'] = {}
    settings['filters'][keyword] = reply_text
    save_settings(m.chat.id, settings)
    bot.reply_to(m, langs[get_lang(m.chat.id)]['filter'] + keyword)

@bot.message_handler(commands=['notes'])
def notes_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'notes'):
        markup = Buttons.set_perm_option('notes')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if len(args) < 3 or args[0] != 'add': return bot.reply_to(m, "Usage: /notes add [name] [text]")
    name, text = args[1], ' '.join(args[2:])
    settings = get_settings(m.chat.id)
    if 'notes' not in settings: settings['notes'] = {}
    settings['notes'][name] = text
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"📝 Note {name} added")

@bot.message_handler(commands=['get'])
def get_note_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'notes'):
        markup = Buttons.set_perm_option('notes')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if not args: return
    name = args[0]
    settings = get_settings(m.chat.id)
    text = settings.get('notes', {}).get(name)
    if text: bot.reply_to(m, text)

@bot.message_handler(commands=['blacklist'])
def blacklist_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'blacklist'):
        markup = Buttons.set_perm_option('blacklist')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if len(args) < 2 or args[0] != 'add': return bot.reply_to(m, "Usage: /blacklist add [word/regex:]")
    word = args[1]
    settings = get_settings(m.chat.id)
    if 'blacklist' not in settings: settings['blacklist'] = []
    settings['blacklist'].append(word)
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🚫 Blacklist added: {word}")

@bot.message_handler(commands=['warn'])
def warn_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'warnings'):
        markup = Buttons.set_perm_option('warnings')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        warns = add_warn(m.chat.id, user_id)
        max_warns = get_settings(m.chat.id).get('warn_limit', 3)
        bot.reply_to(m, f"⚠️ User warned ({warns}/{max_warns})!")
        send_log(m.chat.id, f"User {user_id} warned ({warns}/{max_warns})")
        if warns >= max_warns:
            bot.ban_chat_member(m.chat.id, user_id)
            bot.send_message(m.chat.id, "User banned for max warns!")

@bot.message_handler(commands=['warnlimit'])
def warnlimit_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'warnings'):
        markup = Buttons.set_perm_option('warnings')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['warn_limit'] = int(args[0])
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"⚠️ Warn limit set to {args[0]}")

@bot.message_handler(commands=['pin'])
def pin_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'pin'):
        markup = Buttons.set_perm_option('pin')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        silent = 'silent' in m.text
        bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id, disable_notification=silent)
        bot.reply_to(m, "📌 Message Pinned!")
        send_log(m.chat.id, f"Message pinned (silent: {silent})")

@bot.message_handler(commands=['leveling'])
def leveling_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'leveling'):
        markup = Buttons.set_perm_option('leveling')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['leveling'] = True
        elif args[0] == 'off': settings['leveling'] = False
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"📈 Leveling: {settings.get('leveling', False)}")

@bot.message_handler(commands=['rank'])
def rank_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'leveling'):
        markup = Buttons.set_perm_option('leveling')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    cursor = conn.execute("SELECT user_id, xp FROM users WHERE chat_id=? ORDER BY xp DESC LIMIT 10", (m.chat.id,))
    ranks = cursor.fetchall()
    text = "📈 Leaderboard:\n"
    for i, (uid, xp) in enumerate(ranks, 1):
        user = bot.get_chat_member(m.chat.id, uid).user
        text += f"{i}. {user.first_name} - {xp} XP\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(commands=['autoclean'])
def autoclean_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'autoclean'):
        markup = Buttons.set_perm_option('autoclean')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['autoclean'] = True
        elif args[0] == 'off': settings['autoclean'] = False
        elif args[0] == 'types': settings['autoclean_types'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🧹 AutoClean: {settings.get('autoclean', False)}, Types: {settings.get('autoclean_types', 'joins leaves commands media topics')}")

@bot.message_handler(commands=['setlog'])
def setlog_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'logs'):
        markup = Buttons.set_perm_option('logs')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['log_channel'] = args[0]
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"📋 Log channel set to {args[0]}")

@bot.message_handler(commands=['setperm'])
def setperm_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'perms'):
        markup = Buttons.set_perm_option('perms')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if len(args) < 2: return bot.reply_to(m, "Usage: /setperm [command] [admins/everyone/role]")
    command, level = args[0], args[1]
    conn.execute("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?)", (m.chat.id, command, level))
    conn.commit()
    bot.reply_to(m, f"⚙️ {command} set to {level}")

@bot.message_handler(commands=['fed'])
def fed_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'feds'):
        markup = Buttons.set_perm_option('feds')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if not args: return bot.reply_to(m, "Usage: /fed [create/join/list/ban]")
    if args[0] == 'create':
        fed_id = random.randint(1, 10000)
        global_conn.execute("INSERT INTO feds VALUES (?, ?)", (fed_id, json.dumps([m.chat.id])))
        global_conn.commit()
        bot.reply_to(m, f"🌐 Fed created: {fed_id}")
    elif args[0] == 'join' and len(args) > 1:
        fed_id = int(args[1])
        cursor = global_conn.execute("SELECT chats FROM feds WHERE fed_id=?", (fed_id,))
        row = cursor.fetchone()
        if row:
            chats = json.loads(row[0])
            chats.append(m.chat.id)
            global_conn.execute("UPDATE feds SET chats=? WHERE fed_id=?", (json.dumps(chats), fed_id))
            global_conn.commit()
            bot.reply_to(m, f"🌐 Joined fed {fed_id}")
    elif args[0] == 'list':
        cursor = global_conn.execute("SELECT fed_id, chats FROM feds")
        text = "🌐 Feds:\n"
        for fed_id, chats in cursor.fetchall():
            text += f"{fed_id}: {json.loads(chats)}\n"
        bot.reply_to(m, text)
    elif args[0] == 'ban' and m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        cursor = global_conn.execute("SELECT chats FROM feds WHERE fed_id IN (SELECT fed_id FROM feds WHERE chats LIKE ?)", (f"%{m.chat.id}%",))
        for row in cursor.fetchall():
            for chat in json.loads(row[0]):
                bot.ban_chat_member(chat, user_id)
        bot.reply_to(m, "🌐 Fed ban applied!")

@bot.message_handler(commands=['gban'])
def gban_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'gban'):
        markup = Buttons.set_perm_option('gban')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        reason = ' '.join(m.text.split()[1:]) if len(m.text.split()) > 1 else ''
        global_conn.execute("INSERT OR REPLACE INTO gban VALUES (?)", (user_id,))
        global_conn.commit()
        cursor = conn.execute("SELECT chat_id FROM settings")
        for (chat,) in cursor.fetchall():
            bot.ban_chat_member(chat, user_id)
        bot.reply_to(m, "🔥 GBanned " + reason)

@bot.message_handler(commands=['backup'])
def backup_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'backups'):
        markup = Buttons.set_perm_option('backups')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if not args: return bot.reply_to(m, "Usage: /backup [export/import]")
    if args[0] == 'export':
        data = get_settings(m.chat.id)
        conn.execute("INSERT OR REPLACE INTO backups VALUES (?, ?)", (m.chat.id, json.dumps(data)))
        conn.commit()
        bot.reply_to(m, "📂 Backup exported!")
    elif args[0] == 'import' and m.reply_to_message and m.reply_to_message.text:
        data = json.loads(m.reply_to_message.text)
        save_settings(m.chat.id, data)
        bot.reply_to(m, "📂 Backup imported!")

@bot.message_handler(commands=['connect'])
def connect_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'connections'):
        markup = Buttons.set_perm_option('connections')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['connected'] = args[0]
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"🔗 Connected to {args[0]}")

@bot.message_handler(commands=['disable'])
def disable_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'disable'):
        markup = Buttons.set_perm_option('disable')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        if 'disabled' not in settings: settings['disabled'] = []
        settings['disabled'].append(args[0])
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"🚫 Disabled {args[0]}")

@bot.message_handler(commands=['purge'])
def purge_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'purges'):
        markup = Buttons.set_perm_option('purges')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        from_id = m.reply_to_message.message_id
        to_id = m.message_id
        for msg_id in range(from_id, to_id + 1):
            bot.delete_message(m.chat.id, msg_id)
        bot.reply_to(m, "🗑️ Purged!")

@bot.message_handler(commands=['restrict'])
def restrict_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'restrictions'):
        markup = Buttons.set_perm_option('restrictions')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        bot.restrict_chat_member(m.chat.id, user_id, can_send_messages=False)
        bot.reply_to(m, "📄 User Restricted!")

@bot.message_handler(commands=['stickermode'])
def stickermode_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'stickermode'):
        markup = Buttons.set_perm_option('stickermode')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['stickermode'] = True
        elif args[0] == 'off': settings['stickermode'] = False
        elif args[0] == 'delete': settings['sticker_delete'] = True
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🖼️ StickerMode: {settings.get('stickermode', False)}")

@bot.message_handler(commands=['tags'])
def tags_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'tags'):
        markup = Buttons.set_perm_option('tags')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    text = ""
    if args and args[0] == 'all':
        cursor = conn.execute("SELECT user_id FROM users WHERE chat_id=?", (m.chat.id,))
        for (uid,) in cursor.fetchall():
            user = bot.get_chat_member(m.chat.id, uid).user
            text += f"@{user.username} " if user.username else ""
        bot.reply_to(m, text + "🏷️ Tagged all!" if text else "No users to tag!")
    elif args and args[0] == 'admins':
        admins = bot.get_chat_administrators(m.chat.id)
        for admin in admins:
            text += f"@{admin.user.username} " if admin.user.username else ""
        bot.reply_to(m, text + "🏷️ Tagged admins!" if text else "No admins to tag!")

@bot.message_handler(commands=['users'])
def users_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'users'):
        markup = Buttons.set_perm_option('users')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    cursor = conn.execute("SELECT user_id FROM users WHERE chat_id=?", (m.chat.id,))
    text = "👥 Users:\n"
    for (uid,) in cursor.fetchall():
        user = bot.get_chat_member(m.chat.id, uid).user
        text += f"{user.first_name} ({uid})\n"
    bot.reply_to(m, text if text != "👥 Users:\n" else "No users found!")

@bot.message_handler(commands=['weather'])
def weather_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'weather'):
        markup = Buttons.set_perm_option('weather')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        # Placeholder for API, use browse or web_search in real
        bot.reply_to(m, f"🌤️ Weather in {args[0]}: Sunny, 25°C (placeholder)")

@bot.message_handler(commands=['wiki'])
def wiki_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'wiki'):
        markup = Buttons.set_perm_option('wiki')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        # Placeholder, use web_search
        bot.reply_to(m, f"📖 Wiki for {' '.join(args)}: Summary (placeholder)")

@bot.message_handler(commands=['youtube'])
def youtube_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'youtube'):
        markup = Buttons.set_perm_option('youtube')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        # Placeholder for download/search
        bot.reply_to(m, f"📹 Youtube {' '.join(args)}: Link (placeholder)")

@bot.message_handler(commands=['zip'])
def zip_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'zipping'):
        markup = Buttons.set_perm_option('zipping')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    if m.reply_to_message and m.reply_to_message.document:
        # Placeholder for zipping
        bot.reply_to(m, "🗜️ Zipped file (placeholder)")

@bot.message_handler(commands=['antinsfw'])
def antinsfw_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'antinsfw'):
        markup = Buttons.set_perm_option('antinsfw')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['antinsfw'] = True
        elif args[0] == 'off': settings['antinsfw'] = False
        elif args[0] == 'sensitivity': settings['nsfw_sensitivity'] = int(args[1])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🛡️ AntiNSFW: {settings.get('antinsfw', False)}, Sensitivity: {settings.get('nsfw_sensitivity', 50)}")

@bot.message_handler(commands=['nightmode'])
def nightmode_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'nightmode'):
        markup = Buttons.set_perm_option('nightmode')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['nightmode'] = True
        elif args[0] == 'off': settings['nightmode'] = False
        elif args[0] == 'time': settings['night_time'] = args[1]
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🌙 NightMode: {settings.get('nightmode', False)}, Time: {settings.get('night_time', '00:00-06:00')}")

@bot.message_handler(commands=['goodbye'])
def goodbye_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'goodbye'):
        markup = Buttons.set_perm_option('goodbye')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['goodbye'] = True
        elif args[0] == 'off': settings['goodbye'] = False
        elif args[0] == 'set': settings['goodbye_text'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"💬 Goodbye: {settings.get('goodbye', False)}, Text: {settings.get('goodbye_text', 'Goodbye!')}")

@bot.message_handler(commands=['alphabets'])
def alphabets_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'alphabets'):
        markup = Buttons.set_perm_option('alphabets')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['alphabets'] = True
        elif args[0] == 'off': settings['alphabets'] = False
        elif args[0] == 'lang': settings['alphabet_lang'] = args[1]
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🔤 Alphabets: {settings.get('alphabets', False)}, Lang: {settings.get('alphabet_lang', 'en')}")

@bot.message_handler(commands=['crypto'])
def crypto_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'crypto'):
        markup = Buttons.set_perm_option('crypto')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        currency = args[0]
        # Placeholder for price, use web_search in real
        price = random.uniform(1000, 50000)  # Placeholder
        global_conn.execute("INSERT OR REPLACE INTO crypto VALUES (?, ?)", (currency, price))
        global_conn.commit()
        bot.reply_to(m, f"🪙 {currency}: ${price}")
        if args[0] == 'alert' and len(args) > 1: 
            settings = get_settings(m.chat.id)
            settings['crypto_alert'] = args[1]
            save_settings(m.chat.id, settings)
            bot.reply_to(m, "🪙 Crypto alert set!")

@bot.message_handler(commands=['lang'])
def lang_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'langs'):
        markup = Buttons.set_perm_option('langs')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        lang = args[0]
        conn.execute("INSERT OR REPLACE INTO langs VALUES (?, ?)", (m.chat.id, lang))
        conn.commit()
        bot.reply_to(m, f"🌍 Language set to {lang}")

@bot.message_handler(commands=['roles'])
def roles_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'roles'):
        markup = Buttons.set_perm_option('roles')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if 'roles' not in settings: settings['roles'] = {}
    if args and args[0] == 'create':
        settings['roles'][args[1]] = args[2:]  # hierarchy/permissions
    elif args and args[0] == 'assign' and m.reply_to_message:
        user_id = m.reply_to_message.from_user.id
        role = args[1]
        conn.execute("UPDATE users SET role=? WHERE chat_id=? AND user_id=?", (role, m.chat.id, user_id))
        conn.commit()
    save_settings(m.chat.id, settings)
    bot.reply_to(m, "🧠 Role managed!")

@bot.message_handler(commands=['recurring'])
def recurring_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'recurring'):
        markup = Buttons.set_perm_option('recurring')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args and args[0] == 'add':
        msg = ' '.join(args[2:])
        time_interval = int(args[1])
        cursor = conn.execute("SELECT messages FROM recurring WHERE chat_id=?", (m.chat.id,))
        row = cursor.fetchone()
        msgs = json.loads(row[0]) if row else []
        msgs.append({'msg': msg, 'time': time_interval})
        conn.execute("INSERT OR REPLACE INTO recurring VALUES (?, ?)", (m.chat.id, json.dumps(msgs)))
        conn.commit()
        bot.reply_to(m, "🗣️ Recurring msg added!")

@bot.message_handler(commands=['privacy'])
def privacy_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'privacy'):
        markup = Buttons.set_perm_option('privacy')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['privacy'] = True
        elif args[0] == 'off': settings['privacy'] = False
        elif args[0] == 'mode': settings['privacy_mode'] = args[1]
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🕵️ Privacy: {settings.get('privacy', False)}, Mode: {settings.get('privacy_mode', 'default')}")

@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'stats'):
        markup = Buttons.set_perm_option('stats')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    cursor = conn.execute("SELECT COUNT(*) FROM users WHERE chat_id=?", (m.chat.id,))
    users = cursor.fetchone()[0]
    bot.reply_to(m, f"📊 Group Stats: {users} users")

@bot.message_handler(commands=['approve'])
def approve_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'approve'):
        markup = Buttons.set_perm_option('approve')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['approve'] = True
        elif args[0] == 'off': settings['approve'] = False
        elif args[0] == 'mode': settings['approve_mode'] = args[1]
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🛡️ Approve: {settings.get('approve', False)}, Mode: {settings.get('approve_mode', 'manual')}")

@bot.message_handler(commands=['checks'])
def checks_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'checks'):
        markup = Buttons.set_perm_option('checks')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['checks'] = True
        elif args[0] == 'off': settings['checks'] = False
        elif args[0] == 'types': settings['checks_types'] = ' '.join(args[1:])
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"🔍 Checks: {settings.get('checks', False)}, Types: {settings.get('checks_types', 'default')}")

@bot.message_handler(commands=['staff'])
def staff_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'staff'):
        markup = Buttons.set_perm_option('staff')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args and args[0] == 'set':
        group_id = args[1]
        conn.execute("INSERT OR REPLACE INTO staff VALUES (?, ?)", (m.chat.id, group_id))
        conn.commit()
        bot.reply_to(m, f"📢 Staff group set to {group_id}")

@bot.message_handler(commands=['discussion'])
def discussion_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'discussion'):
        markup = Buttons.set_perm_option('discussion')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args and args[0] == 'set':
        group_id = args[1]
        settings = get_settings(m.chat.id)
        settings['discussion'] = group_id
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"🗨️ Discussion set to {group_id}")

@bot.message_handler(commands=['magic'])
def magic_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'magic'):
        markup = Buttons.set_perm_option('magic')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    settings = get_settings(m.chat.id)
    if args:
        if args[0] == 'on': settings['magic'] = True
        elif args[0] == 'off': settings['magic'] = False
    save_settings(m.chat.id, settings)
    bot.reply_to(m, f"✨ Magic Stickers/GIFs: {settings.get('magic', False)}")

@bot.message_handler(commands=['maxmsg'])
def maxmsg_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'maxmsg'):
        markup = Buttons.set_perm_option('maxmsg')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        settings = get_settings(m.chat.id)
        settings['max_msg'] = int(args[0])
        save_settings(m.chat.id, settings)
        bot.reply_to(m, f"📏 Max Msg Length: {args[0]}")

@bot.message_handler(commands=['raid'])
def raid_cmd(m):
    if m.chat.type not in ['group', 'supergroup']:
        bot.reply_to(m, langs[get_lang(m.chat.id)]['group_only'])
        return
    if not is_allowed(m.chat.id, m.from_user.id, 'raid'):
        markup = Buttons.set_perm_option('raid')
        bot.reply_to(m, langs[get_lang(m.chat.id)]['no_perm'] + " Set permission:", reply_markup=markup)
        return
    args = m.text.split()[1:]
    if args:
        tweet = args[0]
        incentives = ' '.join(args[1:])
        # Placeholder for raid, notify members
        bot.send_message(m.chat.id, f"⚡ Raid on {tweet}! Incentives: {incentives} - Like, Repost, Reply, Bookmark!")

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(m):
    chat_id = m.chat.id
    settings = get_settings(chat_id)
    for member in m.new_chat_members:
        user_id = member.id
        cursor = global_conn.execute("SELECT * FROM gban WHERE user_id=?", (user_id,))
        if cursor.fetchone():
            bot.ban_chat_member(chat_id, user_id)
            bot.send_message(chat_id, "🔥 GBanned user tried to join!")
            return
        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
        if settings.get('welcome', False):
            text = settings.get('welcome_text', 'Welcome to the group!') + "\n" + settings.get('rules_text', '')
            bot.send_message(chat_id, text)
        if settings.get('captcha', False):
            question = settings.get('captcha_quiz', 'What is 2+2?')
            answers = ['4', random.choice(['3', '5', '6']), random.choice(['1', '7', '8'])]
            answer = '4'
            msg = bot.send_message(chat_id, question, reply_markup=Buttons.captcha(user_id, chat_id, question, answers))
            conn.execute("INSERT OR REPLACE INTO captcha VALUES (?, ?, ?, ?)", (chat_id, user_id, answer, msg.message_id))
            conn.commit()
        send_log(chat_id, f"New member {user_id}")

@bot.message_handler(content_types=['left_chat_member'])
def handle_left(m):
    settings = get_settings(m.chat.id)
    if settings.get('goodbye', False):
        text = settings.get('goodbye_text', 'Goodbye!')
        bot.send_message(m.chat.id, text)
    if settings.get('autoclean', False):
        bot.delete_message(m.chat.id, m.message_id)

@bot.message_handler(func=lambda m: True)
def handle_messages(m):
    chat_id = m.chat.id
    user_id = m.from_user.id if m.from_user else None
    settings = get_settings(chat_id)
    text = m.text.lower() if m.text else ''
    
    if user_id:
        if settings.get('leveling', False) and not m.text.startswith('/'):
            add_xp(chat_id, user_id)
        
        if settings.get('antispam', False) and spam_check(user_id, chat_id):
            bot.ban_chat_member(chat_id, user_id)
            bot.send_message(chat_id, langs[get_lang(chat_id)]['spam'])
            send_log(chat_id, f"Spammer {user_id} banned")
            return
    
    if settings.get('autoclean', False) and m.content_type in settings.get('autoclean_types', ['new_chat_members', 'left_chat_member', 'pinned_message']) or m.from_user is None:
        bot.delete_message(chat_id, m.message_id)
    
    if 'blacklist' in settings and text:
        for pattern in settings['blacklist']:
            if re.search(pattern if pattern.startswith('regex:') else pattern, text, re.IGNORECASE):
                bot.delete_message(chat_id, m.message_id)
                bot.ban_chat_member(chat_id, user_id)
                bot.send_message(chat_id, "🚫 Blacklisted! Banned.")
                send_log(chat_id, f"User {user_id} banned for blacklist match: {pattern}")
                return
    
    if 'filters' in settings and text:
        for keyword, reply in settings['filters'].items():
            if keyword.startswith('regex:'):
                if re.search(keyword[6:], text, re.IGNORECASE):
                    bot.reply_to(m, reply)
            elif keyword.lower() in text:
                bot.reply_to(m, reply)
    
    if settings.get('locks', False):
        lock_types = ['media', 'links', 'stickers', 'polls', 'forwards', 'buttons', 'channels']
        for lock in lock_types:
            if settings.get(f'lock_{lock}', False):
                if (lock == 'media' and m.content_type in ['photo', 'video', 'audio', 'document']) or \
                   (lock == 'links' and m.entities and any(e.type in ['url', 'text_link'] for e in m.entities)) or \
                   (lock == 'stickers' and m.content_type == 'sticker') or \
                   (lock == 'polls' and m.content_type == 'poll') or \
                   (lock == 'forwards' and m.forward_from or m.forward_from_chat) or \
                   (lock == 'buttons' and m.reply_markup) or \
                   (lock == 'channels' and m.forward_from_chat and m.forward_from_chat.type == 'channel'):
                    bot.delete_message(chat_id, m.message_id)
                    bot.send_message(chat_id, f"🔐 {lock.capitalize()} locked!")
                    send_log(chat_id, f"Message deleted for {lock} lock by {user_id}")
                    return

    if settings.get('stickermode', False) and m.content_type == 'sticker' and settings.get('sticker_delete', False):
        bot.delete_message(chat_id, m.message_id)
        bot.send_message(chat_id, "🖼️ Sticker deleted!")
        send_log(chat_id, f"Sticker deleted by {user_id}")

    if settings.get('antinsfw', False) and m.content_type in ['photo', 'video']:
        # Placeholder for NSFW detection (use AI model or API in real implementation)
        nsfw_score = random.uniform(0, 100)  # Placeholder
        if nsfw_score > settings.get('nsfw_sensitivity', 50):
            bot.delete_message(chat_id, m.message_id)
            bot.send_message(chat_id, "🛡️ NSFW content detected and deleted!")
            send_log(chat_id, f"NSFW content deleted from {user_id}")

    if settings.get('alphabets', False) and text:
        allowed_lang = settings.get('alphabet_lang', 'en')
        # Placeholder for non-allowed language detection
        is_non_english = not all(ord(c) < 128 for c in text) if allowed_lang == 'en' else False
        if is_non_english:
            bot.delete_message(chat_id, m.message_id)
            bot.send_message(chat_id, f"🔤 Only {allowed_lang} allowed!")
            send_log(chat_id, f"Non-{allowed_lang} message deleted from {user_id}")

    if settings.get('max_msg', 0) and text and len(text) > settings['max_msg']:
        bot.delete_message(chat_id, m.message_id)
        bot.send_message(chat_id, f"📏 Message too long! Max {settings['max_msg']} characters.")
        send_log(chat_id, f"Long message deleted from {user_id}")

    if settings.get('nightmode', False):
        from datetime import datetime
        import re
        night_time = settings.get('night_time', '00:00-06:00')
        start, end = re.match(r'(\d+:\d+)-(\d+:\d+)', night_time).groups()
        start_h, start_m = map(int, start.split(':'))
        end_h, end_m = map(int, end.split(':'))
        now = datetime.now()
        current_time = now.hour * 60 + now.minute
        start_time = start_h * 60 + start_m
        end_time = end_h * 60 + end_m
        if start_time <= current_time <= end_time:
            bot.delete_message(chat_id, m.message_id)
            bot.send_message(chat_id, "🌙 Night mode: No messages allowed!")
            send_log(chat_id, f"Message deleted in night mode from {user_id}")

    if settings.get('approve', False) and settings.get('approve_mode', 'manual') == 'manual':
        bot.delete_message(chat_id, m.message_id)
        bot.send_message(chat_id, "🛡️ Message pending approval!")
        send_log(chat_id, f"Message from {user_id} pending approval")

    if settings.get('recurring', False):
        cursor = conn.execute("SELECT messages FROM recurring WHERE chat_id=?", (chat_id,))
        row = cursor.fetchone()
        if row:
            messages = json.loads(row[0])
            for msg in messages:
                if time.time() % msg['time'] < 10:  # Approx check for recurring
                    bot.send_message(chat_id, msg['msg'])
                    send_log(chat_id, f"Recurring message sent: {msg['msg']}")

    if settings.get('crypto_alert') and m.text:
        cursor = global_conn.execute("SELECT currency, price FROM crypto")
        for currency, price in cursor.fetchall():
            if currency.lower() in text.lower():
                bot.reply_to(m, f"🪙 {currency} price: ${price}")

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    return 'OK', 200

@app.route('/')
def home(): return "🤖 Ultimate Bot Live!"

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"https://helliobot.onrender.com/{TOKEN}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)