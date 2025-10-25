#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Telegram Group Management Bot (v7.2+)
Framework: Telebot (pyTelegramBotAPI)
Database: SQLite
Language: Hindi (Default) + English Support
"""

import os
import sys
import logging
import sqlite3
import time
import json
import re
from datetime import datetime, timedelta
from threading import Thread, Lock
from collections import defaultdict
import random
import html

try:
    import telebot
    from telebot import types
except ImportError:
    print("❌ Telebot not installed. Run: pip install pyTelegramBotAPI")
    sys.exit(1)

# ---------- Logging Setup ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# ---------- Bot Token ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN environment variable missing!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ---------- Database Path ----------
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

# ---------- Global State & Locks ----------
STATE = {}  # For multi-step conversations: {(chat_id, key): data}
user_messages = defaultdict(list)  # Flood tracking: {(chat_id, user_id): [timestamps]}
pending_captcha = {}  # {(chat_id, user_id): {'answer': int, 'created_at': ts}}
rejoin_tracker = defaultdict(set)  # {chat_id: {user_id}}
AUTO_CLEAN_QUEUE = []  # [(chat_id, msg_id, delete_at_ts), ...]
AUTO_CLEAN_LOCK = Lock()
CAPTCHA_LOCK = Lock()
FLOOD_LOCK = Lock()

# ---------- Language Dictionary (Hindi Default) ----------
LANG = {
    'hi': {
        'admin_only': '❌ यह कमांड सिर्फ़ admin के लिए है।',
        'setting_updated': '✅ सेटिंग अपडेट हो गई।',
        'error_occurred': '⚠️ कुछ गलत हो गया।',
        'invalid_input': '❌ गलत input।',
        'user_not_found': '❌ User नहीं मिला।',
        'user_warned': '⚠️ {user} को warn किया गया ({count}/3)',
        'user_muted': '🔇 {user} को mute कर दिया ({duration})',
        'user_banned': '🚫 {user} को ban कर दिया',
        'user_kicked': '👢 {user} को kick कर दिया',
        'flood_detected': '⚠️ Spam मत करो! ({count}/{limit})',
        'blacklist_violation': '❌ Blacklist word detect हुआ! Violation: {count}/3',
        'captcha_verify': '🔐 कृपया captcha solve करें:\n{q1} + {q2} = ?',
        'captcha_success': '✅ Captcha verified! Welcome {name}',
        'captcha_failed': '❌ Captcha गलत है।',
        'welcome_message': '👋 Welcome {name}!',
        'goodbye_message': '👋 {name} left the group.',
        'usage': '📖 Usage: {usage}',
        'main_menu': '🏠 Main Menu',
        'back': '⬅️ Back',
        'cancel': '❌ Cancel',
        'confirm': '✅ Confirm',
        'enabled': '✅ Enabled',
        'disabled': '❌ Disabled',
        'nobody': 'Nobody ❌',
        'admin': 'Admin 👮',
        'all': 'All 🌍',
        'note_added': '✅ Note "{key}" add हो गया।',
        'note_deleted': '✅ Note "{key}" delete हो गया।',
        'trigger_added': '✅ Trigger add हो गया।',
        'poll_created': '📊 Poll बन गया।',
        'xp_gained': '🎯 +{points} XP!',
        'rank_display': '🏆 {name}: Rank #{rank}, XP: {xp}',
    },
    'en': {
        'admin_only': '❌ This command is admin-only.',
        'setting_updated': '✅ Setting updated.',
        'error_occurred': '⚠️ Something went wrong.',
        'invalid_input': '❌ Invalid input.',
        'user_not_found': '❌ User not found.',
        'user_warned': '⚠️ {user} warned ({count}/3)',
        'user_muted': '🔇 {user} muted ({duration})',
        'user_banned': '🚫 {user} banned',
        'user_kicked': '👢 {user} kicked',
        'flood_detected': '⚠️ Stop spamming! ({count}/{limit})',
        'blacklist_violation': '❌ Blacklist word detected! Violation: {count}/3',
        'captcha_verify': '🔐 Please solve captcha:\n{q1} + {q2} = ?',
        'captcha_success': '✅ Captcha verified! Welcome {name}',
        'captcha_failed': '❌ Wrong captcha.',
        'welcome_message': '👋 Welcome {name}!',
        'goodbye_message': '👋 {name} left the group.',
        'usage': '📖 Usage: {usage}',
        'main_menu': '🏠 Main Menu',
        'back': '⬅️ Back',
        'cancel': '❌ Cancel',
        'confirm': '✅ Confirm',
        'enabled': '✅ Enabled',
        'disabled': '❌ Disabled',
        'nobody': 'Nobody ❌',
        'admin': 'Admin 👮',
        'all': 'All 🌍',
        'note_added': '✅ Note "{key}" added.',
        'note_deleted': '✅ Note "{key}" deleted.',
        'trigger_added': '✅ Trigger added.',
        'poll_created': '📊 Poll created.',
        'xp_gained': '🎯 +{points} XP!',
        'rank_display': '🏆 {name}: Rank #{rank}, XP: {xp}',
    }
}

def _(chat_id, key, **kwargs):
    """Get translated text"""
    row = get_settings(str(chat_id))
    lang = row.get('lang', 'hi')
    text = LANG.get(lang, LANG['hi']).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ---------- Utility Functions ----------
def now_ts():
    """Current Unix timestamp"""
    return int(time.time())

def jdump(obj):
    """JSON dump"""
    return json.dumps(obj, ensure_ascii=False)

def jload(text, default=None):
    """JSON load with fallback"""
    try:
        return json.loads(text)
    except:
        return default

def safe_html(text):
    """Escape HTML entities"""
    return html.escape(str(text))

# ---------- Database Initialization ----------
def db():
    """Return SQLite connection"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize all tables (existing schema preserved)"""
    conn = db()
    c = conn.cursor()
    
    # Settings table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
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
    )''')
    
    # Triggers table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS triggers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        pattern TEXT,
        reply TEXT,
        is_regex INTEGER DEFAULT 0
    )''')
    
    # Notes table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        key TEXT,
        content TEXT,
        created_at INTEGER,
        expires_at INTEGER DEFAULT 0
    )''')
    
    # Commands table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        cmd TEXT,
        body TEXT,
        roles TEXT DEFAULT 'all'
    )''')
    
    # Blacklist table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        word TEXT
    )''')
    
    # XP table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS xp (
        chat_id TEXT,
        user_id TEXT,
        points INTEGER DEFAULT 0,
        last_at INTEGER,
        PRIMARY KEY (chat_id, user_id)
    )''')
    
    # Polls table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS polls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        question TEXT,
        options_json TEXT,
        multiple INTEGER DEFAULT 0,
        open INTEGER DEFAULT 1,
        created_at INTEGER
    )''')
    
    # Dumps table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS dumps (
        chat_id TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        forward_to TEXT
    )''')
    
    # Analytics table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS analytics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        action TEXT,
        at INTEGER
    )''')
    
    # Punishments table (existing)
    c.execute('''CREATE TABLE IF NOT EXISTS punishments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id TEXT,
        user_id TEXT,
        type TEXT,
        until_ts INTEGER
    )''')
    
    conn.commit()
    conn.close()
    logging.info("✅ Database initialized successfully")

init_db()

# ---------- Settings Helper Functions (existing, preserved) ----------
def ensure_settings(chat_id):
    """Ensure settings row exists for chat"""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT chat_id FROM settings WHERE chat_id=?", (str(chat_id),))
    if not c.fetchone():
        c.execute('''INSERT INTO settings 
            (chat_id, lang, welcome_enabled, leave_enabled, flood_window, flood_limit, 
             blacklist_enabled, locks_json, roles_json, rss_json, plugins_json, 
             subscriptions_json, menu_json) 
            VALUES (?, 'hi', 1, 1, 15, 7, 1, '{}', '{}', '[]', '[]', '[]', '{}')''',
            (str(chat_id),))
        conn.commit()
    conn.close()

def get_settings(chat_id):
    """Get settings row as dict"""
    ensure_settings(str(chat_id))
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM settings WHERE chat_id=?", (str(chat_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {}

def set_setting(chat_id, key, value):
    """Update single setting"""
    ensure_settings(str(chat_id))
    conn = db()
    c = conn.cursor()
    c.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, str(chat_id)))
    conn.commit()
    conn.close()

def menu_get(chat_id):
    """Get menu_json as dict"""
    row = get_settings(str(chat_id))
    return jload(row.get('menu_json', '{}'), {})

def menu_set(chat_id, data):
    """Set menu_json"""
    set_setting(str(chat_id), 'menu_json', jdump(data))

def roles_get(chat_id):
    """Get roles_json as dict"""
    row = get_settings(str(chat_id))
    return jload(row.get('roles_json', '{}'), {})

def roles_set(chat_id, data):
    """Set roles_json"""
    set_setting(str(chat_id), 'roles_json', jdump(data))

def locks_get(chat_id):
    """Get locks_json as dict"""
    row = get_settings(str(chat_id))
    return jload(row.get('locks_json', '{}'), {})

def locks_set(chat_id, data):
    """Set locks_json"""
    set_setting(str(chat_id), 'locks_json', jdump(data))
    
    # ---------- Admin & Permission Check Functions ----------
def is_admin_member(chat_id, user_id):
    """Check if user is admin in the chat"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False

def check_bot_permissions(chat_id):
    """Check if bot has required permissions"""
    try:
        me = bot.get_me()
        member = bot.get_chat_member(chat_id, me.id)
        return {
            'can_restrict': member.can_restrict_members,
            'can_delete': member.can_delete_messages,
            'can_invite': member.can_invite_users,
            'can_pin': member.can_pin_messages,
            'is_admin': member.status == 'administrator'
        }
    except:
        return {}

def notify_missing_permission(chat_id, permission):
    """Notify admin about missing bot permission"""
    try:
        admins = bot.get_chat_administrators(chat_id)
        creator = [a for a in admins if a.status == 'creator']
        if creator:
            bot.send_message(
                creator[0].user.id,
                f"⚠️ Bot को '{permission}' permission नहीं है।\n"
                f"Group: {chat_id}"
            )
    except Exception as e:
        print(f"Error notifying missing permission: {e}")

def has_command_permission(chat_id, user_id, command):
    """Check if user has permission to use command based on roles_json"""
    roles = roles_get(chat_id)
    role = roles.get(command, 'all')  # default: all users can use
    
    if role == 'nobody':
        return False
    elif role == 'admin':
        return is_admin_member(chat_id, user_id)
    elif role == 'all':
        return True
    return False

# ---------- Logging & Analytics ----------
def log_action(chat_id, user_id, action):
    """Log action to analytics table"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO analytics (chat_id, user_id, action, at) VALUES (?,?,?,?)",
                  (str(chat_id), str(user_id), action, now_ts()))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.warning(f"Log action failed: {e}")

def forward_log(chat_id, text):
    """Forward log to configured channel/chat"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT forward_to FROM dumps WHERE chat_id=? AND enabled=1", (str(chat_id),))
        row = c.fetchone()
        conn.close()
        if row and row['forward_to']:
            bot.send_message(row['forward_to'], f"📋 Log from {chat_id}:
{text}")
    except Exception as e:
        logging.warning(f"Forward log failed: {e}")

# ---------- User Info Helpers ----------
def get_user_display_name(user):
    """Get user's display name"""
    if user.username:
        return f"@{user.username}"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name.strip() or f"User{user.id}"

def get_user_mention(user):
    """Get HTML mention for user"""
    name = safe_html(user.first_name or f"User{user.id}")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ---------- Punishment System ----------
def warn_user(chat_id, user_id, reason=""):
    """Warn user with escalation (3 warns → ban)"""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM punishments WHERE chat_id=? AND user_id=? AND type='warn'",
              (str(chat_id), str(user_id)))
    count = c.fetchone()['cnt'] + 1
    
    c.execute("INSERT INTO punishments (chat_id, user_id, type, until_ts) VALUES (?,?,?,?)",
              (str(chat_id), str(user_id), 'warn', now_ts()))
    conn.commit()
    conn.close()
    
    log_action(chat_id, user_id, f"warned:{reason}")
    
    if count >= 3:
        ban_user(chat_id, user_id, "3 warnings")
        return count, 'banned'
    return count, 'warned'

def mute_user(chat_id, user_id, duration_sec=3600):
    """Mute user for specified duration"""
    try:
        until = now_ts() + duration_sec
        bot.restrict_chat_member(
            chat_id, user_id,
            until_date=until,
            can_send_messages=False
        )
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO punishments (chat_id, user_id, type, until_ts) VALUES (?,?,?,?)",
                  (str(chat_id), str(user_id), 'mute', until))
        conn.commit()
        conn.close()
        log_action(chat_id, user_id, f"muted:{duration_sec}s")
        return True
    except Exception as e:
        logging.warning(f"Mute failed: {e}")
        return False

def ban_user(chat_id, user_id, reason=""):
    """Ban user permanently"""
    try:
        bot.ban_chat_member(chat_id, user_id)
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO punishments (chat_id, user_id, type, until_ts) VALUES (?,?,?,?)",
                  (str(chat_id), str(user_id), 'ban', 0))
        conn.commit()
        conn.close()
        log_action(chat_id, user_id, f"banned:{reason}")
        return True
    except Exception as e:
        logging.warning(f"Ban failed: {e}")
        return False

def kick_user(chat_id, user_id):
    """Kick user (ban then unban)"""
    try:
        bot.ban_chat_member(chat_id, user_id)
        bot.unban_chat_member(chat_id, user_id)
        log_action(chat_id, user_id, "kicked")
        return True
    except Exception as e:
        logging.warning(f"Kick failed: {e}")
        return False

def undo_punishment(chat_id, user_id):
    """Undo last punishment for user"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("""SELECT id, type FROM punishments 
                     WHERE chat_id=? AND user_id=? 
                     ORDER BY id DESC LIMIT 1""",
                  (str(chat_id), str(user_id)))
        row = c.fetchone()
        if not row:
            return False, "No punishment found"
        
        pid, ptype = row['id'], row['type']
        c.execute("DELETE FROM punishments WHERE id=?", (pid,))
        conn.commit()
        conn.close()
        
        if ptype == 'ban':
            bot.unban_chat_member(chat_id, user_id)
        elif ptype == 'mute':
            bot.restrict_chat_member(
                chat_id, user_id,
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        
        log_action(chat_id, user_id, f"undo:{ptype}")
        return True, ptype
    except Exception as e:
        logging.warning(f"Undo failed: {e}")
        return False, str(e)

# ---------- Flood Protection ----------
def check_flood(chat_id, user_id):
    """Check if user is flooding, return (is_flood, count, limit)"""
    with FLOOD_LOCK:
        settings = get_settings(chat_id)
        window = settings.get('flood_window', 15)
        limit = settings.get('flood_limit', 7)
        
        key = (chat_id, user_id)
        now = now_ts()
        cutoff = now - window
        
        # Remove old messages
        user_messages[key] = [ts for ts in user_messages[key] if ts > cutoff]
        user_messages[key].append(now)
        
        count = len(user_messages[key])
        return count > limit, count, limit

# ---------- Blacklist System ----------
def check_blacklist(chat_id, text):
    """Check if text contains blacklisted words, return (found, word, violation_count)"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
        words = [row['word'].lower() for row in c.fetchall()]
        conn.close()
        
        text_lower = text.lower()
        for word in words:
            if word in text_lower:
                return True, word, 1
        return False, None, 0
    except:
        return False, None, 0

def add_blacklist_violation(chat_id, user_id):
    """Track blacklist violations, auto-ban on 3rd"""
    conn = db()
    c = conn.cursor()
    c.execute("""SELECT COUNT(*) as cnt FROM punishments 
                 WHERE chat_id=? AND user_id=? AND type='blacklist'""",
              (str(chat_id), str(user_id)))
    count = c.fetchone()['cnt'] + 1
    
    c.execute("INSERT INTO punishments (chat_id, user_id, type, until_ts) VALUES (?,?,?,?)",
              (str(chat_id), str(user_id), 'blacklist', now_ts()))
    conn.commit()
    conn.close()
    
    if count >= 3:
        ban_user(chat_id, user_id, "3 blacklist violations")
        return count, True
    return count, False

# ---------- Locks System ----------
def check_locks(chat_id, message):
    """Check if message violates any locks"""
    locks = locks_get(chat_id)
    
    violations = []
    if locks.get('urls') and message.entities:
        for entity in message.entities:
            if entity.type in ['url', 'text_link']:
                violations.append('urls')
                break
    
    if locks.get('photos') and message.photo:
        violations.append('photos')
    
    if locks.get('videos') and message.video:
        violations.append('videos')
    
    if locks.get('stickers') and message.sticker:
        violations.append('stickers')
    
    if locks.get('forwards') and message.forward_date:
        violations.append('forwards')
    
    if locks.get('documents') and message.document:
        violations.append('documents')
    
    return violations

# ---------- Captcha System ----------
def create_captcha(chat_id, user_id):
    """Create math captcha for new user"""
    with CAPTCHA_LOCK:
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        answer = num1 + num2
        
        pending_captcha[(chat_id, user_id)] = {
            'answer': answer,
            'created_at': now_ts(),
            'q1': num1,
            'q2': num2
        }
        return num1, num2

def verify_captcha(chat_id, user_id, answer):
    """Verify captcha answer"""
    with CAPTCHA_LOCK:
        key = (chat_id, user_id)
        if key not in pending_captcha:
            return False
        
        correct = pending_captcha[key]['answer']
        if int(answer) == correct:
            del pending_captcha[key]
            return True
        return False

def restrict_new_user(chat_id, user_id):
    """Restrict new user until captcha verification"""
    try:
        bot.restrict_chat_member(
            chat_id, user_id,
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        return True
    except Exception as e:
        logging.warning(f"Restrict new user failed: {e}")
        return False

def unrestrict_user(chat_id, user_id):
    """Remove all restrictions from user"""
    try:
        bot.restrict_chat_member(
            chat_id, user_id,
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        return True
    except Exception as e:
        logging.warning(f"Unrestrict failed: {e}")
        return False
        
        # ---------- XP SYSTEM (UPGRADED) ----------
XP_COOLDOWN = 60  # seconds between XP gains

def add_xp(chat_id, user_id, points=10):
    """Add XP to user with cooldown"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT points, last_at FROM xp WHERE chat_id=? AND user_id=?",
                  (str(chat_id), str(user_id)))
        row = c.fetchone()
        
        now = now_ts()
        if row:
            if now - row['last_at'] < XP_COOLDOWN:
                conn.close()
                return False, 0  # Cooldown active
            new_points = row['points'] + points
            c.execute("UPDATE xp SET points=?, last_at=? WHERE chat_id=? AND user_id=?",
                      (new_points, now, str(chat_id), str(user_id)))
        else:
            c.execute("INSERT INTO xp (chat_id, user_id, points, last_at) VALUES (?,?,?,?)",
                      (str(chat_id), str(user_id), points, now))
            new_points = points
        
        conn.commit()
        conn.close()
        return True, new_points
    except Exception as e:
        logging.warning(f"Add XP failed: {e}")
        return False, 0

def get_user_rank(chat_id, user_id):
    """Get user's rank and XP"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT points FROM xp WHERE chat_id=? AND user_id=?",
                  (str(chat_id), str(user_id)))
        row = c.fetchone()
        if not row:
            conn.close()
            return 0, 0
        
        points = row['points']
        c.execute("""SELECT COUNT(*) as rank FROM xp 
                     WHERE chat_id=? AND points > ?""",
                  (str(chat_id), points))
        rank = c.fetchone()['rank'] + 1
        conn.close()
        return rank, points
    except:
        return 0, 0

def get_top_users(chat_id, limit=10):
    """Get top users by XP"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("""SELECT user_id, points FROM xp 
                     WHERE chat_id=? 
                     ORDER BY points DESC LIMIT ?""",
                  (str(chat_id), limit))
        rows = c.fetchall()
        conn.close()
        return [(row['user_id'], row['points']) for row in rows]
    except:
        return []

# ---------- BACKGROUND WORKERS (UPGRADED) ----------

def captcha_expiry_worker():
    """Background worker to auto-kick users who don't solve captcha"""
    TIMEOUT = 180  # 3 minutes
    while True:
        try:
            time.sleep(30)  # Check every 30 seconds
            with CAPTCHA_LOCK:
                now = now_ts()
                to_remove = []
                for (chat_id, user_id), data in pending_captcha.items():
                    if now - data['created_at'] > TIMEOUT:
                        try:
                            bot.ban_chat_member(chat_id, user_id)
                            bot.unban_chat_member(chat_id, user_id)
                            bot.send_message(chat_id, 
                                           f"⏰ Captcha timeout - User {user_id} kicked")
                            to_remove.append((chat_id, user_id))
                            log_action(chat_id, user_id, "captcha_timeout")
                        except:
                            pass
                
                for key in to_remove:
                    if key in pending_captcha:
                        del pending_captcha[key]
        except Exception as e:
            logging.warning(f"Captcha worker error: {e}")

def auto_clean_worker():
    """Background worker to auto-delete scheduled messages"""
    while True:
        try:
            time.sleep(10)  # Check every 10 seconds
            with AUTO_CLEAN_LOCK:
                now = now_ts()
                to_remove = []
                for item in AUTO_CLEAN_QUEUE:
                    chat_id, msg_id, delete_at = item
                    if now >= delete_at:
                        try:
                            bot.delete_message(chat_id, msg_id)
                            to_remove.append(item)
                        except:
                            to_remove.append(item)  # Remove even if delete fails
                
                for item in to_remove:
                    AUTO_CLEAN_QUEUE.remove(item)
        except Exception as e:
            logging.warning(f"Auto clean worker error: {e}")

def sched_worker():
    """Background worker for scheduled tasks"""
    while True:
        try:
            time.sleep(60)  # Check every minute
            # Add scheduled task logic here
            # Example: Check notes with expires_at and delete expired ones
            conn = db()
            c = conn.cursor()
            now = now_ts()
            c.execute("DELETE FROM notes WHERE expires_at > 0 AND expires_at < ?", (now,))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning(f"Scheduler worker error: {e}")

# Start background workers as daemon threads
captcha_thread = Thread(target=captcha_expiry_worker, daemon=True)
captcha_thread.start()

auto_clean_thread = Thread(target=auto_clean_worker, daemon=True)
auto_clean_thread.start()

sched_thread = Thread(target=sched_worker, daemon=True)
sched_thread.start()

logging.info("✅ Background workers started")

# ---------- MENU SYSTEM (UPGRADED) ----------

def build_role_buttons(chat_id, command):
    """Build role selection buttons (Nobody/Admin/All)"""
    roles = roles_get(chat_id)
    current = roles.get(command, 'all')
    
    buttons = []
    for role_type in ['nobody', 'admin', 'all']:
        emoji = '✅' if current == role_type else ''
        label = _(chat_id, role_type)
        if emoji:
            label = f"{emoji} {label}"
        buttons.append(types.InlineKeyboardButton(
            label, callback_data=f"role:{command}:{role_type}"
        ))
    return buttons

def build_toggle_button(chat_id, setting_key, current_value):
    """Build enable/disable toggle button"""
    if current_value:
        label = f"✅ {_(chat_id, 'enabled')}"
        callback = f"toggle:{setting_key}:0"
    else:
        label = f"❌ {_(chat_id, 'disabled')}"
        callback = f"toggle:{setting_key}:1"
    return types.InlineKeyboardButton(label, callback_data=callback)

def send_menu(chat_id, message_id=None, menu_type='main'):
    """Send or edit menu with inline buttons"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if menu_type == 'main':
        text = f"🏠 <b>{_(chat_id, 'main_menu')}</b>

Select an option:"
        markup.add(
            types.InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
            types.InlineKeyboardButton("👥 Users", callback_data="menu:users"),
            types.InlineKeyboardButton("🔐 Locks", callback_data="menu:locks"),
            types.InlineKeyboardButton("📝 Notes", callback_data="menu:notes"),
            types.InlineKeyboardButton("🤖 Triggers", callback_data="menu:triggers"),
            types.InlineKeyboardButton("🎯 XP System", callback_data="menu:xp"),
            types.InlineKeyboardButton("📊 Polls", callback_data="menu:polls"),
            types.InlineKeyboardButton("🚫 Blacklist", callback_data="menu:blacklist"),
            types.InlineKeyboardButton("🔧 Commands", callback_data="menu:commands"),
            types.InlineKeyboardButton("💾 Backup/Restore", callback_data="menu:backup"),
        )
    
    elif menu_type == 'settings':
        settings = get_settings(chat_id)
        text = "⚙️ <b>Settings</b>

"
        text += f"🌐 Language: <code>{settings.get('lang', 'hi')}</code>
"
        text += f"⏱ Flood Window: <code>{settings.get('flood_window', 15)}s</code>
"
        text += f"🚨 Flood Limit: <code>{settings.get('flood_limit', 7)} msgs</code>
"
        
        markup.add(
            build_toggle_button(chat_id, 'welcome_enabled', settings.get('welcome_enabled', 1)),
            build_toggle_button(chat_id, 'leave_enabled', settings.get('leave_enabled', 1)),
            build_toggle_button(chat_id, 'blacklist_enabled', settings.get('blacklist_enabled', 1)),
        )
        markup.add(
            types.InlineKeyboardButton("🌐 Change Language", callback_data="setting:lang"),
            types.InlineKeyboardButton("⏱ Flood Settings", callback_data="setting:flood"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'locks':
        locks = locks_get(chat_id)
        text = "🔐 <b>Locks</b>

Toggle content restrictions:"
        
        markup.add(
            build_toggle_button(chat_id, 'lock_urls', locks.get('urls', False)),
            build_toggle_button(chat_id, 'lock_photos', locks.get('photos', False)),
            build_toggle_button(chat_id, 'lock_videos', locks.get('videos', False)),
            build_toggle_button(chat_id, 'lock_stickers', locks.get('stickers', False)),
            build_toggle_button(chat_id, 'lock_forwards', locks.get('forwards', False)),
            build_toggle_button(chat_id, 'lock_documents', locks.get('documents', False)),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'commands':
        text = "🔧 <b>Command Permissions</b>

Set who can use each command:"
        
        commands = ['warn', 'mute', 'ban', 'kick', 'note', 'trigger', 'poll']
        for cmd in commands:
            markup.add(
                types.InlineKeyboardButton(f"/{cmd}", callback_data=f"cmd_perm:{cmd}"),
            )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type.startswith('cmd_perm:'):
        cmd = menu_type.split(':', 1)[1]
        text = f"🔧 <b>Permission for /{cmd}</b>

Select access level:"
        
        buttons = build_role_buttons(chat_id, cmd)
        markup.add(*buttons)
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:commands"))
    
    elif menu_type == 'notes':
        text = "📝 <b>Notes</b>

Manage saved notes:"
        markup.add(
            types.InlineKeyboardButton("➕ Add Note", callback_data="note:add"),
            types.InlineKeyboardButton("📋 List Notes", callback_data="note:list"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'triggers':
        text = "🤖 <b>Auto Triggers</b>

Manage auto-reply triggers:"
        markup.add(
            types.InlineKeyboardButton("➕ Add Trigger", callback_data="trigger:add"),
            types.InlineKeyboardButton("📋 List Triggers", callback_data="trigger:list"),
            types.InlineKeyboardButton("🧪 Test Regex", callback_data="trigger:test"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'xp':
        text = "🎯 <b>XP System</b>

Manage experience points:"
        markup.add(
            types.InlineKeyboardButton("🏆 Leaderboard", callback_data="xp:top"),
            types.InlineKeyboardButton("📊 My Rank", callback_data="xp:rank"),
            types.InlineKeyboardButton("⚙️ XP Settings", callback_data="xp:settings"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'polls':
        text = "📊 <b>Polls</b>

Create and manage polls:"
        markup.add(
            types.InlineKeyboardButton("➕ Create Poll", callback_data="poll:create"),
            types.InlineKeyboardButton("📋 Active Polls", callback_data="poll:list"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'blacklist':
        text = "🚫 <b>Blacklist</b>

Manage banned words:"
        markup.add(
            types.InlineKeyboardButton("➕ Add Word", callback_data="blacklist:add"),
            types.InlineKeyboardButton("📋 List Words", callback_data="blacklist:list"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    elif menu_type == 'backup':
        text = "💾 <b>Backup & Restore</b>

Manage bot data:"
        markup.add(
            types.InlineKeyboardButton("📤 Export Backup", callback_data="backup:export"),
            types.InlineKeyboardButton("📥 Import Backup", callback_data="backup:import"),
        )
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    else:
        text = "❌ Unknown menu"
        markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:main"))
    
    # Send or edit message
    try:
        if message_id:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        else:
            bot.send_message(chat_id, text, reply_markup=markup)
    except Exception as e:
        logging.warning(f"Send menu failed: {e}")
        
        # ---------- CALLBACK QUERY HANDLER (UPGRADED) ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    """Handle all inline button callbacks"""
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    data = call.data
    msg_id = call.message.message_id
    
    # Admin check for most actions
    if not data.startswith(('xp:rank', 'xp:top', 'poll:vote')):
        if not is_admin_member(chat_id, user_id):
            bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
            return
    
    try:
        # Menu navigation
        if data.startswith('menu:'):
            menu_type = data.split(':', 1)[1]
            send_menu(chat_id, msg_id, menu_type)
            bot.answer_callback_query(call.id)
        
        # Command permission toggle
        elif data.startswith('cmd_perm:'):
            cmd = data.split(':', 1)[1]
            send_menu(chat_id, msg_id, f'cmd_perm:{cmd}')
            bot.answer_callback_query(call.id)
        
        # Role change
        elif data.startswith('role:'):
            parts = data.split(':')
            cmd, role = parts[1], parts[2]
            roles = roles_get(chat_id)
            roles[cmd] = role
            roles_set(chat_id, roles)
            send_menu(chat_id, msg_id, f'cmd_perm:{cmd}')
            bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'), show_alert=True)
        
        # Toggle settings
        elif data.startswith('toggle:'):
            parts = data.split(':')
            key, value = parts[1], int(parts[2])
            
            if key.startswith('lock_'):
                lock_type = key.replace('lock_', '')
                locks = locks_get(chat_id)
                locks[lock_type] = bool(value)
                locks_set(chat_id, locks)
                send_menu(chat_id, msg_id, 'locks')
            else:
                set_setting(chat_id, key, value)
                send_menu(chat_id, msg_id, 'settings')
            
            bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'))
        
        # Note actions
        elif data.startswith('note:'):
            action = data.split(':', 1)[1]
            if action == 'add':
                STATE[(chat_id, 'note_add')] = {'user_id': user_id}
                bot.edit_message_text(
                    "📝 Note का नाम भेजें (key):",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
            elif action == 'list':
                conn = db()
                c = conn.cursor()
                c.execute("SELECT key FROM notes WHERE chat_id=? LIMIT 20", (str(chat_id),))
                notes = [row['key'] for row in c.fetchall()]
                conn.close()
                if notes:
                    text = "📝 <b>Saved Notes:</b>

" + "
".join(f"• <code>{n}</code>" for n in notes)
                    text += f"

<i>Total: {len(notes)}</i>"
                else:
                    text = "📝 कोई notes नहीं हैं।"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:notes"))
                bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
        
        # Trigger actions
        elif data.startswith('trigger:'):
            action = data.split(':', 1)[1]
            if action == 'add':
                STATE[(chat_id, 'trigger_add')] = {'user_id': user_id, 'step': 'pattern'}
                bot.edit_message_text(
                    "🤖 Trigger pattern भेजें:",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
            elif action == 'list':
                conn = db()
                c = conn.cursor()
                c.execute("SELECT pattern, reply FROM triggers WHERE chat_id=? LIMIT 10", 
                         (str(chat_id),))
                triggers = c.fetchall()
                conn.close()
                if triggers:
                    text = "🤖 <b>Active Triggers:</b>

"
                    for t in triggers:
                        text += f"• {safe_html(t['pattern'][:30])} → {safe_html(t['reply'][:30])}
"
                else:
                    text = "🤖 कोई triggers नहीं हैं।"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:triggers"))
                bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
            elif action == 'test':
                STATE[(chat_id, 'trigger_test')] = {'user_id': user_id}
                bot.edit_message_text(
                    "🧪 Test करने के लिए text भेजें:",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
        
        # XP actions
        elif data.startswith('xp:'):
            action = data.split(':', 1)[1]
            if action == 'rank':
                rank, xp = get_user_rank(chat_id, user_id)
                name = get_user_display_name(call.from_user)
                text = _(chat_id, 'rank_display', name=name, rank=rank, xp=xp)
                bot.answer_callback_query(call.id, text, show_alert=True)
            elif action == 'top':
                top = get_top_users(chat_id, 10)
                text = "🏆 <b>Top 10 Users:</b>

"
                for i, (uid, pts) in enumerate(top, 1):
                    try:
                        member = bot.get_chat_member(chat_id, uid)
                        name = get_user_display_name(member.user)
                    except:
                        name = f"User {uid}"
                    text += f"{i}. {safe_html(name)} - {pts} XP
"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:xp"))
                bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
        
        # Poll actions
        elif data.startswith('poll:'):
            action = data.split(':', 1)[1]
            if action == 'create':
                STATE[(chat_id, 'poll_create')] = {'user_id': user_id, 'step': 'question'}
                bot.edit_message_text(
                    "📊 Poll का question भेजें:",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
            elif action == 'list':
                conn = db()
                c = conn.cursor()
                c.execute("SELECT id, question FROM polls WHERE chat_id=? AND open=1 LIMIT 10",
                         (str(chat_id),))
                polls = c.fetchall()
                conn.close()
                if polls:
                    text = "📊 <b>Active Polls:</b>

"
                    for p in polls:
                        text += f"• {safe_html(p['question'][:50])}
"
                else:
                    text = "📊 कोई active polls नहीं हैं।"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:polls"))
                bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
        
        # Blacklist actions
        elif data.startswith('blacklist:'):
            action = data.split(':', 1)[1]
            if action == 'add':
                STATE[(chat_id, 'blacklist_add')] = {'user_id': user_id}
                bot.edit_message_text(
                    "🚫 Blacklist करने के लिए word भेजें:",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
            elif action == 'list':
                conn = db()
                c = conn.cursor()
                c.execute("SELECT word FROM blacklist WHERE chat_id=? LIMIT 20", (str(chat_id),))
                words = [row['word'] for row in c.fetchall()]
                conn.close()
                if words:
                    text = "🚫 <b>Blacklisted Words:</b>

" + "
".join(f"• <code>{w}</code>" for w in words)
                else:
                    text = "🚫 कोई blacklisted words नहीं हैं।"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(_(chat_id, 'back'), callback_data="menu:blacklist"))
                bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id)
        
        # Backup actions
        elif data.startswith('backup:'):
            action = data.split(':', 1)[1]
            if action == 'export':
                bot.answer_callback_query(call.id, "📤 Creating backup...")
                backup_data = export_backup(chat_id)
                bot.send_message(chat_id, f"<code>{backup_data}</code>")
            elif action == 'import':
                STATE[(chat_id, 'backup_import')] = {'user_id': user_id}
                bot.edit_message_text(
                    "📥 Backup JSON को reply करें:",
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id)
        
        # Captcha verification
        elif data.startswith('captcha:'):
            answer = data.split(':', 1)[1]
            if verify_captcha(chat_id, user_id, answer):
                unrestrict_user(chat_id, user_id)
                name = get_user_mention(call.from_user)
                bot.edit_message_text(
                    _(chat_id, 'captcha_success', name=name),
                    chat_id, msg_id
                )
                bot.answer_callback_query(call.id, "✅ Verified!")
            else:
                bot.answer_callback_query(call.id, _(chat_id, 'captcha_failed'), show_alert=True)
        
        else:
            bot.answer_callback_query(call.id, "❓ Unknown action")
    
    except Exception as e:
        logging.warning(f"Callback error: {e}")
        bot.answer_callback_query(call.id, _(chat_id, 'error_occurred'), show_alert=True)

# ---------- COMMAND HANDLERS (UPGRADED) ----------

@bot.message_handler(commands=['start'])
def cmd_start(m):
    """Start command"""
    if m.chat.type == 'private':
        bot.reply_to(m, 
            "👋 <b>Welcome!</b>

"
            "मैं एक advanced group management bot हूँ।
"
            "मुझे किसी group में add करें और /menu use करें।"
        )
    else:
        send_menu(m.chat.id, menu_type='main')

@bot.message_handler(commands=['menu'])
def cmd_menu(m):
    """Show main menu"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    send_menu(m.chat.id, menu_type='main')

@bot.message_handler(commands=['help'])
def cmd_help(m):
    """Show help message"""
    text = """
🤖 <b>Available Commands:</b>

<b>👮 Admin Commands:</b>
• /menu - Main menu
• /warn @user - Warn user
• /mute @user [duration] - Mute user
• /ban @user - Ban user
• /kick @user - Kick user
• /undo @user - Undo last punishment

<b>📝 Content:</b>
• /note <key> <content> - Save note
• /get <key> - Get note
• /trigger <pattern> <reply> - Add trigger

<b>🎯 XP System:</b>
• /rank - Your rank & XP
• /top - Leaderboard

<b>📊 Polls:</b>
• /poll <question> | <opt1> | <opt2> - Create poll

<b>💾 Backup:</b>
• /backup - Export data
• /restore - Import data (reply to backup)

<b>🔧 Settings:</b>
• /lang <hi/en> - Change language
• /locks - View locks status
"""
    bot.reply_to(m, text)

@bot.message_handler(commands=['warn'])
def cmd_warn(m):
    """Warn a user"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'warn'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    else:
        args = m.text.split(maxsplit=1)
        if len(args) > 1 and args[1].startswith('@'):
            # Try to find user by username
            pass
    
    if not target:
        bot.reply_to(m, 
            "❌ Reply to user या username mention करें।
"
            f"{_(m.chat.id, 'usage', usage='/warn @user')}"
        )
        return
    
    count, status = warn_user(m.chat.id, target.id)
    name = get_user_mention(target)
    
    if status == 'banned':
        msg = _(m.chat.id, 'user_banned', user=name)
    else:
        msg = _(m.chat.id, 'user_warned', user=name, count=count)
    
    bot.reply_to(m, msg)
    forward_log(m.chat.id, f"Warned {target.id} by {m.from_user.id}")

@bot.message_handler(commands=['mute'])
def cmd_mute(m):
    """Mute a user"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'mute'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    target = None
    duration = 3600  # default 1 hour
    
    if m.reply_to_message:
        target = m.reply_to_message.from_user
        args = m.text.split()
        if len(args) > 1:
            try:
                duration = int(args[1]) * 60  # minutes to seconds
            except:
                pass
    
    if not target:
        bot.reply_to(m, 
            "❌ Reply to user करें।
"
            f"{_(m.chat.id, 'usage', usage='/mute @user [minutes]')}"
        )
        return
    
    if mute_user(m.chat.id, target.id, duration):
        name = get_user_mention(target)
        duration_str = f"{duration//60}m" if duration < 3600 else f"{duration//3600}h"
        bot.reply_to(m, _(m.chat.id, 'user_muted', user=name, duration=duration_str))
        forward_log(m.chat.id, f"Muted {target.id} for {duration}s by {m.from_user.id}")
    else:
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['ban'])
def cmd_ban(m):
    """Ban a user"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'ban'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    
    if not target:
        bot.reply_to(m, 
            "❌ Reply to user करें।
"
            f"{_(m.chat.id, 'usage', usage='/ban @user')}"
        )
        return
    
    if ban_user(m.chat.id, target.id, "manual ban"):
        name = get_user_mention(target)
        bot.reply_to(m, _(m.chat.id, 'user_banned', user=name))
        forward_log(m.chat.id, f"Banned {target.id} by {m.from_user.id}")
    else:
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['kick'])
def cmd_kick(m):
    """Kick a user"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'kick'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    
    if not target:
        bot.reply_to(m, 
            "❌ Reply to user करें।
"
            f"{_(m.chat.id, 'usage', usage='/kick @user')}"
        )
        return
    
    if kick_user(m.chat.id, target.id):
        name = get_user_mention(target)
        bot.reply_to(m, _(m.chat.id, 'user_kicked', user=name))
        forward_log(m.chat.id, f"Kicked {target.id} by {m.from_user.id}")
    else:
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['undo'])
def cmd_undo(m):
    """Undo last punishment"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    target = None
    if m.reply_to_message:
        target = m.reply_to_message.from_user
    
    if not target:
        bot.reply_to(m, "❌ Reply to user करें।")
        return
    
    success, result = undo_punishment(m.chat.id, target.id)
    if success:
        name = get_user_mention(target)
        bot.reply_to(m, f"✅ {name} का {result} punishment undo हो गया।")
    else:
        bot.reply_to(m, f"❌ {result}")
        
        # ---------- NOTE COMMANDS ----------
@bot.message_handler(commands=['note'])
def cmd_note(m):
    """Save a note"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'note'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(m, 
            f"❌ Format गलत है।
"
            f"{_(m.chat.id, 'usage', usage='/note <key> <content>')}"
        )
        return
    
    key = args[1]
    content = args[2]
    
    try:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO notes (chat_id, key, content, created_at) VALUES (?,?,?,?)",
                  (str(m.chat.id), key, content, now_ts()))
        conn.commit()
        conn.close()
        bot.reply_to(m, _(m.chat.id, 'note_added', key=key))
        log_action(m.chat.id, m.from_user.id, f"note_added:{key}")
    except Exception as e:
        logging.warning(f"Save note failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['get'])
def cmd_get(m):
    """Get a note"""
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/get <key>')}")
        return
    
    key = args[1]
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT content FROM notes WHERE chat_id=? AND key=?", 
                  (str(m.chat.id), key))
        row = c.fetchone()
        conn.close()
        
        if row:
            bot.reply_to(m, safe_html(row['content']))
        else:
            bot.reply_to(m, f"❌ Note '{key}' नहीं मिला।")
    except Exception as e:
        logging.warning(f"Get note failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['delnote'])
def cmd_delnote(m):
    """Delete a note"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/delnote <key>')}")
        return
    
    key = args[1]
    try:
        conn = db()
        c = conn.cursor()
        c.execute("DELETE FROM notes WHERE chat_id=? AND key=?", 
                  (str(m.chat.id), key))
        conn.commit()
        conn.close()
        bot.reply_to(m, _(m.chat.id, 'note_deleted', key=key))
        log_action(m.chat.id, m.from_user.id, f"note_deleted:{key}")
    except Exception as e:
        logging.warning(f"Delete note failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- TRIGGER COMMANDS ----------
@bot.message_handler(commands=['trigger'])
def cmd_trigger(m):
    """Add auto-reply trigger"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'trigger'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(m, 
            f"❌ Format गलत है।
"
            f"{_(m.chat.id, 'usage', usage='/trigger <pattern> <reply>')}"
        )
        return
    
    pattern = args[1]
    reply = args[2]
    is_regex = 0
    
    # Check if pattern looks like regex
    if any(c in pattern for c in ['^', '$', '[', ']', '(', ')', '*', '+', '?', '|']):
        is_regex = 1
        # Test regex validity
        try:
            re.compile(pattern)
        except:
            bot.reply_to(m, "❌ Invalid regex pattern!")
            return
    
    try:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO triggers (chat_id, pattern, reply, is_regex) VALUES (?,?,?,?)",
                  (str(m.chat.id), pattern, reply, is_regex))
        conn.commit()
        conn.close()
        bot.reply_to(m, _(m.chat.id, 'trigger_added'))
        log_action(m.chat.id, m.from_user.id, f"trigger_added:{pattern}")
    except Exception as e:
        logging.warning(f"Add trigger failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['triggers'])
def cmd_triggers(m):
    """List all triggers"""
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT id, pattern, reply, is_regex FROM triggers WHERE chat_id=?",
                  (str(m.chat.id),))
        triggers = c.fetchall()
        conn.close()
        
        if not triggers:
            bot.reply_to(m, "🤖 कोई triggers नहीं हैं।")
            return
        
        text = "🤖 <b>Active Triggers:</b>

"
        for t in triggers:
            regex_mark = "🔧" if t['is_regex'] else "📝"
            text += f"{regex_mark} <code>{t['id']}</code>: {safe_html(t['pattern'][:30])}
"
            text += f"   → {safe_html(t['reply'][:50])}

"
        
        text += f"<i>Total: {len(triggers)}</i>
"
        text += f"
{_(m.chat.id, 'usage', usage='/deltrigger <id>')}"
        bot.reply_to(m, text)
    except Exception as e:
        logging.warning(f"List triggers failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['deltrigger'])
def cmd_deltrigger(m):
    """Delete a trigger"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/deltrigger <id>')}")
        return
    
    try:
        trigger_id = int(args[1])
        conn = db()
        c = conn.cursor()
        c.execute("DELETE FROM triggers WHERE id=? AND chat_id=?",
                  (trigger_id, str(m.chat.id)))
        conn.commit()
        conn.close()
        bot.reply_to(m, f"✅ Trigger {trigger_id} delete हो गया।")
        log_action(m.chat.id, m.from_user.id, f"trigger_deleted:{trigger_id}")
    except ValueError:
        bot.reply_to(m, "❌ Invalid trigger ID")
    except Exception as e:
        logging.warning(f"Delete trigger failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- XP COMMANDS ----------
@bot.message_handler(commands=['rank'])
def cmd_rank(m):
    """Show user's rank and XP"""
    rank, xp = get_user_rank(m.chat.id, m.from_user.id)
    name = get_user_display_name(m.from_user)
    text = _(m.chat.id, 'rank_display', name=name, rank=rank, xp=xp)
    bot.reply_to(m, text)

@bot.message_handler(commands=['top'])
def cmd_top(m):
    """Show top 10 users"""
    top = get_top_users(m.chat.id, 10)
    if not top:
        bot.reply_to(m, "🏆 अभी तक कोई XP नहीं है।")
        return
    
    text = "🏆 <b>Top 10 Users:</b>

"
    for i, (uid, pts) in enumerate(top, 1):
        try:
            member = bot.get_chat_member(m.chat.id, uid)
            name = get_user_display_name(member.user)
        except:
            name = f"User {uid}"
        
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        text += f"{medal} {safe_html(name)} - <b>{pts}</b> XP
"
    
    bot.reply_to(m, text)

# ---------- POLL COMMANDS ----------
@bot.message_handler(commands=['poll'])
def cmd_poll(m):
    """Create a poll"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not has_command_permission(m.chat.id, m.from_user.id, 'poll'):
        bot.reply_to(m, "❌ You don't have permission to use this command.")
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2 or '|' not in args[1]:
        bot.reply_to(m, 
            f"❌ Format गलत है।
"
            f"{_(m.chat.id, 'usage', usage='/poll <question> | <opt1> | <opt2> | ...')}"
        )
        return
    
    parts = [p.strip() for p in args[1].split('|')]
    question = parts[0]
    options = parts[1:]
    
    if len(options) < 2:
        bot.reply_to(m, "❌ कम से कम 2 options चाहिए।")
        return
    
    try:
        conn = db()
        c = conn.cursor()
        options_json = jdump({'options': options, 'votes': {i: [] for i in range(len(options))}})
        c.execute("INSERT INTO polls (chat_id, question, options_json, created_at, open) VALUES (?,?,?,?,1)",
                  (str(m.chat.id), question, options_json, now_ts()))
        poll_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Send poll with inline buttons
        markup = types.InlineKeyboardMarkup(row_width=2)
        for i, opt in enumerate(options):
            markup.add(types.InlineKeyboardButton(
                f"{opt} (0)", callback_data=f"poll:vote:{poll_id}:{i}"
            ))
        markup.add(types.InlineKeyboardButton("🔒 Close Poll", callback_data=f"poll:close:{poll_id}"))
        
        bot.send_message(m.chat.id, f"📊 <b>{safe_html(question)}</b>", reply_markup=markup)
        bot.reply_to(m, _(m.chat.id, 'poll_created'))
        log_action(m.chat.id, m.from_user.id, f"poll_created:{poll_id}")
    except Exception as e:
        logging.warning(f"Create poll failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- BLACKLIST COMMANDS ----------
@bot.message_handler(commands=['blacklist'])
def cmd_blacklist(m):
    """Add word to blacklist"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/blacklist <word>')}")
        return
    
    word = args[1].lower()
    try:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO blacklist (chat_id, word) VALUES (?,?)",
                  (str(m.chat.id), word))
        conn.commit()
        conn.close()
        bot.reply_to(m, f"✅ '{word}' blacklist में add हो गया।")
        log_action(m.chat.id, m.from_user.id, f"blacklist_added:{word}")
    except Exception as e:
        logging.warning(f"Add blacklist failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['unblacklist'])
def cmd_unblacklist(m):
    """Remove word from blacklist"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/unblacklist <word>')}")
        return
    
    word = args[1].lower()
    try:
        conn = db()
        c = conn.cursor()
        c.execute("DELETE FROM blacklist WHERE chat_id=? AND word=?",
                  (str(m.chat.id), word))
        conn.commit()
        conn.close()
        bot.reply_to(m, f"✅ '{word}' blacklist से remove हो गया।")
        log_action(m.chat.id, m.from_user.id, f"blacklist_removed:{word}")
    except Exception as e:
        logging.warning(f"Remove blacklist failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- LANGUAGE & SETTINGS ----------
@bot.message_handler(commands=['lang'])
def cmd_lang(m):
    """Change bot language"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2 or args[1] not in ['hi', 'en']:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/lang <hi|en>')}")
        return
    
    lang = args[1]
    set_setting(m.chat.id, 'lang', lang)
    bot.reply_to(m, _(m.chat.id, 'setting_updated'))

@bot.message_handler(commands=['locks'])
def cmd_locks(m):
    """Show locks status"""
    locks = locks_get(m.chat.id)
    text = "🔐 <b>Current Locks:</b>

"
    
    lock_types = ['urls', 'photos', 'videos', 'stickers', 'forwards', 'documents']
    for lock_type in lock_types:
        status = "🔒" if locks.get(lock_type) else "🔓"
        text += f"{status} {lock_type.title()}
"
    
    text += f"
{_(m.chat.id, 'usage', usage='/lock <type> | /unlock <type>')}"
    bot.reply_to(m, text)

@bot.message_handler(commands=['lock'])
def cmd_lock(m):
    """Lock content type"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/lock <urls|photos|videos|stickers|forwards|documents>')}")
        return
    
    lock_type = args[1].lower()
    valid_types = ['urls', 'photos', 'videos', 'stickers', 'forwards', 'documents']
    
    if lock_type not in valid_types:
        bot.reply_to(m, f"❌ Invalid type. Valid: {', '.join(valid_types)}")
        return
    
    locks = locks_get(m.chat.id)
    locks[lock_type] = True
    locks_set(m.chat.id, locks)
    bot.reply_to(m, f"🔒 {lock_type.title()} locked.")
    log_action(m.chat.id, m.from_user.id, f"locked:{lock_type}")

@bot.message_handler(commands=['unlock'])
def cmd_unlock(m):
    """Unlock content type"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, f"{_(m.chat.id, 'usage', usage='/unlock <type>')}")
        return
    
    lock_type = args[1].lower()
    valid_types = ['urls', 'photos', 'videos', 'stickers', 'forwards', 'documents']
    
    if lock_type not in valid_types:
        bot.reply_to(m, f"❌ Invalid type. Valid: {', '.join(valid_types)}")
        return
    
    locks = locks_get(m.chat.id)
    locks[lock_type] = False
    locks_set(m.chat.id, locks)
    bot.reply_to(m, f"🔓 {lock_type.title()} unlocked.")
    log_action(m.chat.id, m.from_user.id, f"unlocked:{lock_type}")
    
    # ---------- BACKUP & RESTORE ----------
def export_backup(chat_id):
    """Export all data for a chat"""
    try:
        conn = db()
        c = conn.cursor()
        
        backup = {}
        tables = ['settings', 'triggers', 'notes', 'commands', 'blacklist', 'xp', 'polls']
        
        for table in tables:
            c.execute(f"SELECT * FROM {table} WHERE chat_id=?", (str(chat_id),))
            rows = c.fetchall()
            backup[table] = [dict(row) for row in rows]
        
        conn.close()
        return jdump(backup)
    except Exception as e:
        logging.warning(f"Export backup failed: {e}")
        return "{}"

def import_backup(chat_id, data):
    """Import backup data"""
    try:
        backup = jload(data, {})
        conn = db()
        c = conn.cursor()
        
        for table, rows in backup.items():
            if table not in ['settings', 'triggers', 'notes', 'commands', 'blacklist', 'xp', 'polls']:
                continue
            
            for row in rows:
                row['chat_id'] = str(chat_id)  # Override chat_id
                
                if table == 'settings':
                    c.execute("""INSERT OR REPLACE INTO settings 
                        (chat_id, lang, welcome_enabled, leave_enabled, flood_window, flood_limit,
                         blacklist_enabled, locks_json, roles_json, rss_json, plugins_json,
                         subscriptions_json, menu_json) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row.get('chat_id'), row.get('lang', 'hi'), 
                         row.get('welcome_enabled', 1), row.get('leave_enabled', 1),
                         row.get('flood_window', 15), row.get('flood_limit', 7),
                         row.get('blacklist_enabled', 1), row.get('locks_json', '{}'),
                         row.get('roles_json', '{}'), row.get('rss_json', '[]'),
                         row.get('plugins_json', '[]'), row.get('subscriptions_json', '[]'),
                         row.get('menu_json', '{}')))
                
                elif table == 'triggers':
                    c.execute("INSERT INTO triggers (chat_id, pattern, reply, is_regex) VALUES (?,?,?,?)",
                             (row['chat_id'], row['pattern'], row['reply'], row.get('is_regex', 0)))
                
                elif table == 'notes':
                    c.execute("INSERT INTO notes (chat_id, key, content, created_at, expires_at) VALUES (?,?,?,?,?)",
                             (row['chat_id'], row['key'], row['content'], 
                              row.get('created_at', now_ts()), row.get('expires_at', 0)))
                
                elif table == 'blacklist':
                    c.execute("INSERT INTO blacklist (chat_id, word) VALUES (?,?)",
                             (row['chat_id'], row['word']))
                
                elif table == 'xp':
                    c.execute("INSERT OR REPLACE INTO xp (chat_id, user_id, points, last_at) VALUES (?,?,?,?)",
                             (row['chat_id'], row['user_id'], row['points'], row.get('last_at', now_ts())))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.warning(f"Import backup failed: {e}")
        return False

@bot.message_handler(commands=['backup'])
def cmd_backup(m):
    """Export backup"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    backup_data = export_backup(m.chat.id)
    bot.send_message(m.chat.id, 
        f"💾 <b>Backup Data</b>

"
        f"<code>{safe_html(backup_data[:4000])}</code>

"
        f"<i>Save this data and use /restore to import</i>"
    )
    log_action(m.chat.id, m.from_user.id, "backup_exported")

@bot.message_handler(commands=['restore'])
def cmd_restore(m):
    """Import backup"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not m.reply_to_message or not m.reply_to_message.text:
        bot.reply_to(m, "❌ Backup JSON को reply करें।")
        return
    
    data = m.reply_to_message.text.strip()
    if import_backup(m.chat.id, data):
        bot.reply_to(m, "✅ Backup restore हो गया!")
        log_action(m.chat.id, m.from_user.id, "backup_restored")
    else:
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- NEW MEMBER HANDLER (CAPTCHA) ----------
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(m):
    """Handle new members with captcha"""
    settings = get_settings(m.chat.id)
    
    for user in m.new_chat_members:
        # Skip bots
        if user.is_bot:
            continue
        
        # Check rejoin
        if user.id in rejoin_tracker[m.chat.id]:
            ban_user(m.chat.id, user.id, "rejoin detected")
            try:
                bot.delete_message(m.chat.id, m.message_id)
            except:
                pass
            continue
        
        rejoin_tracker[m.chat.id].add(user.id)
        
        # Restrict user
        restrict_new_user(m.chat.id, user.id)
        
        # Create captcha
        q1, q2 = create_captcha(m.chat.id, user.id)
        
        markup = types.InlineKeyboardMarkup(row_width=3)
        # Generate 3 options (1 correct, 2 wrong)
        correct = q1 + q2
        options = [correct]
        while len(options) < 3:
            wrong = random.randint(correct - 5, correct + 5)
            if wrong not in options and wrong > 0:
                options.append(wrong)
        random.shuffle(options)
        
        buttons = [
            types.InlineKeyboardButton(str(opt), callback_data=f"captcha:{opt}")
            for opt in options
        ]
        markup.add(*buttons)
        
        name = get_user_mention(user)
        text = _(m.chat.id, 'captcha_verify', q1=q1, q2=q2)
        text = f"{name}

{text}"
        
        try:
            sent = bot.send_message(m.chat.id, text, reply_markup=markup)
            # Auto-delete captcha message after 3 minutes
            with AUTO_CLEAN_LOCK:
                AUTO_CLEAN_QUEUE.append((m.chat.id, sent.message_id, now_ts() + 180))
        except Exception as e:
            logging.warning(f"Send captcha failed: {e}")
        
        # Send welcome if enabled
        if settings.get('welcome_enabled', 1):
            welcome_text = _(m.chat.id, 'welcome_message', name=name)
            try:
                bot.send_message(m.chat.id, welcome_text)
            except:
                pass

# ---------- LEFT MEMBER HANDLER ----------
@bot.message_handler(content_types=['left_chat_member'])
def handle_left_member(m):
    """Handle member leaving"""
    settings = get_settings(m.chat.id)
    
    if settings.get('leave_enabled', 1):
        user = m.left_chat_member
        name = get_user_display_name(user)
        text = _(m.chat.id, 'goodbye_message', name=safe_html(name))
        try:
            bot.send_message(m.chat.id, text)
        except:
            pass

# ---------- REGULAR MESSAGE HANDLER ----------
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'sticker', 'document'])
def handle_messages(m):
    """Handle all regular messages"""
    # Skip if not a group
    if m.chat.type not in ['group', 'supergroup']:
        return
    
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    # Skip if admin
    if is_admin_member(chat_id, user_id):
        return
    
    settings = get_settings(chat_id)
    
    # Check locks
    violations = check_locks(chat_id, m)
    if violations:
        try:
            bot.delete_message(chat_id, m.message_id)
            bot.send_message(chat_id, 
                f"🔒 {get_user_mention(m.from_user)}, "
                f"{', '.join(violations)} locked हैं।")
        except Exception as e:
            logging.warning(f"Delete locked content failed: {e}")
        return
    
    # Check blacklist
    if m.text and settings.get('blacklist_enabled', 1):
        found, word, _ = check_blacklist(chat_id, m.text)
        if found:
            try:
                bot.delete_message(chat_id, m.message_id)
                count, banned = add_blacklist_violation(chat_id, user_id)
                
                if banned:
                    bot.send_message(chat_id, 
                        _(chat_id, 'user_banned', user=get_user_mention(m.from_user)))
                else:
                    bot.send_message(chat_id, 
                        _(chat_id, 'blacklist_violation', count=count))
            except Exception as e:
                logging.warning(f"Handle blacklist failed: {e}")
            return
    
    # Check flood
    is_flood, count, limit = check_flood(chat_id, user_id)
    if is_flood:
        # Escalate: warn → mute → ban
        conn = db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM punishments WHERE chat_id=? AND user_id=? AND type='flood'",
                  (str(chat_id), str(user_id)))
        flood_count = c.fetchone()['cnt']
        conn.close()
        
        if flood_count == 0:
            warn_user(chat_id, user_id, "flooding")
            bot.send_message(chat_id, 
                _(chat_id, 'flood_detected', count=count, limit=limit))
        elif flood_count == 1:
            mute_user(chat_id, user_id, 600)  # 10 minutes
            bot.send_message(chat_id, 
                _(chat_id, 'user_muted', user=get_user_mention(m.from_user), duration='10m'))
        else:
            ban_user(chat_id, user_id, "repeated flooding")
            bot.send_message(chat_id, 
                _(chat_id, 'user_banned', user=get_user_mention(m.from_user)))
        
        try:
            bot.delete_message(chat_id, m.message_id)
        except:
            pass
        return
    
    # Check triggers (auto-reply)
    if m.text:
        try:
            conn = db()
            c = conn.cursor()
            c.execute("SELECT pattern, reply, is_regex FROM triggers WHERE chat_id=?",
                     (str(chat_id),))
            triggers = c.fetchall()
            conn.close()
            
            for trigger in triggers:
                matched = False
                if trigger['is_regex']:
                    try:
                        if re.search(trigger['pattern'], m.text, re.IGNORECASE):
                            matched = True
                    except:
                        pass
                else:
                    if trigger['pattern'].lower() in m.text.lower():
                        matched = True
                
                if matched:
                    bot.reply_to(m, safe_html(trigger['reply']))
                    log_action(chat_id, user_id, f"trigger_matched:{trigger['pattern']}")
                    break
        except Exception as e:
            logging.warning(f"Check triggers failed: {e}")
    
    # Add XP for activity
    if m.text and len(m.text) > 10:
        success, points = add_xp(chat_id, user_id, 10)
        if success and random.random() < 0.1:  # 10% chance to notify
            bot.send_message(chat_id, _(chat_id, 'xp_gained', points=10))

# ---------- STATE-BASED MESSAGE HANDLER ----------
@bot.message_handler(func=lambda m: (m.chat.id, 'note_add') in STATE)
def handle_note_add(m):
    """Handle note addition flow"""
    state = STATE.get((m.chat.id, 'note_add'))
    if not state:
        return
    
    if 'key' not in state:
        state['key'] = m.text.strip()
        STATE[(m.chat.id, 'note_add')] = state
        bot.reply_to(m, "📝 अब note का content भेजें:")
    else:
        key = state['key']
        content = m.text.strip()
        
        try:
            conn = db()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO notes (chat_id, key, content, created_at) VALUES (?,?,?,?)",
                      (str(m.chat.id), key, content, now_ts()))
            conn.commit()
            conn.close()
            bot.reply_to(m, _(m.chat.id, 'note_added', key=key))
            log_action(m.chat.id, m.from_user.id, f"note_added:{key}")
        except Exception as e:
            logging.warning(f"Save note failed: {e}")
            bot.reply_to(m, _(m.chat.id, 'error_occurred'))
        
        del STATE[(m.chat.id, 'note_add')]

@bot.message_handler(func=lambda m: (m.chat.id, 'trigger_add') in STATE)
def handle_trigger_add(m):
    """Handle trigger addition flow"""
    state = STATE.get((m.chat.id, 'trigger_add'))
    if not state:
        return
    
    if state['step'] == 'pattern':
        state['pattern'] = m.text.strip()
        state['step'] = 'reply'
        STATE[(m.chat.id, 'trigger_add')] = state
        bot.reply_to(m, "🤖 अब trigger का reply भेजें:")
    else:
        pattern = state['pattern']
        reply = m.text.strip()
        is_regex = 0
        
        if any(c in pattern for c in ['^', '$', '[', ']', '(', ')', '*', '+', '?', '|']):
            is_regex = 1
            try:
                re.compile(pattern)
            except:
                bot.reply_to(m, "❌ Invalid regex pattern!")
                del STATE[(m.chat.id, 'trigger_add')]
                return
        
        try:
            conn = db()
            c = conn.cursor()
            c.execute("INSERT INTO triggers (chat_id, pattern, reply, is_regex) VALUES (?,?,?,?)",
                      (str(m.chat.id), pattern, reply, is_regex))
            conn.commit()
            conn.close()
            bot.reply_to(m, _(m.chat.id, 'trigger_added'))
            log_action(m.chat.id, m.from_user.id, f"trigger_added:{pattern}")
        except Exception as e:
            logging.warning(f"Add trigger failed: {e}")
            bot.reply_to(m, _(m.chat.id, 'error_occurred'))
        
        del STATE[(m.chat.id, 'trigger_add')]

@bot.message_handler(func=lambda m: (m.chat.id, 'trigger_test') in STATE)
def handle_trigger_test(m):
    """Handle trigger testing flow"""
    state = STATE.get((m.chat.id, 'trigger_test'))
    if not state:
        return
    
    test_text = m.text.strip()
    
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT pattern, reply, is_regex FROM triggers WHERE chat_id=?",
                 (str(m.chat.id),))
        triggers = c.fetchall()
        conn.close()
        
        matches = []
        for trigger in triggers:
            matched = False
            if trigger['is_regex']:
                try:
                    if re.search(trigger['pattern'], test_text, re.IGNORECASE):
                        matched = True
                except:
                    pass
            else:
                if trigger['pattern'].lower() in test_text.lower():
                    matched = True
            
            if matched:
                matches.append((trigger['pattern'], trigger['reply']))
        
        if matches:
            text = "✅ <b>Matching Triggers:</b>

"
            for pattern, reply in matches:
                text += f"• <code>{safe_html(pattern)}</code>
"
                text += f"  → {safe_html(reply)}

"
        else:
            text = "❌ कोई trigger match नहीं हुआ।"
        
        bot.reply_to(m, text)
    except Exception as e:
        logging.warning(f"Test trigger failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))
    
    del STATE[(m.chat.id, 'trigger_test')]

@bot.message_handler(func=lambda m: (m.chat.id, 'blacklist_add') in STATE)
def handle_blacklist_add(m):
    """Handle blacklist addition flow"""
    state = STATE.get((m.chat.id, 'blacklist_add'))
    if not state:
        return
    
    word = m.text.strip().lower()
    
    try:
        conn = db()
        c = conn.cursor()
        c.execute("INSERT INTO blacklist (chat_id, word) VALUES (?,?)",
                  (str(m.chat.id), word))
        conn.commit()
        conn.close()
        bot.reply_to(m, f"✅ '{word}' blacklist में add हो गया।")
        log_action(m.chat.id, m.from_user.id, f"blacklist_added:{word}")
    except Exception as e:
        logging.warning(f"Add blacklist failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))
    
    del STATE[(m.chat.id, 'blacklist_add')]

@bot.message_handler(func=lambda m: (m.chat.id, 'poll_create') in STATE)
def handle_poll_create(m):
    """Handle poll creation flow"""
    state = STATE.get((m.chat.id, 'poll_create'))
    if not state:
        return
    
    if state['step'] == 'question':
        state['question'] = m.text.strip()
        state['step'] = 'options'
        state['options'] = []
        STATE[(m.chat.id, 'poll_create')] = state
        bot.reply_to(m, "📊 Poll options भेजें (एक line में एक option, 'done' लिखकर finish करें):")
    else:
        text = m.text.strip()
        if text.lower() == 'done':
            if len(state['options']) < 2:
                bot.reply_to(m, "❌ कम से कम 2 options चाहिए।")
                return
            
            question = state['question']
            options = state['options']
            
            try:
                conn = db()
                c = conn.cursor()
                options_json = jdump({'options': options, 'votes': {i: [] for i in range(len(options))}})
                c.execute("INSERT INTO polls (chat_id, question, options_json, created_at, open) VALUES (?,?,?,?,1)",
                          (str(m.chat.id), question, options_json, now_ts()))
                poll_id = c.lastrowid
                conn.commit()
                conn.close()
                
                markup = types.InlineKeyboardMarkup(row_width=2)
                for i, opt in enumerate(options):
                    markup.add(types.InlineKeyboardButton(
                        f"{opt} (0)", callback_data=f"poll:vote:{poll_id}:{i}"
                    ))
                markup.add(types.InlineKeyboardButton("🔒 Close Poll", callback_data=f"poll:close:{poll_id}"))
                
                bot.send_message(m.chat.id, f"📊 <b>{safe_html(question)}</b>", reply_markup=markup)
                bot.reply_to(m, _(m.chat.id, 'poll_created'))
                log_action(m.chat.id, m.from_user.id, f"poll_created:{poll_id}")
            except Exception as e:
                logging.warning(f"Create poll failed: {e}")
                bot.reply_to(m, _(m.chat.id, 'error_occurred'))
            
            del STATE[(m.chat.id, 'poll_create')]
        else:
            state['options'].append(text)
            STATE[(m.chat.id, 'poll_create')] = state
            bot.reply_to(m, f"✅ Option add हुआ। Total: {len(state['options'])}. अगला option भेजें या 'done' लिखें।")
            
            # ---------- POLL VOTING CALLBACK HANDLER (ADDITIONAL) ----------
# This extends the callback_handler with poll voting logic

# Add this to the existing callback_handler function (insert after poll actions):
"""
        # Poll vote handling
        elif data.startswith('poll:vote:'):
            parts = data.split(':')
            poll_id = int(parts[2])
            option_idx = int(parts[3])
            
            try:
                conn = db()
                c = conn.cursor()
                c.execute("SELECT question, options_json, open FROM polls WHERE id=? AND chat_id=?",
                         (poll_id, str(chat_id)))
                row = c.fetchone()
                
                if not row:
                    bot.answer_callback_query(call.id, "❌ Poll not found", show_alert=True)
                    conn.close()
                    return
                
                if not row['open']:
                    bot.answer_callback_query(call.id, "❌ Poll closed", show_alert=True)
                    conn.close()
                    return
                
                poll_data = jload(row['options_json'], {})
                votes = poll_data.get('votes', {})
                
                # Remove user's previous vote
                for idx in votes:
                    if str(user_id) in votes[idx]:
                        votes[idx].remove(str(user_id))
                
                # Add new vote
                if str(option_idx) not in votes:
                    votes[str(option_idx)] = []
                votes[str(option_idx)].append(str(user_id))
                
                poll_data['votes'] = votes
                c.execute("UPDATE polls SET options_json=? WHERE id=?",
                         (jdump(poll_data), poll_id))
                conn.commit()
                conn.close()
                
                # Update buttons
                markup = types.InlineKeyboardMarkup(row_width=2)
                for i, opt in enumerate(poll_data['options']):
                    vote_count = len(votes.get(str(i), []))
                    markup.add(types.InlineKeyboardButton(
                        f"{opt} ({vote_count})", 
                        callback_data=f"poll:vote:{poll_id}:{i}"
                    ))
                markup.add(types.InlineKeyboardButton("🔒 Close Poll", callback_data=f"poll:close:{poll_id}"))
                
                bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id, "✅ Vote recorded!")
                
            except Exception as e:
                logging.warning(f"Poll vote failed: {e}")
                bot.answer_callback_query(call.id, "❌ Error voting", show_alert=True)
        
        # Poll close handling
        elif data.startswith('poll:close:'):
            poll_id = int(data.split(':')[2])
            
            try:
                conn = db()
                c = conn.cursor()
                c.execute("UPDATE polls SET open=0 WHERE id=? AND chat_id=?",
                         (poll_id, str(chat_id)))
                conn.commit()
                
                c.execute("SELECT question, options_json FROM polls WHERE id=?", (poll_id,))
                row = c.fetchone()
                conn.close()
                
                if row:
                    poll_data = jload(row['options_json'], {})
                    text = f"📊 <b>{safe_html(row['question'])}</b>

🔒 <i>Poll Closed</i>

<b>Results:</b>
"
                    
                    votes = poll_data.get('votes', {})
                    total_votes = sum(len(v) for v in votes.values())
                    
                    for i, opt in enumerate(poll_data['options']):
                        vote_count = len(votes.get(str(i), []))
                        percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
                        bar = '█' * int(percentage / 10)
                        text += f"
{opt}: {vote_count} votes ({percentage:.1f}%)
{bar}
"
                    
                    bot.edit_message_text(text, chat_id, msg_id)
                    bot.answer_callback_query(call.id, "✅ Poll closed")
                    log_action(chat_id, user_id, f"poll_closed:{poll_id}")
            
            except Exception as e:
                logging.warning(f"Close poll failed: {e}")
                bot.answer_callback_query(call.id, "❌ Error closing poll", show_alert=True)
"""

# ---------- ERROR HANDLER ----------
@bot.message_handler(func=lambda m: False)
def error_handler(m):
    """Global error handler (fallback)"""
    pass

# ---------- EXCEPTION HANDLER ----------
def handle_exception(e):
    """Log exceptions"""
    logging.error(f"Unhandled exception: {e}", exc_info=True)

# ---------- ADDITIONAL ADMIN COMMANDS ----------

@bot.message_handler(commands=['pin'])
def cmd_pin(m):
    """Pin a message"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not m.reply_to_message:
        bot.reply_to(m, "❌ Reply to message करें।")
        return
    
    try:
        bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id)
        bot.reply_to(m, "📌 Message pin हो गया।")
        log_action(m.chat.id, m.from_user.id, "message_pinned")
    except Exception as e:
        logging.warning(f"Pin failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['unpin'])
def cmd_unpin(m):
    """Unpin message"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    try:
        bot.unpin_chat_message(m.chat.id)
        bot.reply_to(m, "📌 Message unpin हो गया।")
        log_action(m.chat.id, m.from_user.id, "message_unpinned")
    except Exception as e:
        logging.warning(f"Unpin failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['purge'])
def cmd_purge(m):
    """Delete multiple messages"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    if not m.reply_to_message:
        bot.reply_to(m, "❌ Start message को reply करें।")
        return
    
    start_id = m.reply_to_message.message_id
    end_id = m.message_id
    
    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            bot.delete_message(m.chat.id, msg_id)
            deleted += 1
            time.sleep(0.1)  # Rate limit
        except:
            pass
    
    bot.send_message(m.chat.id, f"🗑 {deleted} messages delete हुए।")
    log_action(m.chat.id, m.from_user.id, f"purge:{deleted}")

@bot.message_handler(commands=['info'])
def cmd_info(m):
    """Show user info"""
    target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    
    try:
        member = bot.get_chat_member(m.chat.id, target.id)
        rank, xp = get_user_rank(m.chat.id, target.id)
        
        text = f"👤 <b>User Info</b>

"
        text += f"Name: {safe_html(get_user_display_name(target))}
"
        text += f"ID: <code>{target.id}</code>
"
        text += f"Status: {member.status}
"
        text += f"XP: {xp}
"
        text += f"Rank: #{rank}
"
        
        if target.username:
            text += f"Username: @{target.username}
"
        
        # Check punishments
        conn = db()
        c = conn.cursor()
        c.execute("SELECT type, COUNT(*) as cnt FROM punishments WHERE chat_id=? AND user_id=? GROUP BY type",
                  (str(m.chat.id), str(target.id)))
        punishments = c.fetchall()
        conn.close()
        
        if punishments:
            text += f"
<b>Punishments:</b>
"
            for p in punishments:
                text += f"• {p['type']}: {p['cnt']}
"
        
        bot.reply_to(m, text)
    except Exception as e:
        logging.warning(f"Info failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['stats'])
def cmd_stats(m):
    """Show group statistics"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    try:
        conn = db()
        c = conn.cursor()
        
        # Count various items
        c.execute("SELECT COUNT(*) as cnt FROM notes WHERE chat_id=?", (str(m.chat.id),))
        notes_count = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM triggers WHERE chat_id=?", (str(m.chat.id),))
        triggers_count = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM blacklist WHERE chat_id=?", (str(m.chat.id),))
        blacklist_count = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM xp WHERE chat_id=?", (str(m.chat.id),))
        users_count = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM polls WHERE chat_id=? AND open=1", (str(m.chat.id),))
        polls_count = c.fetchone()['cnt']
        
        conn.close()
        
        text = f"📊 <b>Group Statistics</b>

"
        text += f"📝 Notes: {notes_count}
"
        text += f"🤖 Triggers: {triggers_count}
"
        text += f"🚫 Blacklist Words: {blacklist_count}
"
        text += f"👥 Active Users: {users_count}
"
        text += f"📊 Active Polls: {polls_count}
"
        
        bot.reply_to(m, text)
    except Exception as e:
        logging.warning(f"Stats failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['setflood'])
def cmd_setflood(m):
    """Set flood protection limits"""
    if not is_admin_member(m.chat.id, m.from_user.id):
        bot.reply_to(m, _(m.chat.id, 'admin_only'))
        return
    
    args = m.text.split()
    if len(args) != 3:
        bot.reply_to(m, 
            f"❌ Format गलत है।
"
            f"{_(m.chat.id, 'usage', usage='/setflood <limit> <window_seconds>')}"
        )
        return
    
    try:
        limit = int(args[1])
        window = int(args[2])
        
        if limit < 1 or window < 1:
            bot.reply_to(m, "❌ Values must be positive.")
            return
        
        set_setting(m.chat.id, 'flood_limit', limit)
        set_setting(m.chat.id, 'flood_window', window)
        
        bot.reply_to(m, 
            f"✅ Flood protection updated:
"
            f"Limit: {limit} messages
"
            f"Window: {window} seconds"
        )
        log_action(m.chat.id, m.from_user.id, f"flood_updated:{limit}/{window}")
    except ValueError:
        bot.reply_to(m, "❌ Invalid numbers")
    except Exception as e:
        logging.warning(f"Set flood failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

@bot.message_handler(commands=['adminlist'])
def cmd_adminlist(m):
    """List all admins"""
    try:
        admins = bot.get_chat_administrators(m.chat.id)
        text = "👮 <b>Admins:</b>

"
        for admin in admins:
            user = admin.user
            name = get_user_display_name(user)
            status = "👑" if admin.status == 'creator' else "👮"
            text += f"{status} {safe_html(name)}
"
        
        bot.reply_to(m, text)
    except Exception as e:
        logging.warning(f"Admin list failed: {e}")
        bot.reply_to(m, _(m.chat.id, 'error_occurred'))

# ---------- BOT STARTUP & MAIN LOOP ----------

def main():
    """Main function to start the bot"""
    logging.info("🤖 Bot starting...")
    logging.info(f"📊 Database: {DB_PATH}")
    logging.info("✅ All systems ready")
    logging.info("🚀 Starting infinite polling...")
    
    try:
        # Start polling with error recovery
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            logger_level=logging.INFO,
            allowed_updates=['message', 'callback_query', 'chat_member']
        )
    except KeyboardInterrupt:
        logging.info("🛑 Bot stopped by user")
    except Exception as e:
        logging.error(f"❌ Bot crashed: {e}", exc_info=True)
        handle_exception(e)

if __name__ == "__main__":
    main()

# ---------- END OF bot.py ----------
            
            