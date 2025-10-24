# -*- coding: utf-8 -*-
# Advanced Telegram Group Manager Bot (single-file, Choreo-safe, no extra libs/APIs)

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
user_messages = defaultdict(list)  # for flood control cache
bot.temp_data = {}  # transient state map

# ---------- Safe utilities ----------
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

# ---------- DB ----------
def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()

    # settings
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        chat_id TEXT PRIMARY KEY,
        lang TEXT DEFAULT 'en',
        welcome_enabled INTEGER DEFAULT 1,
        leave_enabled INTEGER DEFAULT 1,
        flood_window INTEGER DEFAULT 15,
        flood_limit INTEGER DEFAULT 7,
        blacklist_enabled INTEGER DEFAULT 1,
        locks_json TEXT DEFAULT '{}',
        roles_json TEXT DEFAULT '{}',
        captcha_mode TEXT DEFAULT 'math',
        rss_json TEXT DEFAULT '[]',
        plugins_json TEXT DEFAULT '[]',
        subscriptions_json TEXT DEFAULT '[]'
    )
    """)

    # triggers
    cur.execute("""
    CREATE TABLE IF NOT EXISTS triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        pattern TEXT,
        reply TEXT,
        is_regex INTEGER DEFAULT 0
    )
    """)

    # notes
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        key TEXT,
        content TEXT,
        created_at INTEGER,
        expires_at INTEGER
    )
    """)

    # custom commands
    cur.execute("""
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        cmd TEXT,
        body TEXT,
        roles TEXT DEFAULT 'all'
    )
    """)

    # analytics
    cur.execute("""
    CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        action TEXT,
        at INTEGER
    )
    """)

    # blacklist words
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        word TEXT
    )
    """)

    # punishments
    cur.execute("""
    CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        type TEXT,
        until_ts INTEGER
    )
    """)

    # dumps toggles
    cur.execute("""
    CREATE TABLE IF NOT EXISTS dumps (
        chat_id TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        forward_to TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------- Settings helpers ----------
def ensure_settings(chat_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT chat_id FROM settings WHERE chat_id=?", (chat_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO settings(chat_id) VALUES(?)", (chat_id,))
        conn.commit()
    conn.close()

def get_settings(chat_id):
    ensure_settings(chat_id)
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM settings WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return row

def set_setting(chat_id, key, value):
    ensure_settings(chat_id)
    conn = db()
    cur = conn.cursor()
    cur.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, chat_id))
    conn.commit()
    conn.close()

# ---------- Message cache & deletion policy ----------
last_reply_id = {}
def remember_reply(chat_id, message_id):
    last_reply_id[str(chat_id)] = message_id

def delete_previous_reply(chat_id):
    # FIX: never delete before sending response; call only after new message is sent
    pass  # no-op here; managed in send_menu

# ---------- Core send with cleanup ----------
def send_menu(chat_id, text, markup=None, cache_key=None, invalidate_keys=None):
    # invalidate caches
    if invalidate_keys:
        for k in invalidate_keys:
            MENU_CACHE.pop((chat_id, k), None)

    # send new message
    m = bot.send_message(chat_id, text, reply_markup=markup)
    # clean previous reply safely
    prev = last_reply_id.get(str(chat_id))
    if prev and prev != m.message_id:
        try:
            bot.delete_message(chat_id, prev)
        except Exception:
            pass
    remember_reply(chat_id, m.message_id)
    return m

# ---------- Languages (minimal sample; extend as needed) ----------
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
    }
}

def tr(chat_id, key):
    row = get_settings(str(chat_id))
    lang = (row['lang'] if row and row['lang'] else 'en')
    return LANG.get(lang, LANG['en']).get(key, key)

# ---------- Keyboards ----------
def kb(rows):
    markup = types.InlineKeyboardMarkup()
    for r in rows:
        markup.row(*[types.InlineKeyboardButton(text=t, callback_data=d) for t, d in r])
    return markup

def main_menu_kb(chat_id):
    return kb([
        [("🛡️ Verify","verify"), ("👋 Welcome","welcome")],
        [("📬 Triggers","triggers"), ("⏰ Schedule","schedule")],
        [("🧹 Clean","clean"), ("🚫 Block","block")],
        [("🌐 Lang","lang"), ("⚙️ Advanced","advanced")],
        [("👥 Group","group")]
    ])

# ---------- Menus ----------
def show_main(chat_id):
    send_menu(chat_id, tr(chat_id, 'main'), main_menu_kb(chat_id), cache_key='main')

def show_group(chat_id):
    markup = kb([
        [("🔒 Locks","g_locks"), ("👤 Roles","g_roles")],
        [("📈 Analytics","g_stats"), ("🧪 Captcha","g_captcha")],
        [("🧰 Tools","g_tools"), ("🧾 Dumps","g_dumps")],
        [(tr(chat_id,'back'),"back_main")]
    ])
    send_menu(chat_id, tr(chat_id, 'group'), markup, cache_key='group')
    
  # ---------- Analytics ----------
def track(chat_id, user_id, action):
    try:
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT INTO analytics(chat_id,user_id,action,at) VALUES(?,?,?,?)",
                    (str(chat_id), str(user_id or ''), action, now_ts()))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"analytics error: {e}")

def stats_report(chat_id, days=7):
    conn = db()
    cur = conn.cursor()
    since = now_ts() - days*86400
    cur.execute("SELECT action, COUNT(*) c FROM analytics WHERE chat_id=? AND at>=? GROUP BY action ORDER BY c DESC",
                (str(chat_id), since))
    rows = cur.fetchall()
    conn.close()
    lines = [f"{r['action']}: {r['c']}" for r in rows] or ["(no data)"]
    return "
".join(lines)

# ---------- Welcome/Leave ----------
@bot.chat_member_handler()
def on_member(event):
    chat_id = event.chat.id
    row = get_settings(str(chat_id))
    new = event.new_chat_member
    left = event.left_chat_member
    if new and row['welcome_enabled']:
        try:
            name = safe_html(new.user.first_name or "User")
            bot.send_message(chat_id, f"👋 Welcome, {name}!")
            track(chat_id, new.user.id, "welcome")
        except Exception:
            pass
    if left and row['leave_enabled']:
        try:
            name = safe_html(left.first_name or "User")
            bot.send_message(chat_id, f"👋 Bye, {name}.")
            track(chat_id, left.id, "leave")
        except Exception:
            pass

# ---------- Triggers ----------
def match_trigger(chat_id, text):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM triggers WHERE chat_id=?", (str(chat_id),))
    rows = cur.fetchall()
    conn.close()
    for r in rows:
        pat = r['pattern']
        if r['is_regex']:
            try:
                if re.search(pat, text, flags=re.I):
                    return r['reply']
            except re.error:
                continue
        else:
            if pat.lower() in text.lower():
                return r['reply']
    return None

# ---------- Blacklist ----------
def contains_blacklist(chat_id, text):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
    rows = cur.fetchall()
    conn.close()
    t = text.lower()
    for r in rows:
        if r['word'].lower() in t:
            return True
    return False

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
        
        # ---------- Commands ----------
@bot.message_handler(commands=['start'])
def cmd_start(m):
    chat_id = m.chat.id
    track(chat_id, m.from_user.id, "start")
    show_main(chat_id)

@bot.message_handler(commands=['lang'])
def cmd_lang(m):
    chat_id = m.chat.id
    row = get_settings(str(chat_id))
    new = 'hi' if (row['lang'] == 'en') else 'en'
    set_setting(str(chat_id), 'lang', new)
    bot.reply_to(m, f"Lang: {new}")
    track(chat_id, m.from_user.id, "lang_toggle")

# ---------- Inline callbacks ----------
@bot.callback_query_handler(func=lambda c: True)
def cb(call):
    chat_id = call.message.chat.id
    data = call.data

    # Main navigation
    if data == 'back_main':
        show_main(chat_id)
        return
    if data == 'group':
        show_group(chat_id)
        return

    # Group submenu
    if data == 'g_stats':
        text = tr(chat_id, 'stats_title') + "

" + stats_report(chat_id, 7) + "
—
" + stats_report(chat_id, 30)
        send_menu(chat_id, text, kb([[(tr(chat_id,'back'),'group')]]))
        return

    if data == 'welcome':
        row = get_settings(str(chat_id))
        new = 0 if row['welcome_enabled'] else 1
        set_setting(str(chat_id), 'welcome_enabled', new)
        send_menu(chat_id, tr(chat_id, 'welcome_on') if new else tr(chat_id, 'welcome_off'), kb([[(tr(chat_id,'back'),'back_main')]]))
        return

    # Locks/roles/captcha/tools/dumps can be similarly routed to advanced handlers (parts below)
    # Placeholder routing stubs here; implementations continue in next parts.
    if data in ('g_locks','g_roles','g_captcha','g_tools','g_dumps','verify','triggers','schedule','clean','block','lang','advanced'):
        advanced_route(chat_id, data)

def advanced_route(chat_id, key):
    # Filled in advanced sections in later parts
    if key == 'lang':
        row = get_settings(str(chat_id))
        new = 'hi' if (row['lang'] == 'en') else 'en'
        set_setting(str(chat_id), 'lang', new)
        show_main(chat_id)
    else:
        send_menu(chat_id, f"Opening: {key}", kb([[(tr(chat_id,'back'),'back_main')]]))
        
        # ---------- Notes ----------
@bot.message_handler(commands=['note'])
def cmd_note(m):
    # /note key text...
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(m, "Use: /note key content")
        return
    key, content = parts[1], parts[2]
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO notes(chat_id,key,content,created_at,expires_at) VALUES(?,?,?,?,?)",
                (str(m.chat.id), key, content, now_ts(), 0))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Saved note: {key}")
    track(m.chat.id, m.from_user.id, "note_save")

@bot.message_handler(commands=['get'])
def cmd_get(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Use: /get key")
        return
    key = parts[1]
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT content FROM notes WHERE chat_id=? AND key=? ORDER BY id DESC LIMIT 1",
                (str(m.chat.id), key))
    row = cur.fetchone(); conn.close()
    bot.reply_to(m, row['content'] if row else "Not found")
    track(m.chat.id, m.from_user.id, "note_get")

# ---------- Custom commands ----------
@bot.message_handler(func=lambda m: m.text and m.text.startswith('!'))
def custom_cmd(m):
    cmd = m.text.split()[0][1:].lower()
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT body FROM commands WHERE chat_id=? AND cmd=?", (str(m.chat.id), cmd))
    row = cur.fetchone(); conn.close()
    if row:
        bot.reply_to(m, row['body'])
        track(m.chat.id, m.from_user.id, f"cmd_{cmd}")

@bot.message_handler(commands=['addcmd'])
def cmd_addcmd(m):
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(m, "Use: /addcmd name body")
        return
    name, body = parts[1].lower(), parts[2]
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO commands(chat_id,cmd,body) VALUES(?,?,?)", (str(m.chat.id), name, body))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Added command: !{name}")
    track(m.chat.id, m.from_user.id, "addcmd")

# ---------- Blacklist mgmt ----------
@bot.message_handler(commands=['blackadd'])
def cmd_blackadd(m):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(m, "Use: /blackadd word")
        return
    w = parts[1].strip()
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT INTO blacklist(chat_id,word) VALUES(?,?)", (str(m.chat.id), w))
    conn.commit(); conn.close()
    bot.reply_to(m, f"Blacklisted: {w}")
    track(m.chat.id, m.from_user.id, "black_add")

@bot.message_handler(commands=['blacklist'])
def cmd_blacklist(m):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(m.chat.id),))
    rows = cur.fetchall(); conn.close()
    words = ", ".join(r['word'] for r in rows) if rows else "(empty)"
    bot.reply_to(m, words)

# ---------- Dumps toggle ----------
@bot.message_handler(commands=['dump'])
def cmd_dump(m):
    parts = m.text.split(maxsplit=2)
    conn = db(); cur = conn.cursor()
    if len(parts) >= 2 and parts[1].lower() in ('on','off'):
        en = 1 if parts[1].lower() == 'on' else 0
        cur.execute("INSERT INTO dumps(chat_id,enabled) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET enabled=?",
                    (str(m.chat.id), en, en))
        conn.commit(); conn.close()
        bot.reply_to(m, f"Dump: {'on' if en else 'off'}")
    else:
        cur.execute("SELECT enabled,forward_to FROM dumps WHERE chat_id=?", (str(m.chat.id),))
        row = cur.fetchone(); conn.close()
        bot.reply_to(m, f"Dump: {('on' if row and row['enabled'] else 'off')}")
        
     # ---------- RSS minimal (urllib) ----------
def rss_get_items(url, limit=5, timeout=8):
    try:
        req = Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode('utf-8','ignore')
        # naive parse for <item><title> / <link>
        titles = re.findall(r'<title>(.*?)</title>', data, flags=re.I|re.S)
        links = re.findall(r'<link>(.*?)</link>', data, flags=re.I|re.S)
        items = []
        for i in range(1, min(limit+1, len(titles), len(links))):  # skip channel title
            t = re.sub(r'<.*?>','', titles[i]).strip()
            l = re.sub(r'<.*?>','', links[i]).strip()
            if t and l:
                items.append((t, l))
        return items
    except (URLError, HTTPError, Exception) as e:
        logging.warning(f"rss error: {e}")
        return []

def rss_tick():
    while True:
        try:
            conn = db(); cur = conn.cursor()
            cur.execute("SELECT chat_id, rss_json FROM settings")
            rows = cur.fetchall()
            now = now_ts()
            for r in rows:
                chat_id = r['chat_id']
                feeds = jload(r['rss_json'], [])
                for f in feeds or []:
                    url = f.get('url'); interval = clamp(safe_int(f.get('interval', 900), 300, 86400))
                    last = safe_int(f.get('last', 0))
                    if now - last >= interval and url:
                        items = rss_get_items(url, limit=3)
                        for t, l in items:
                            try:
                                bot.send_message(chat_id, f"📰 {safe_html(t)}
{l}")
                            except Exception:
                                pass
                        f['last'] = now
                # persist back
                cur2 = conn.cursor()
                cur2.execute("UPDATE settings SET rss_json=? WHERE chat_id=?", (jdump(feeds), chat_id))
                conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"rss tick error: {e}")
        time.sleep(20)

Thread(target=rss_tick, daemon=True).start()

@bot.message_handler(commands=['rss'])
def cmd_rss(m):
    # /rss add URL 900  or /rss list
    parts = m.text.split()
    if len(parts) == 1:
        row = get_settings(str(m.chat.id))
        feeds = jload(row['rss_json'], [])
        text = "Feeds:
" + "
".join(f"- {f.get('url')} ({f.get('interval','?')}s)" for f in feeds or []) if feeds else "No feeds."
        bot.reply_to(m, text)
        return
    if len(parts) >= 3 and parts[1].lower() == 'add':
        url = parts[2]; interval = clamp(safe_int(parts[3], 900) if len(parts) >=4 else 900, 300, 86400)
        row = get_settings(str(m.chat.id))
        feeds = jload(row['rss_json'], [])
        feeds = feeds or []
        feeds.append({'url': url, 'interval': interval, 'last': 0})
        set_setting(str(m.chat.id), 'rss_json', jdump(feeds))
        bot.reply_to(m, "RSS added.")
        return

# ---------- Captcha (math/text) ----------
pending_captcha = {}

def captcha_new(user_id):
    a,b = random.randint(3,12), random.randint(3,12)
    return f"{a}+{b}=?", a+b

@bot.message_handler(commands=['captcha'])
def cmd_captcha(m):
    q, ans = captcha_new(m.from_user.id)
    pending_captcha[m.from_user.id] = ans
    bot.reply_to(m, f"Solve: {q}")

@bot.message_handler(func=lambda m: m.text and m.from_user.id in pending_captcha)
def captcha_answer(m):
    ans = pending_captcha.get(m.from_user.id)
    if safe_int(m.text) == ans:
        pending_captcha.pop(m.from_user.id, None)
        bot.reply_to(m, "Verified ✅")
        track(m.chat.id, m.from_user.id, "captcha_pass")
    else:
        bot.reply_to(m, "Wrong ❌")
        track(m.chat.id, m.from_user.id, "captcha_fail")

# ---------- Roles & Locks (basic granular) ----------
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

@bot.message_handler(commands=['lock'])
def cmd_lock(m):
    # /lock links on|off
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Use: /lock feature on|off")
        return
    feature = parts[1].lower()
    val = 1 if parts[2].lower()=='on' else 0
    locks = get_locks(m.chat.id)
    locks[feature] = val
    set_locks(m.chat.id, locks)
    bot.reply_to(m, f"Lock {feature}: {'on' if val else 'off'}")
    
    # ---------- Message filters ----------
@bot.message_handler(func=lambda m: bool(m.text))
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

    # triggers
    reply = match_trigger(m.chat.id, m.text)
    if reply:
        bot.reply_to(m, reply)
        track(m.chat.id, m.from_user.id, "trigger_reply")

# ---------- Federation-lite ----------
def federation_sync(chats, payload):
    # No external calls; just local broadcast to listed chats
    for c in chats:
        try:
            bot.send_message(c, f"[Federation] {payload}")
        except Exception:
            pass

@bot.message_handler(commands=['federate'])
def cmd_federate(m):
    # /federate chat_id1 chat_id2 ... : message
    parts = m.text.split()
    if len(parts) < 3:
        bot.reply_to(m, "Use: /federate <chat_ids...> : <text>")
        return
    if ':' not in m.text:
        bot.reply_to(m, "Missing ':' separator")
        return
    ids_part, text_part = m.text.split(':', 1)
    chat_ids = [p for p in ids_part.split()[1:] if p.isdigit()]
    payload = text_part.strip()
    federation_sync(chat_ids, payload)
    bot.reply_to(m, f"Sent to {len(chat_ids)} chats.")

# ---------- Subscriptions ----------
def subs_get(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['subscriptions_json'], []) or []

def subs_set(chat_id, arr):
    set_setting(str(chat_id), 'subscriptions_json', jdump(arr))

@bot.message_handler(commands=['sub'])
def cmd_sub(m):
    # /sub add name 7d | /sub list
    parts = m.text.split()
    if len(parts)==1:
        arr = subs_get(m.chat.id)
        txt = "Subscriptions:
" + "
".join(f"- {a['name']} till {a['until']}" for a in arr) if arr else "No subs."
        bot.reply_to(m, txt); return
    if len(parts)>=4 and parts[1]=='add':
        name = parts[2]
        dur = parts[3].lower()
        days = 30 if dur.endswith('m') else safe_int(dur.rstrip('d'),7)
        until = (datetime.utcnow()+timedelta(days=days)).strftime('%Y-%m-%d')
        arr = subs_get(m.chat.id); arr.append({'name':name,'until':until})
        subs_set(m.chat.id, arr)
        bot.reply_to(m, f"Added sub {name} till {until}")

# ---------- Advanced routes bodies ----------
def advanced_route(chat_id, key):
    if key == 'lang':
        row = get_settings(str(chat_id))
        new = 'hi' if (row['lang'] == 'en') else 'en'
        set_setting(str(chat_id), 'lang', new)
        show_main(chat_id); return

    if key == 'g_tools':
        send_menu(chat_id, "Tools:
- /note
- /get
- /addcmd
- /blackadd
- /blacklist
- /dump on|off
- /rss add <url> <sec>",
                  kb([[(tr(chat_id,'back'),'group')]])); return

    if key == 'g_locks':
        locks = jdump(get_locks(chat_id))
        send_menu(chat_id, f"Locks: {locks}", kb([[("Lock links on","LOCK_links_on"),("Lock links off","LOCK_links_off")],
                                                 [(tr(chat_id,'back'),'group')]])); return

    if key == 'g_roles':
        roles = jdump(get_roles(chat_id))
        send_menu(chat_id, f"Roles: {roles}", kb([[(tr(chat_id,'back'),'group')]])); return

    if key == 'g_captcha':
        send_menu(chat_id, "Captcha: use /captcha to test.", kb([[(tr(chat_id,'back'),'group')]])); return

    if key == 'g_dumps':
        send_menu(chat_id, "Dumps: /dump on|off", kb([[(tr(chat_id,'back'),'group')]])); return

    if key == 'verify':
        send_menu(chat_id, "Verification tools ready.", kb([[(tr(chat_id,'back'),'back_main')]])); return

    if key == 'triggers':
        send_menu(chat_id, "Triggers: add via DB later or commands.", kb([[(tr(chat_id,'back'),'back_main')]])); return

    if key == 'schedule':
        send_menu(chat_id, "Scheduler coming (use RSS interval for demo).", kb([[(tr(chat_id,'back'),'back_main')]])); return

    if key == 'clean':
        send_menu(chat_id, "Clean rules configurable later.", kb([[(tr(chat_id,'back'),'back_main')]])); return

    if key == 'block':
        send_menu(chat_id, "Blacklist: /blackadd, /blacklist", kb([[(tr(chat_id,'back'),'back_main')]])); return

    if key == 'advanced':
        send_menu(chat_id, "Advanced: Roles, Locks, RSS, Dumps, Federation, Subs.", kb([[(tr(chat_id,'back'),'back_main')]])); return
        
        # ---------- Plugin registry (DB-stored, no dynamic import) ----------
def plugins_get(chat_id):
    row = get_settings(str(chat_id))
    return jload(row['plugins_json'], []) or []

def plugins_set(chat_id, arr):
    set_setting(str(chat_id), 'plugins_json', jdump(arr))

@bot.message_handler(commands=['plugin'])
def cmd_plugin(m):
    # /plugin list | /plugin add name on|off
    parts = m.text.split()
    if len(parts)==1 or parts[1]=='list':
        arr = plugins_get(m.chat.id)
        txt = "Plugins:
" + "
".join(f"- {p['name']}: {'on' if p.get('on') else 'off'}" for p in arr) if arr else "No plugins."
        bot.reply_to(m, txt); return
    if len(parts)>=4 and parts[1]=='add':
        name, onoff = parts[2], parts[3].lower()
        arr = plugins_get(m.chat.id)
        found = next((p for p in arr if p['name']==name), None)
        if found: found['on'] = (onoff=='on')
        else: arr.append({'name':name,'on':(onoff=='on')})
        plugins_set(m.chat.id, arr)
        bot.reply_to(m, f"Plugin {name}: {onoff}")

# ---------- MENU_CACHE invalidation helpers ----------
def cache_invalidate_for(chat_id, keys):
    for k in keys:
        MENU_CACHE.pop((chat_id, k), None)

# ---------- Dumps forwarder (if toggled) ----------
@bot.message_handler(content_types=['photo','video','document','audio','sticker','voice','text'])
def dump_forward(m):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT enabled,forward_to FROM dumps WHERE chat_id=?", (str(m.chat.id),))
    row = cur.fetchone(); conn.close()
    if not row or not row['enabled']:
        return
    try:
        # Simple re-send summary
        if getattr(m, 'text', None):
            bot.send_message(m.chat.id, f"[Dump] {safe_html(m.text[:200])}")
        else:
            bot.send_message(m.chat.id, "[Dump] media received.")
    except Exception:
        pass
        
        # ---------- Run ----------
def bg_housekeep():
    # future: clean expired notes/subs/punishments
    while True:
        # expire notes
        try:
            conn = db(); cur = conn.cursor()
            cur.execute("DELETE FROM notes WHERE expires_at>0 AND expires_at<?", (now_ts(),))
            conn.commit(); conn.close()
        except Exception as e:
            logging.warning(f"housekeep: {e}")
        time.sleep(60)

Thread(target=bg_housekeep, daemon=True).start()

if __name__ == '__main__':
    logging.info("Bot starting...")
    # Choreo-safe: non-stop polling with restart-on-error
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logging.error(f"polling error: {e}")
            time.sleep(3)