# -*- coding: utf-8 -*-
# Advanced Telegram Group Manager Bot — single-file, no extra libs, Choreo-safe
# Buttons-first UX. Cleanup policy: naya message send hone ke baad hi pichla delete.

import os, sqlite3, json, time, re, random, logging, html
from datetime import datetime, timedelta
from threading import Lock, Thread
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

import telebot
from telebot import types
from dotenv import load_dotenv

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

# ---------- Env & Bot ----------
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logging.error("❌ BOT_TOKEN not found! Check your Choreo Environment Variables.")
    raise SystemExit(1)

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# ---------- Globals ----------
DB_PATH = os.getenv('DB_PATH', 'bot.db')
MENU_CACHE = {}
flood_locks = defaultdict(Lock)
user_messages = defaultdict(list)  # flood cache
last_reply_id = {}                 # per-chat last bot message id
START_MESSAGE_IDS = set()          # /start messages protected from cleanup
STATE = {}                         # transient per-chat states
LOCK = Lock()
DEBUG_CHATS = set()

# ---------- Utilities ----------
def now_ts():
    return int(time.time())

def jdump(obj):
    return json.dumps(obj, ensure_ascii=False)

def jload(s, default=None):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default

def safe_int(x, d=0):
    try:
        return int(x)
    except Exception:
        return d

def safe_html(text):
    return html.escape(text or "")

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def is_admin_member(chat_id, user_id):
    try:
        m = bot.get_chat_member(chat_id, user_id)
        return m.status in ("administrator", "creator")
    except Exception:
        return False

def dbg(chat_id, text):
    if chat_id in DEBUG_CHATS:
        try: bot.send_message(chat_id, f"[DBG] {text[:350]}")
        except Exception: pass

# ---------- DB ----------
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db(); c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        chat_id TEXT PRIMARY KEY,
        lang TEXT DEFAULT 'hi',
        welcome_enabled INTEGER DEFAULT 1,
        leave_enabled INTEGER DEFAULT 1,
        flood_window INTEGER DEFAULT 15,
        flood_limit INTEGER DEFAULT 7,
        blacklist_enabled INTEGER DEFAULT 1,
        locks_json TEXT DEFAULT '{}',
        roles_json TEXT DEFAULT '{}',
        rss_json TEXT DEFAULT '[]',
        plugins_json TEXT DEFAULT '[]',
        subscriptions_json TEXT DEFAULT '[]',
        menu_json TEXT DEFAULT '{}'
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        pattern TEXT,
        reply TEXT,
        is_regex INTEGER DEFAULT 0
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        key TEXT,
        content TEXT,
        created_at INTEGER,
        expires_at INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        cmd TEXT,
        body TEXT,
        roles TEXT DEFAULT 'all'
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        action TEXT,
        at INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        word TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        type TEXT,
        until_ts INTEGER
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS dumps (
        chat_id TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        forward_to TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        question TEXT,
        options_json TEXT,
        multiple INTEGER DEFAULT 0,
        open INTEGER DEFAULT 1,
        created_at INTEGER
    )""")

    conn.commit(); conn.close()

init_db()

# ---------- Settings helpers ----------
def ensure_settings(chat_id):
    conn = db(); c = conn.cursor()
    c.execute("SELECT chat_id FROM settings WHERE chat_id=?", (chat_id,))
    if not c.fetchone():
        c.execute("INSERT INTO settings(chat_id) VALUES(?)", (chat_id,))
        conn.commit()
    conn.close()

def get_settings(chat_id):
    ensure_settings(str(chat_id))
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM settings WHERE chat_id=?", (str(chat_id),))
    row = c.fetchone(); conn.close()
    return row

def set_setting(chat_id, key, value):
    ensure_settings(str(chat_id))
    conn = db(); c = conn.cursor()
    c.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, str(chat_id)))
    conn.commit(); conn.close()

# ---------- Cleanup-safe send ----------
def send_menu(chat_id, text, markup=None, tag=None, skip_cleanup=False, mark_start=False):
    """
    Policy: pehle send, fir purana delete (agar hai).
    skip_cleanup=True ho to purana mat delete.
    mark_start=True: is message ko /start protection milegi (auto-delete kabhi nahi).
    """
    m = bot.send_message(chat_id, text, reply_markup=markup)
    if mark_start:
        START_MESSAGE_IDS.add((chat_id, m.message_id))
    if not skip_cleanup:
        prev = last_reply_id.get(str(chat_id))
        if prev and prev != m.message_id and (chat_id, prev) not in START_MESSAGE_IDS:
            try:
                bot.delete_message(chat_id, prev)
            except Exception:
                pass
    last_reply_id[str(chat_id)] = m.message_id
    if tag:
        MENU_CACHE[(str(chat_id), tag)] = m.message_id
    return m

# ---------- Languages ----------
LANG = {
    'en': {
        'main': """🔧 MAIN MENU

🛡️ Verify
👋 Welcome
📬 Triggers
⏰ Schedule
🧹 Clean
🚫 Block
🌐 Lang
⚙️ Advanced
👥 Group""",
        'back': "⬅️ Back",
        'group': "👥 GROUP MANAGEMENT",
        'ok': "✅ Done",
        'cancel': "✖️ Cancel",
        'welcome_on': "Welcome enabled.",
        'welcome_off': "Welcome disabled.",
        'stats_title': "📈 Analytics (7d/30d):",
        'start': "👋 Hello! Use the menu below to manage this chat."
    },
    'hi': {
        'main': """🔧 मुख्य मेनू

🛡️ वेरिफ़ाई
👋 स्वागत
📬 ट्रिगर्स
⏰ शेड्यूल
🧹 क्लीन
🚫 ब्लॉक
🌐 भाषा
⚙️ एडवांस्ड
👥 ग्रुप""",
        'back': "⬅️ पीछे",
        'group': "👥 ग्रुप प्रबंधन",
        'ok': "✅ हो गया",
        'cancel': "✖️ रद्द",
        'welcome_on': "स्वागत संदेश चालू।",
        'welcome_off': "स्वागत संदेश बंद।",
        'stats_title': "📈 एनालिटिक्स (7दिन/30दिन):",
        'start': "👋 नमस्ते! नीचे दिए मेनू से इस चैट को मैनेज करें."
    }
}

def tr(chat_id, key):
    row = get_settings(str(chat_id))
    lang = (row['lang'] if row and row['lang'] else 'hi')
    return LANG.get(lang, LANG['hi']).get(key, key)

# ---------- Button labels (no split dependency) ----------
BTN = {
    'en': {
        'verify': "🛡️ Verify",
        'welcome': "👋 Welcome",
        'triggers': "📬 Triggers",
        'schedule': "⏰ Schedule",
        'clean': "🧹 Clean",
        'block': "🚫 Block",
        'lang': "🌐 Lang",
        'advanced': "⚙️ Advanced",
        'group': "👥 Group",
        'back': "⬅️ Back"
    },
    'hi': {
        'verify': "🛡️ वेरिफ़ाई",
        'welcome': "👋 स्वागत",
        'triggers': "📬 ट्रिगर्स",
        'schedule': "⏰ शेड्यूल",
        'clean': "🧹 क्लीन",
        'block': "🚫 ब्लॉक",
        'lang': "🌐 भाषा",
        'advanced': "⚙️ एडवांस्ड",
        'group': "👥 ग्रुप",
        'back': "⬅️ पीछे"
    }
}

def bt(chat_id, key):
    row = get_settings(str(chat_id))
    lang = (row['lang'] if row and row['lang'] else 'hi')
    return BTN.get(lang, BTN['hi']).get(key, key)
# ---------- Keyboards ----------
def kb(rows):
    markup = types.InlineKeyboardMarkup()
    for r in rows:
        markup.row(*[types.InlineKeyboardButton(text=t, callback_data=d) for t, d in r])
    return markup

def main_menu_kb(chat_id):
    return kb([
        [(bt(chat_id,'verify'),"verify"), (bt(chat_id,'welcome'),"welcome")],
        [(bt(chat_id,'triggers'),"triggers"), (bt(chat_id,'schedule'),"schedule")],
        [(bt(chat_id,'clean'),"clean"), (bt(chat_id,'block'),"block")],
        [(bt(chat_id,'lang'),"lang"), (bt(chat_id,'advanced'),"advanced")],
        [(bt(chat_id,'group'),"group")]
    ])
    
    # ---------- Analytics ----------
def track(chat_id, user_id, action):
    try:
        conn = db(); c = conn.cursor()
        c.execute("INSERT INTO analytics(chat_id,user_id,action,at) VALUES(?,?,?,?)",
                  (str(chat_id), str(user_id or ''), action, now_ts()))
        conn.commit(); conn.close()
    except Exception as e:
        logging.warning(f"analytics error: {e}")

def stats_report(chat_id, days=7):
    conn = db(); c = conn.cursor()
    since = now_ts() - days*86400
    c.execute("SELECT action, COUNT(*) c FROM analytics WHERE chat_id=? AND at>=? GROUP BY action ORDER BY c DESC",
              (str(chat_id), since))
    rows = c.fetchall(); conn.close()
    lines = [f"{r['action']}: {r['c']}" for r in rows] or ["(no data)"]
    return "\n".join(lines)

# ---------- Welcome Template ----------
def welcome_tpl_get(chat_id):
    row = get_settings(str(chat_id))
    menu = jload(row['menu_json'], {}) or {}
    return menu.get('welcome_tpl', "👋 Welcome, {name}!")

def welcome_tpl_set(chat_id, text):
    row = get_settings(str(chat_id))
    menu = jload(row['menu_json'], {}) or {}
    menu['welcome_tpl'] = text
    set_setting(str(chat_id), 'menu_json', jdump(menu))

# ---------- Member updates (welcome/leave) ----------
@bot.chat_member_handler()
def on_member(event):
    chat_id = event.chat.id
    row = get_settings(str(chat_id))
    new = event.new_chat_member
    left = event.left_chat_member
    if new and row['welcome_enabled']:
        try:
            tpl = welcome_tpl_get(chat_id)
            name = safe_html(new.user.first_name or "User")
            msg = tpl.format(name=name, id=new.user.id)
            bot.send_message(chat_id, msg)
            track(chat_id, new.user.id, "welcome")
        except Exception:
            pass
    if left and row['leave_enabled']:
        try:
            name = safe_html(left.first_name or "User")
            bot.send_message(chat_id, f"👋 {name} left.")
            track(chat_id, left.id, "leave")
        except Exception:
            pass

# ---------- Flood control ----------
def check_flood(chat_id, user_id):
    row = get_settings(str(chat_id))
    window = clamp(safe_int(row['flood_window'], 15), 5, 120)
    limit = clamp(safe_int(row['flood_limit'], 7), 3, 30)
    key = (str(chat_id), str(user_id))
    with flood_locks[key]:
        arr = user_messages[key]
        now = now_ts()
        arr = [t for t in arr if now - t <= window]
        arr.append(now)
        user_messages[key] = arr
        return len(arr) > limit

# ---------- Blacklist ----------
def contains_blacklist(chat_id, text):
    conn = db(); c = conn.cursor()
    c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall(); conn.close()
    t = (text or "").lower()
    for r in rows:
        if r['word'].lower() in t:
            return True
    return False

# ---------- Triggers ----------
def match_trigger(chat_id, text):
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM triggers WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall(); conn.close()
    for r in rows:
        pat = r['pattern']
        if r['is_regex']:
            try:
                if re.search(pat, text, flags=re.I):
                    return r['reply']
            except re.error:
                continue
        else:
            if pat.lower() in (text or "").lower():
                return r['reply']
    return None
    
    
    # ---------- Commands ----------
@bot.message_handler(commands=['start'])
def cmd_start(m):
    chat_id = m.chat.id
    markup = main_menu_kb(chat_id)
    sent = bot.send_message(chat_id, tr(chat_id,'start'), reply_markup=markup)
    START_MESSAGE_IDS.add((chat_id, sent.message_id))  # protect start message
    last_reply_id[str(chat_id)] = sent.message_id
    track(chat_id, m.from_user.id, "start")

@bot.message_handler(commands=['menu'])
def cmd_menu(m):
    show_main(m.chat.id)

@bot.message_handler(commands=['lang'])
def cmd_lang(m):
    chat_id = m.chat.id
    row = get_settings(str(chat_id))
    new = 'hi' if (row['lang'] == 'en') else 'en'
    set_setting(str(chat_id), 'lang', new)
    bot.reply_to(m, f"Lang: {new}")
    track(chat_id, m.from_user.id, "lang_toggle")

def kb_back(chat_id, back_cb):
    return kb([[(tr(chat_id,'back'), back_cb)]])

def show_main(chat_id):
    send_menu(chat_id, tr(chat_id, 'main'), main_menu_kb(chat_id), tag='main')

def group_menu(chat_id):
    markup = kb([
        [("🔒 Locks","g_locks"), ("👤 Roles","g_roles")],
        [("📈 Analytics","g_stats"), ("🧪 Captcha","g_captcha")],
        [("🧰 Tools","g_tools"), ("🧾 Dumps","g_dumps")],
        [(tr(chat_id,'back'),"back_main")]
    ])
    send_menu(chat_id, tr(chat_id, 'group'), markup, tag='group')

# ---------- Callback routing ----------
@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == 'back_main':
        show_main(chat_id); return
    if data == 'group':
        group_menu(chat_id); return

    if data == 'g_stats':
        text = tr(chat_id, 'stats_title') + "

" + stats_report(chat_id, 7) + "
—
" + stats_report(chat_id, 30)
        send_menu(chat_id, text, kb_back(chat_id,'group')); return

    if data == 'welcome':
        row = get_settings(str(chat_id))
        new = 0 if row['welcome_enabled'] else 1
        set_setting(str(chat_id), 'welcome_enabled', new)
        send_menu(chat_id, tr(chat_id, 'welcome_on') if new else tr(chat_id, 'welcome_off'), kb_back(chat_id,'back_main')); return

    if data == 'verify':
        send_menu(chat_id, "Verification tools ready.", kb_back(chat_id,'back_main')); return

    if data == 'triggers':
        send_menu(chat_id, "Triggers menu.", kb([[("Add","TR_ADD"),("List","TR_LIST")],[("Test regex","TR_TEST")],[ (tr(chat_id,'back'),'back_main') ]])); return

    if data == 'schedule':
        send_menu(chat_id, "Scheduler:", kb([[("➕ Add","SCH_ADD"),("📋 List","SCH_LIST")],[ (tr(chat_id,'back'),'back_main') ]])); return

    if data == 'clean':
        send_menu(chat_id, "Clean rules.", kb([[("Flood","CL_FLOOD"),("Blacklist","CL_BL")],[ (tr(chat_id,'back'),'back_main') ]])); return

    if data == 'block':
        send_menu(chat_id, "Blacklist menu.", kb([[("Add word","BL_ADD"),("List","BL_LIST")],[ (tr(chat_id,'back'),'back_main') ]])); return

    if data == 'advanced':
        send_menu(chat_id, "Advanced: Roles, Locks, RSS, Dumps, Federation, Subs, Polls.",
                  kb([[("Subs","SUBS"),("Plugins","PLUG")],[("Polls","PL_MENU")],[ (tr(chat_id,'back'),'back_main') ]])); return

    advanced_route(chat_id, data)

def advanced_route(chat_id, key):
    if key == 'lang':
        row = get_settings(str(chat_id))
        new = 'hi' if (row['lang'] == 'en') else 'en'
        set_setting(str(chat_id), 'lang', new)
        show_main(chat_id); return

    if key == 'g_tools':
        send_menu(chat_id, "Tools:
- Notes
- Commands
- Blacklist
- Dumps
- RSS", kb_back(chat_id,'group')); return

    if key == 'g_locks':
        locks = jdump(get_locks(chat_id))
        send_menu(chat_id, f"Locks: {locks}",
                  kb([[("Links on","LOCK_links_on"),("Links off","LOCK_links_off")],
                      [(tr(chat_id,'back'),'group')]])); return

    if key == 'g_roles':
        roles = jdump(get_roles(chat_id))
        send_menu(chat_id, f"Roles: {roles}", kb_back(chat_id,'group')); return

    if key == 'g_captcha':
        send_menu(chat_id, "Captcha: use the button to generate.",
                  kb([[("Generate","CAP_GEN")],[ (tr(chat_id,'back'),'group') ]])); return

    if key == 'g_dumps':
        send_menu(chat_id, "Dumps: toggle and set forward target.",
                  kb([[("Toggle","DUMP_T"),("Set target","DUMP_S")],[ (tr(chat_id,'back'),'group') ]])); return

    if key == 'PL_MENU':
        send_menu(chat_id, "Polls:", kb([[("➕ New","PL_NEW"),("📋 List","PL_LIST")],[ (tr(chat_id,'back'),'advanced') ]])); return
        
        
        # ---------- Roles & Locks ----------
def get_roles(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['roles_json'], {}) or {}

def set_roles(chat_id, roles):
    set_setting(str(chat_id), 'roles_json', jdump(roles))

def get_locks(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['locks_json'], {}) or {}

def set_locks(chat_id, locks):
    set_setting(str(chat_id), 'locks_json', jdump(locks))

@bot.callback_query_handler(func=lambda c: c.data.startswith("LOCK_"))
def cb_lock(call):
    chat_id = call.message.chat.id
    _, feature, onoff = call.data.split("_", 3)
    locks = get_locks(chat_id); locks[feature] = 1 if onoff == 'on' else 0
    set_locks(chat_id, locks)
    send_menu(chat_id, f"Lock {feature}: {'on' if locks[feature] else 'off'}",
              kb([[("Links on","LOCK_links_on"),("Links off","LOCK_links_off")],[ (tr(chat_id,'back'),'group') ]]))

# ---------- Captcha ----------
pending_captcha = {}

def captcha_new():
    a,b = random.randint(3,12), random.randint(3,12)
    return f"{a}+{b}=?", a+b

@bot.callback_query_handler(func=lambda c: c.data == "CAP_GEN")
def cb_cap_gen(call):
    chat_id = call.message.chat.id
    q, ans = captcha_new()
    pending_captcha[(chat_id, call.from_user.id)] = ans
    send_menu(chat_id, f"Solve: {q}", kb([[("Submit ✅","CAP_OK")],[ (tr(chat_id,'back'),'g_captcha') ]]))

@bot.callback_query_handler(func=lambda c: c.data == "CAP_OK")
def cb_cap_ok(call):
    chat_id = call.message.chat.id
    key = (chat_id, call.from_user.id)
    if key in pending_captcha:
        pending_captcha.pop(key, None)
        send_menu(chat_id, "Verified ✅", kb_back(chat_id,'g_captcha'))
        track(chat_id, call.from_user.id, "captcha_pass")
    else:
        send_menu(chat_id, "No pending captcha.", kb_back(chat_id,'g_captcha'))
        
        
        
        # ---------- Blacklist UI ----------
@bot.callback_query_handler(func=lambda c: c.data in ("BL_ADD","BL_LIST"))
def cb_blacklist_menu(call):
    chat_id = call.message.chat.id
    if call.data == "BL_ADD":
        STATE[(chat_id, "await_bl")] = True
        send_menu(chat_id, "Word bhejo (chat me type karo).", kb_back(chat_id,'block'))
    else:
        conn = db(); c = conn.cursor()
        c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
        rows = c.fetchall(); conn.close()
        words = ", ".join(r['word'] for r in rows) if rows else "(empty)"
        send_menu(chat_id, f"Blacklist: {words}", kb_back(chat_id,'block'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_bl")) and bool(m.text))
def bl_add_text(m):
    chat_id = m.chat.id
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO blacklist(chat_id,word) VALUES(?,?)", (str(chat_id), m.text.strip()))
    conn.commit(); conn.close()
    STATE.pop((chat_id, "await_bl"), None)
    bot.reply_to(m, "Added to blacklist.")

# ---------- Triggers UI ----------
@bot.callback_query_handler(func=lambda c: c.data in ("TR_ADD","TR_LIST","TR_TEST"))
def cb_triggers(call):
    chat_id = call.message.chat.id
    if call.data == "TR_ADD":
        STATE[(chat_id, "await_tr_pat")] = {'is_regex':0}
        send_menu(chat_id, "Trigger keyword ya /regex:<pattern> bhejo.", kb_back(chat_id,'triggers'))
    elif call.data == "TR_LIST":
        conn = db(); c = conn.cursor()
        c.execute("SELECT pattern, is_regex FROM triggers WHERE chat_id=?", (str(chat_id),))
        rows = c.fetchall(); conn.close()
        text = "Triggers:
" + "
".join(f"- {'/regex:' if r['is_regex'] else ''}{r['pattern']}" for r in rows) if rows else "No triggers."
        send_menu(chat_id, text, kb_back(chat_id,'triggers'))
    else:
        STATE[(chat_id, "await_regex_test")] = {'step':1}
        send_menu(chat_id, "Regex दर्ज करें. Example: ^hello$", kb_back(chat_id,'triggers'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_tr_pat")))
def tr_add_flow(m):
    chat_id = m.chat.id
    data = STATE.get((chat_id, "await_tr_pat"))
    txt = m.text.strip()
    is_regex = 0
    if txt.startswith("/regex:"):
        is_regex = 1
        txt = txt[len("/regex:"):].strip()
        try:
            re.compile(txt)
        except re.error:
            bot.reply_to(m, "Regex invalid.")
            return
    STATE[(chat_id, "await_tr_rep")] = {'pattern':txt, 'is_regex':is_regex}
    STATE.pop((chat_id, "await_tr_pat"), None)
    bot.reply_to(m, "Reply text bhejo.")

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_tr_rep")))
def tr_add_reply(m):
    chat_id = m.chat.id
    step = STATE.pop((chat_id, "await_tr_rep"))
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO triggers(chat_id,pattern,reply,is_regex) VALUES(?,?,?,?)",
              (str(chat_id), step['pattern'], m.text.strip(), step['is_regex']))
    conn.commit(); conn.close()
    bot.reply_to(m, "Trigger added.")

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_regex_test")) and bool(m.text))
def tr_test_flow(m):
    chat_id = m.chat.id
    st = STATE.get((chat_id, "await_regex_test"))
    if st['step'] == 1:
        pattern = m.text.strip()
        try:
            re.compile(pattern)
        except re.error as e:
            bot.reply_to(m, f"Invalid regex: {e}"); return
        st['pattern'] = pattern; st['step'] = 2
        STATE[(chat_id, "await_regex_test")] = st
        bot.reply_to(m, "Test text भेजें.")
    else:
        pattern = st['pattern']; text = m.text
        try:
            ok = bool(re.search(pattern, text, flags=re.I))
            bot.reply_to(m, f"Match: {'YES' if ok else 'NO'}")
        except re.error as e:
            bot.reply_to(m, f"Error: {e}")
        STATE.pop((chat_id, "await_regex_test"), None)
        
        
        # ---------- Notes ----------
@bot.message_handler(commands=['note'])
def cmd_note(m):
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(m, "Use: /note key content"); return
    key, content = parts[1], parts[2]
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO notes(chat_id,key,content,created_at,expires_at) VALUES(?,?,?,?,?)",
              (str(m.chat.id), key, content, now_ts(), 0))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Saved note: {key}")

@bot.message_handler(commands=['get'])
def cmd_get(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Use: /get key"); return
    key = parts[1]
    conn = db(); c = conn.cursor()
    c.execute("SELECT content FROM notes WHERE chat_id=? AND key=? ORDER BY id DESC LIMIT 1",
              (str(m.chat.id), key))
    row = c.fetchone(); conn.close()
    bot.reply_to(m, row['content'] if row else "Not found")

# ---------- Custom commands ----------
@bot.message_handler(func=lambda m: m.text and m.text.startswith('!'))
def custom_cmd(m):
    cmd = m.text.split()[0][1:].lower()
    conn = db(); c = conn.cursor()
    c.execute("SELECT body FROM commands WHERE chat_id=? AND cmd=?", (str(m.chat.id), cmd))
    row = c.fetchone(); conn.close()
    if row:
        bot.reply_to(m, row['body'])

@bot.message_handler(commands=['addcmd'])
def cmd_addcmd(m):
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(m, "Use: /addcmd name body"); return
    name, body = parts[1].lower(), parts[2]
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO commands(chat_id,cmd,body) VALUES(?,?,?)", (str(m.chat.id), name, body))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Added command: !{name}")

# ---------- Admin-only guard ----------
def admin_only(m):
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, "Admin only."); return False
    return True

@bot.message_handler(commands=['lock'])
def cmd_lock(m):
    if not admin_only(m): return
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Use: /lock feature on|off"); return
    feature = parts[1].lower()
    val = 1 if parts[2].lower()=='on' else 0
    locks = get_locks(m.chat.id); locks[feature] = val; set_locks(m.chat.id, locks)
    bot.reply_to(m, f"Lock {feature}: {'on' if val else 'off'}")

# ---------- Help/About ----------
HELP_TEXT_HI = """ℹ️ मदद

- /start — मेनू खोलें
- /menu — मेनू दिखाएँ
- /lang — भाषा बदलें
- /note, /get — नोट सेव/लाओ
- /addcmd, !cmd — कस्टम कमांड
- /blackadd, /blacklist — ब्लैकलिस्ट
- /lock — लॉक ऑन/ऑफ
- /export_stats — एनालिटिक्स एक्सपोर्ट
बाक़ी सब बटन से करें."""
HELP_TEXT_EN = """ℹ️ Help

- /start — open menu
- /menu — show menu
- /lang — toggle language
- /note, /get — notes save/get
- /addcmd, !cmd — custom commands
- /blackadd, /blacklist — blacklist
- /lock — toggle locks
- /export_stats — export analytics
Use buttons for everything else."""

@bot.message_handler(commands=['help','about'])
def cmd_help(m):
    row = get_settings(str(m.chat.id))
    lang = row['lang'] if row and row['lang'] else 'hi'
    bot.reply_to(m, HELP_TEXT_HI if lang=='hi' else HELP_TEXT_EN)

@bot.callback_query_handler(func=lambda c: c.data == "HELP")
def cb_help(call):
    chat_id = call.message.chat.id
    send_menu(chat_id, "Help opened. Also try /help.", kb_back(chat_id,'back_main'))

# ---------- Debug toggle ----------
@bot.message_handler(commands=['debug'])
def cmd_debug(m):
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, "Admin only."); return
    if m.chat.id in DEBUG_CHATS:
        DEBUG_CHATS.remove(m.chat.id); bot.reply_to(m, "Debug: off")
    else:
        DEBUG_CHATS.add(m.chat.id); bot.reply_to(m, "Debug: on")
        
        
        # ---------- RSS ----------
def rss_get_items(url, limit=5, timeout=10):
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8', 'ignore')
        items = []
        for item in re.findall(r'<item>(.*?)</item>', data, flags=re.I|re.S):
            t = re.search(r'<title>(.*?)</title>', item, flags=re.I|re.S)
            l = re.search(r'<link>(.*?)</link>', item, flags=re.I|re.S)
            if t and l:
                title = re.sub(r'<.*?>','', t.group(1)).strip()
                link = re.sub(r'<.*?>','', l.group(1)).strip()
                if title and link:
                    items.append((title, link))
            if len(items) >= limit: break
        return items
    except Exception as e:
        logging.warning(f"rss error: {e}")
        return []

def rss_list(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['rss_json'], []) or []

def rss_save(chat_id, feeds):
    set_setting(str(chat_id), 'rss_json', jdump(feeds))

@bot.callback_query_handler(func=lambda c: c.data in ("RSS_ADD","RSS_LIST"))
def cb_rss_menu(call):
    chat_id = call.message.chat.id
    if call.data == "RSS_ADD":
        STATE[(chat_id, "await_rss_url")] = True
        send_menu(chat_id, "RSS URL bhejo, optional space ke baad seconds (default 900).", kb_back(chat_id,'schedule'))
    else:
        feeds = rss_list(chat_id)
        text = "Feeds:
" + "
".join(f"- {f['url']} ({f.get('interval',900)}s)" for f in feeds) if feeds else "No feeds."
        send_menu(chat_id, text, kb_back(chat_id,'schedule'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_rss_url")) and bool(m.text))
def rss_add_text(m):
    parts = m.text.split()
    url = parts[0]
    interval = clamp(safe_int(parts[1], 900) if len(parts) >=2 else 900, 300, 86400)
    feeds = rss_list(m.chat.id); feeds.append({'url':url, 'interval':interval, 'last':0, 'seen':[]})
    rss_save(m.chat.id, feeds)
    STATE.pop((m.chat.id, "await_rss_url"), None)
    bot.reply_to(m, "RSS added.")

def rss_tick():
    while True:
        try:
            conn = db(); c = conn.cursor()
            c.execute("SELECT chat_id, rss_json FROM settings")
            rows = c.fetchall()
            now = now_ts()
            for r in rows:
                chat_id = r['chat_id']
                feeds = jload(r['rss_json'], []) or []
                updated = False
                for f in feeds:
                    url = f.get('url'); interval = clamp(safe_int(f.get('interval',900),900), 300, 86400)
                    last = safe_int(f.get('last', 0))
                    if not url: continue
                    if now - last >= interval:
                        items = rss_get_items(url, limit=3)
                        seen = f.get('seen', [])
                        for t, l in items:
                            key = (t + "|" + l)[:200]
                            if key in seen: continue
                            try:
                                bot.send_message(chat_id, f"📰 {safe_html(t)}
{l}")
                            except Exception:
                                pass
                            seen.append(key)
                            if len(seen) > 50: seen = seen[-50:]
                        f['seen'] = seen
                        f['last'] = now
                        updated = True
                if updated:
                    c2 = conn.cursor()
                    c2.execute("UPDATE settings SET rss_json=? WHERE chat_id=?", (jdump(feeds), chat_id))
                    conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"rss tick error: {e}")
        time.sleep(15)

Thread(target=rss_tick, daemon=True).start()


# ---------- Subscriptions ----------
def subs_get(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['subscriptions_json'], []) or []

def subs_set(chat_id, arr):
    set_setting(str(chat_id), 'subscriptions_json', jdump(arr))

@bot.callback_query_handler(func=lambda c: c.data == "SUBS")
def cb_subs(call):
    chat_id = call.message.chat.id
    send_menu(chat_id, "Subscriptions:", kb([[("Add","SUBS_ADD"),("List","SUBS_LIST")],[ (tr(chat_id,'back'),'advanced') ]]))

@bot.callback_query_handler(func=lambda c: c.data in ("SUBS_ADD","SUBS_LIST"))
def cb_subs_ops(call):
    chat_id = call.message.chat.id
    if call.data == "SUBS_ADD":
        STATE[(chat_id, "await_subs")] = True
        send_menu(chat_id, "Format: name days (e.g., pro 30)", kb_back(chat_id,'SUBS'))
    else:
        arr = subs_get(chat_id)
        text = "Subs:
" + "
".join(f"- {a['name']} till {a['until']}" for a in arr) if arr else "No subs."
        send_menu(chat_id, text, kb_back(chat_id,'SUBS'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_subs")) and bool(m.text))
def subs_add_text(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Use: name days"); return
    name, days = parts[0], clamp(safe_int(parts[1], 7), 1, 365)
    until = (datetime.utcnow()+timedelta(days=days)).strftime('%Y-%m-%d')
    arr = subs_get(m.chat.id); arr.append({'name':name,'until':until})
    subs_set(m.chat.id, arr); STATE.pop((m.chat.id, "await_subs"), None)
    bot.reply_to(m, f"Added {name} till {until}")

# ---------- Plugins (registry only) ----------
def plugins_get(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['plugins_json'], []) or []

def plugins_set(chat_id, arr):
    set_setting(str(chat_id), 'plugins_json', jdump(arr))

@bot.callback_query_handler(func=lambda c: c.data == "PLUG")
def cb_plug(call):
    chat_id = call.message.chat.id
    send_menu(chat_id, "Plugins:", kb([[("List","PLUG_LIST"),("Add/Toggle","PLUG_ADD")],[ (tr(chat_id,'back'),'advanced') ]]))

@bot.callback_query_handler(func=lambda c: c.data in ("PLUG_LIST","PLUG_ADD"))
def cb_plug_ops(call):
    chat_id = call.message.chat.id
    if call.data == "PLUG_LIST":
        arr = plugins_get(chat_id)
        text = "Plugins:
" + "
".join(f"- {p['name']}: {'on' if p.get('on') else 'off'}" for p in arr) if arr else "No plugins."
        send_menu(chat_id, text, kb_back(chat_id,'PLUG'))
    else:
        STATE[(chat_id, "await_plug")] = True
        send_menu(chat_id, "Format: name on|off", kb_back(chat_id,'PLUG'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_plug")) and bool(m.text))
def plug_add_text(m):
    parts = m.text.split()
    if len(parts) < 2:
        bot.reply_to(m, "Use: name on|off"); return
    name, onoff = parts[0], parts[1].lower()
    arr = plugins_get(m.chat.id)
    found = next((p for p in arr if p['name']==name), None)
    if found:
        found['on'] = (onoff == 'on')
    else:
        arr.append({'name':name, 'on': (onoff=='on')})
    plugins_set(m.chat.id, arr)
    STATE.pop((m.chat.id, "await_plug"), None)
    bot.reply_to(m, f"Plugin {name}: {'on' if (onoff=='on') else 'off'}")

# ---------- Dumps ----------
@bot.callback_query_handler(func=lambda c: c.data in ("DUMP_T","DUMP_S"))
def cb_dump_ops(call):
    chat_id = call.message.chat.id
    if call.data == "DUMP_T":
        conn = db(); c = conn.cursor()
        c.execute("SELECT enabled FROM dumps WHERE chat_id=?", (str(chat_id),))
        row = c.fetchone()
        enabled = 0 if (row and row['enabled']) else 1
        c.execute("INSERT INTO dumps(chat_id,enabled) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET enabled=?",
                  (str(chat_id), enabled, enabled))
        conn.commit(); conn.close()
        send_menu(chat_id, f"Dump: {'on' if enabled else 'off'}", kb_back(chat_id,'g_dumps'))
    else:
        STATE[(chat_id, "await_dump_target")] = True
        send_menu(chat_id, "Forward target chat_id bhejo (negative id for channels).", kb_back(chat_id,'g_dumps'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_dump_target")) and bool(m.text))
def dump_set_target(m):
    chat_id = m.chat.id
    target = m.text.strip()
    conn = db(); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO dumps(chat_id,forward_to,enabled) VALUES(?,?,COALESCE((SELECT enabled FROM dumps WHERE chat_id=?),0))",
              (str(chat_id), target, str(chat_id)))
    conn.commit(); conn.close()
    STATE.pop((chat_id, "await_dump_target"), None)
    bot.reply_to(m, f"Dump target set: {target}")

@bot.message_handler(content_types=['photo','video','document','audio','sticker','voice','text'])
def dump_forward(m):
    try:
        conn = db(); c = conn.cursor()
        c.execute("SELECT enabled, forward_to FROM dumps WHERE chat_id=?", (str(m.chat.id),))
        row = c.fetchone(); conn.close()
        if not row or not row['enabled'] or not row['forward_to']:
            return
        target = safe_int(row['forward_to'])
        if getattr(m, 'text', None):
            bot.send_message(target, f"[Dump] {safe_html(m.text[:350])}")
        elif m.photo:
            file_id = m.photo[-1].file_id
            bot.send_photo(target, file_id, caption="[Dump]")
        elif m.document:
            bot.send_document(target, m.document.file_id, caption="[Dump]")
        elif m.video:
            bot.send_video(target, m.video.file_id, caption="[Dump]")
        elif m.voice:
            bot.send_voice(target, m.voice.file_id, caption="[Dump]")
        elif m.audio:
            bot.send_audio(target, m.audio.file_id, caption="[Dump]")
        elif m.sticker:
            bot.send_sticker(target, m.sticker.file_id)
    except Exception as e:
        logging.warning(f"dump forward error: {e}")
        
        
        # ---------- Message filters ----------
MAX_MSG_LEN = 4096

def paginate(text, limit=MAX_MSG_LEN):
    if len(text) <= limit:
        return [text]
    chunks = []
    s = text
    while s:
        chunks.append(s[:limit]); s = s[limit:]
    return chunks

@bot.message_handler(func=lambda m: bool(getattr(m, 'text', None)))
def all_text(m):
    # blacklist
    if contains_blacklist(m.chat.id, m.text):
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            pass
        track(m.chat.id, m.from_user.id, "blacklist_delete")
        return

    # flood
    if check_flood(m.chat.id, m.from_user.id):
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except Exception:
            pass
        track(m.chat.id, m.from_user.id, "flood_delete")
        return

    # locks (basic example: links)
    locks = get_locks(m.chat.id)
    if locks.get('links'):
        if re.search(r'https?://', m.text, flags=re.I):
            if not is_admin_member(m.chat.id, m.from_user.id):
                try:
                    bot.delete_message(m.chat.id, m.message_id)
                except Exception:
                    pass
                track(m.chat.id, m.from_user.id, "lock_links_delete")
                return

    # triggers
    reply = match_trigger(m.chat.id, m.text or "")
    if reply:
        for chunk in paginate(reply):
            bot.reply_to(m, chunk)
        track(m.chat.id, m.from_user.id, "trigger_reply")
        
        # ---------- Lock enforcement (media, stickers, forwards) ----------
def enforce_lock_delete(m, action_tag):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except Exception:
        pass
    track(m.chat.id, m.from_user.id, action_tag)

@bot.message_handler(content_types=['photo'])
def lock_photo(m):
    locks = get_locks(m.chat.id)
    if locks.get('photos') and not is_admin_member(m.chat.id, m.from_user.id):
        enforce_lock_delete(m, "lock_photos_delete")

@bot.message_handler(content_types=['video'])
def lock_video(m):
    locks = get_locks(m.chat.id)
    if locks.get('videos') and not is_admin_member(m.chat.id, m.from_user.id):
        enforce_lock_delete(m, "lock_videos_delete")

@bot.message_handler(content_types=['sticker'])
def lock_sticker(m):
    locks = get_locks(m.chat.id)
    if locks.get('stickers') and not is_admin_member(m.chat.id, m.from_user.id):
        enforce_lock_delete(m, "lock_stickers_delete")

@bot.message_handler(func=lambda m: getattr(m, 'forward_from', None) or getattr(m, 'forward_from_chat', None))
def lock_forwards(m):
    locks = get_locks(m.chat.id)
    if locks.get('forwards') and not is_admin_member(m.chat.id, m.from_user.id):
        enforce_lock_delete(m, "lock_forwards_delete")
        
        # ---------- Polls ----------
def polls_create(chat_id, question, options, multiple=False):
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO polls(chat_id,question,options_json,multiple,open,created_at) VALUES(?,?,?,?,?,?)",
              (str(chat_id), question, jdump({'opts':options,'votes':{}}), 1 if multiple else 0, 1, now_ts()))
    conn.commit(); conn.close()

def polls_get_open(chat_id):
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM polls WHERE chat_id=? AND open=1 ORDER BY id DESC", (str(chat_id),))
    rows = c.fetchall(); conn.close(); return rows

def polls_get(chat_id, pid):
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM polls WHERE chat_id=? AND id=?", (str(chat_id), pid))
    row = c.fetchone(); conn.close(); return row

def polls_save_row(row):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE polls SET options_json=?, open=? WHERE id=?",
              (row['options_json'], row['open'], row['id']))
    conn.commit(); conn.close()

def polls_render_kb(pid, options):
    rows = []
    for idx, opt in enumerate(options):
        rows.append([(opt, f"PL_VOTE_{pid}_{idx}")])
    rows.append([("✅ Close","PL_CLOSE_"+str(pid)), ("🔙 Back","PL_BACK")])
    return kb(rows)

@bot.callback_query_handler(func=lambda c: c.data in ("PL_NEW","PL_LIST","PL_BACK"))
def cb_polls_menu(call):
    chat_id = call.message.chat.id
    if call.data == "PL_NEW":
        STATE[(chat_id, "await_poll_q")] = True
        send_menu(chat_id, "Poll question bhejo.
Format: Question | opt1;opt2;opt3", kb([[("🔙 Back","advanced")]]))
    elif call.data == "PL_LIST":
        rows = polls_get_open(chat_id)
        if not rows:
            send_menu(chat_id, "No open polls.", kb([[("🔙 Back","advanced")]])); return
        lines = []
        for r in rows:
            data = jload(r['options_json'], {'opts':[], 'votes':{}})
            counts = [len(data['votes'].get(str(i), [])) for i in range(len(data['opts']))]
            lines.append(f"#{r['id']} {r['question']} — " + ", ".join(f"{data['opts'][i]}={counts[i]}" for i in range(len(counts))))
        send_menu(chat_id, "Open polls:
" + "
".join(lines), kb([[("🔙 Back","advanced")]]))
    else:
        send_menu(chat_id, "Advanced:", kb([[("Subs","SUBS"),("Plugins","PLUG")],[("Polls","PL_MENU")],[ (tr(chat_id,'back'),'back_main') ]]))

@bot.callback_query_handler(func=lambda c: c.data == "PL_MENU")
def cb_poll_root(call):
    chat_id = call.message.chat.id
    send_menu(chat_id, "Polls:", kb([[("➕ New","PL_NEW"),("📋 List","PL_LIST")],[ (tr(chat_id,'back'),'advanced') ]]))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_poll_q")) and bool(m.text))
def polls_new_text(m):
    chat_id = m.chat.id
    STATE.pop((chat_id, "await_poll_q"), None)
    if '|' not in m.text:
        bot.reply_to(m, "Format: Question | opt1;opt2;opt3"); return
    q, opts = m.text.split('|', 1)
    options = [o.strip() for o in opts.split(';') if o.strip()]
    if len(options) < 2:
        bot.reply_to(m, "कम से कम 2 options देने होंगे."); return
    polls_create(chat_id, q.strip(), options, multiple=False)
    row = polls_get_open(chat_id)[0]
    send_menu(chat_id, f"Poll #{row['id']}: {q.strip()}", polls_render_kb(row['id'], options))

@bot.callback_query_handler(func=lambda c: c.data.startswith("PL_VOTE_"))
def cb_poll_vote(call):
    chat_id = call.message.chat.id
    _, _, pid, idx = call.data.split('_', 3)
    pid = safe_int(pid); idx = safe_int(idx)
    row = polls_get(chat_id, pid)
    if not row: return
    if not row['open']:
        send_menu(chat_id, "Poll बंद है.", polls_render_kb(pid, jload(row['options_json'],{})['opts'])); return
    data = jload(row['options_json'], {'opts':[], 'votes':{}})
    if idx < 0 or idx >= len(data['opts']): return
    votes = data.get('votes', {})
    uid = str(call.from_user.id)
    for k in list(votes.keys()):
        if uid in votes[k]:
            votes[k].remove(uid)
    arr = votes.get(str(idx), [])
    if uid not in arr:
        arr.append(uid)
    votes[str(idx)] = arr
    data['votes'] = votes
    newrow = dict(row); newrow['options_json'] = jdump(data)
    polls_save_row(newrow)
    counts = [len(votes.get(str(i), [])) for i in range(len(data['opts']))]
    send_menu(chat_id, f"Voted: {data['opts'][idx]}
" + ", ".join(f"{data['opts'][i]}={counts[i]}" for i in range(len(counts))),
              polls_render_kb(pid, data['opts']))

@bot.callback_query_handler(func=lambda c: c.data.startswith("PL_CLOSE_"))
def cb_poll_close(call):
    chat_id = call.message.chat.id
    pid = safe_int(call.data.split('_')[-1])
    row = polls_get(chat_id, pid)
    if not row: return
    data = jload(row['options_json'], {'opts':[], 'votes':{}})
    row = dict(row); row['open'] = 0; polls_save_row(row)
    counts = [len(data['votes'].get(str(i), [])) for i in range(len(data['opts']))]
    send_menu(chat_id, f"Closed #{pid}
" + "
".join(f"- {data['opts'][i]}: {counts[i]}" for i in range(len(counts))),
              kb([[("🔙 Back","PL_MENU")]]))
              
              
              # ---------- Pagination ----------
def render_list(title, items, back_cb, page=1, per_page=20, prefix=""):
    total = len(items)
    pages = max(1, (total + per_page - 1)//per_page)
    page = clamp(page, 1, pages)
    start = (page-1)*per_page; end = min(total, start+per_page)
    view = items[start:end]
    text = f"{title} ({page}/{pages})
" + ("
".join(f"{prefix}{i+1}. {view[i]}" for i in range(len(view))) if view else "(empty)")
    nav = []
    if page > 1: nav.append(("⬅️ Prev", f"PG_{back_cb}_{page-1}"))
    if page < pages: nav.append(("➡️ Next", f"PG_{back_cb}_{page+1}"))
    rows = [nav] if nav else []
    rows.append([(tr(back_cb,'back') if isinstance(back_cb,int) else "🔙 Back", str(back_cb))])
    return text, kb(rows)

@bot.callback_query_handler(func=lambda c: c.data.startswith("PG_"))
def cb_paginate(call):
    _, key, page = call.data.split("_", 2)
    page = safe_int(page, 1)
    chat_id = call.message.chat.id
    if key == 'TR_LIST':
        conn = db(); c = conn.cursor()
        c.execute("SELECT pattern FROM triggers WHERE chat_id=?", (str(chat_id),))
        rows = [r['pattern'] for r in c.fetchall()]; conn.close()
        text, markup = render_list("Triggers", rows, "triggers", page, 20, prefix="- ")
        send_menu(chat_id, text, markup)
    elif key == 'BL_LIST':
        conn = db(); c = conn.cursor()
        c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
        rows = [r['word'] for r in c.fetchall()]; conn.close()
        text, markup = render_list("Blacklist", rows, "block", page, 20, prefix="- ")
        send_menu(chat_id, text, markup)

# ---------- Analytics export ----------
@bot.message_handler(commands=['export_stats'])
def cmd_export_stats(m):
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, "Admin only."); return
    text = tr(m.chat.id, 'stats_title') + "

" + stats_report(m.chat.id, 7) + "
—
" + stats_report(m.chat.id, 30)
    for chunk in paginate(text):
        bot.reply_to(m, chunk)
        
        
        # ---------- Backup/Restore ----------
@bot.message_handler(commands=['backup'])
def cmd_backup(m):
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, "Admin only."); return
    conn = db(); c = conn.cursor()
    dump = {}
    for tbl, key in [
        ("settings","chat_id"),("triggers","chat_id"),("notes","chat_id"),
        ("commands","chat_id"),("blacklist","chat_id"),("analytics","chat_id"),
        ("punishments","chat_id"),("dumps","chat_id"),("polls","chat_id")
    ]:
        c.execute(f"SELECT * FROM {tbl} WHERE {key}=?", (str(m.chat.id),))
        rows = [dict(r) for r in c.fetchall()]
        dump[tbl] = rows
    conn.close()
    text = jdump(dump)
    for chunk in paginate(text, 3500):
        bot.reply_to(m, f"``````")

@bot.message_handler(commands=['restore'])
def cmd_restore(m):
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, "Admin only."); return
    if not m.reply_to_message or not m.reply_to_message.text:
        bot.reply_to(m, "Reply to backup JSON."); return
    try:
        data = jload(m.reply_to_message.text.strip(), {})
        conn = db(); c = conn.cursor()
        for tbl, rows in data.items():
            if tbl not in ("settings","triggers","notes","commands","blacklist","analytics","punishments","dumps","polls"):
                continue
            for r in rows:
                if tbl == "settings":
                    c.execute("INSERT OR REPLACE INTO settings(chat_id,lang,welcome_enabled,leave_enabled,flood_window,flood_limit,blacklist_enabled,locks_json,roles_json,rss_json,plugins_json,subscriptions_json,menu_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (r.get('chat_id'), r.get('lang','hi'), r.get('welcome_enabled',1), r.get('leave_enabled',1),
                               r.get('flood_window',15), r.get('flood_limit',7), r.get('blacklist_enabled',1),
                               r.get('locks_json','{}'), r.get('roles_json','{}'), r.get('rss_json','[]'),
                               r.get('plugins_json','[]'), r.get('subscriptions_json','[]'), r.get('menu_json','{}')))
                elif tbl == "triggers":
                    c.execute("INSERT INTO triggers(chat_id,pattern,reply,is_regex) VALUES(?,?,?,?)",
                              (str(m.chat.id), r.get('pattern',''), r.get('reply',''), r.get('is_regex',0)))
                elif tbl == "notes":
                    c.execute("INSERT INTO notes(chat_id,key,content,created_at,expires_at) VALUES(?,?,?,?,?)",
                              (str(m.chat.id), r.get('key',''), r.get('content',''), r.get('created_at',now_ts()), r.get('expires_at',0)))
                elif tbl == "commands":
                    c.execute("INSERT INTO commands(chat_id,cmd,body,roles) VALUES(?,?,?,?)",
                              (str(m.chat.id), r.get('cmd',''), r.get('body',''), r.get('roles','all')))
                elif tbl == "blacklist":
                    c.execute("INSERT INTO blacklist(chat_id,word) VALUES(?,?)", (str(m.chat.id), r.get('word','')))
                elif tbl == "analytics":
                    c.execute("INSERT INTO analytics(chat_id,user_id,action,at) VALUES(?,?,?,?)",
                              (str(m.chat.id), r.get('user_id',''), r.get('action',''), r.get('at',now_ts())))
                elif tbl == "punishments":
                    c.execute("INSERT INTO punishments(chat_id,user_id,type,until_ts) VALUES(?,?,?,?)",
                              (str(m.chat.id), r.get('user_id',''), r.get('type','mute'), r.get('until_ts',0)))
                elif tbl == "dumps":
                    c.execute("INSERT OR REPLACE INTO dumps(chat_id,enabled,forward_to) VALUES(?,?,?)",
                              (str(m.chat.id), r.get('enabled',0), r.get('forward_to')))
                elif tbl == "polls":
                    c.execute("INSERT INTO polls(chat_id,question,options_json,multiple,open,created_at) VALUES(?,?,?,?,?,?)",
                              (str(m.chat.id), r.get('question',''), r.get('options_json','{"opts":[],"votes":{}}'),
                               r.get('multiple',0), r.get('open',1), r.get('created_at',now_ts())))
        conn.commit(); conn.close()
        bot.reply_to(m, "Restore done.")
    except Exception as e:
        bot.reply_to(m, f"Restore error: {e}")
        
        
        # ---------- Manual Scheduler ----------
def sched_get(chat_id):
    row = get_settings(str(chat_id))
    menu = jload(row['menu_json'], {}) or {}
    return menu.get('sched', [])

def sched_set(chat_id, arr):
    row = get_settings(str(chat_id))
    menu = jload(row['menu_json'], {}) or {}
    menu['sched'] = arr
    set_setting(str(chat_id), 'menu_json', jdump(menu))

@bot.callback_query_handler(func=lambda c: c.data in ("SCH_ADD","SCH_LIST"))
def cb_sched(call):
    chat_id = call.message.chat.id
    if call.data == "SCH_ADD":
        STATE[(chat_id, "await_sched")] = {'step':1}
        send_menu(chat_id, "Message bhejo jo schedule करना है.", kb_back(chat_id,'schedule'))
    else:
        arr = sched_get(chat_id)
        text = "Scheduled:
" + "
".join(f"- {a['when']} => {a['text'][:40]}" for a in arr) if arr else "No scheduled."
        send_menu(chat_id, text, kb_back(chat_id,'schedule'))

@bot.message_handler(func=lambda m: STATE.get((m.chat.id, "await_sched")) and bool(m.text))
def sched_flow(m):
    chat_id = m.chat.id
    st = STATE.get((chat_id, "await_sched"))
    if st['step'] == 1:
        st['text'] = m.text.strip()
        st['step'] = 2
        STATE[(chat_id, "await_sched")] = st
        bot.reply_to(m, "Kab bhejna? Format: YYYY-MM-DD HH:MM (UTC)")
    else:
        when = m.text.strip()
        try:
            dt = datetime.strptime(when, "%Y-%m-%d %H:%M")
        except ValueError:
            bot.reply_to(m, "Format galat. Use: YYYY-MM-DD HH:MM"); return
        arr = sched_get(chat_id); arr.append({'when': when, 'text': st['text']})
        sched_set(chat_id, arr)
        STATE.pop((chat_id, "await_sched"), None)
        bot.reply_to(m, f"Scheduled at {when}")

def sched_tick():
    while True:
        try:
            conn = db(); c = conn.cursor()
            c.execute("SELECT chat_id, menu_json FROM settings")
            rows = c.fetchall()
            now_utc = datetime.utcnow()
            for r in rows:
                chat_id = r['chat_id']
                menu = jload(r['menu_json'], {}) or {}
                arr = menu.get('sched', [])
                keep = []
                for item in arr:
                    try:
                        dt = datetime.strptime(item['when'], "%Y-%m-%d %H:%M")
                    except ValueError:
                        continue
                    if now_utc >= dt:
                        try:
                            bot.send_message(chat_id, item['text'])
                        except Exception:
                            pass
                    else:
                        keep.append(item)
                if len(keep) != len(arr):
                    menu['sched'] = keep
                    c2 = conn.cursor()
                    c2.execute("UPDATE settings SET menu_json=? WHERE chat_id=?", (jdump(menu), chat_id))
                    conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"sched tick error: {e}")
        time.sleep(20)

Thread(target=sched_tick, daemon=True).start()



# ---------- Federation-lite ----------
def federation_sync(chats, payload):
    for c in chats:
        try:
            bot.send_message(int(c), f"[Federation] {payload}")
        except Exception:
            pass

@bot.message_handler(commands=['federate'])
def cmd_federate(m):
    parts = m.text.split()
    if ':' not in m.text or len(parts) < 3:
        bot.reply_to(m, "Use: /federate <chat_ids...> : <text>"); return
    ids_part, text_part = m.text.split(':', 1)
    chat_ids = [p for p in ids_part.split()[1:] if p.lstrip('-').isdigit()]
    payload = text_part.strip()
    federation_sync(chat_ids, payload)
    bot.reply_to(m, f"Sent to {len(chat_ids)} chats.")

# ---------- Blacklist commands ----------
@bot.message_handler(commands=['blackadd'])
def cmd_blackadd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Use: /blackadd word"); return
    w = parts[1].strip()
    conn = db(); c = conn.cursor()
    c.execute("INSERT INTO blacklist(chat_id,word) VALUES(?,?)", (str(m.chat.id), w))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Blacklisted: {w}")

@bot.message_handler(commands=['blacklist'])
def cmd_blacklist(m):
    conn = db(); c = conn.cursor()
    c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(m.chat.id),))
    rows = [r['word'] for r in c.fetchall()]; conn.close()
    text = "Blacklist:
" + "
".join(f"- {w}" for w in rows) if rows else "No words."
    for chunk in paginate(text):
        bot.reply_to(m, chunk)

# ---------- Analytics views (extra) ----------
@bot.callback_query_handler(func=lambda c: c.data == "g_stats_more")
def cb_stats_more(call):
    chat_id = call.message.chat.id
    text = tr(chat_id, 'stats_title') + "

" + stats_report(chat_id, 7) + "
—
" + stats_report(chat_id, 30)
    for chunk in paginate(text):
        bot.send_message(chat_id, chunk)

# ---------- Housekeeping ----------
def bg_housekeep():
    while True:
        try:
            conn = db(); c = conn.cursor()
            c.execute("DELETE FROM notes WHERE expires_at>0 AND expires_at<?", (now_ts(),))
            conn.commit(); conn.close()
            # prune flood cache
            now = now_ts()
            for key, arr in list(user_messages.items()):
                user_messages[key] = [t for t in arr if now - t <= 120]
        except Exception as e:
            logging.warning(f"housekeep: {e}")
        time.sleep(60)

Thread(target=bg_housekeep, daemon=True).start()


# ---------- Run ----------
if __name__ == '__main__':
    logging.info("Bot starting...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logging.error(f"polling error: {e}")
            time.sleep(3)