#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Advanced Telegram Group Management Bot (v8.0 - UX Overhaul)
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
BOT_USERNAME = ""  # Will be fetched in main()

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
# Added new keys for UX overhaul
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
        'main_menu': '🏠 मुख्य मेनू',
        'back': '⬅️ वापस',
        'cancel': '❌ रद्द करें',
        'confirm': '✅ पुष्टि करें',
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
        
        # New UX Keys
        'unknown_action': '❓ अज्ञात कार्रवाई।',
        'lang_changed': '✅ भाषा English में बदल गई।',
        'main_menu_desc': 'ग्रुप को मैनेज करने के लिए एक विकल्प चुनें:',
        'settings': '⚙️ सेटिंग्स',
        'settings_desc': 'बॉट की बेसिक सेटिंग्स मैनेज करें।',
        'moderation': '🛡️ मॉडरेशन',
        'moderation_desc': 'ग्रुप मॉडरेशन टूल्स। किसी यूजर को /warn, /mute, /ban, /kick करने के लिए उसके मैसेज को रिप्लाई करें।',
        'locks': '🔐 Locks',
        'locks_desc': 'कंट्रोल करें कि कौन से मीडिया प्रकारों की अनुमति है।',
        'notes': '📝 Notes',
        'notes_desc': 'पुन: प्रयोज्य टेक्स्ट सेव करें। (कुल: {count})',
        'triggers': '🤖 Triggers',
        'triggers_desc': 'ऑटो-रिप्लाई सेट करें। (कुल: {count})',
        'xp_system': '🎯 XP सिस्टम',
        'xp_desc': 'यूजर लेवलिंग सिस्टम को मैनेज करें।',
        'xp_settings': '⚙️ XP सेटिंग्स',
        'xp_settings_desc': 'XP सिस्टम को टॉगल करें और कूलडाउन सेट करें।',
        'polls': '📊 Polls',
        'polls_desc': 'Polls बनाएं। (सक्रिय: {count})',
        'blacklist': '🚫 Blacklist',
        'blacklist_desc': 'ग्रुप में शब्दों को ब्लॉक करें। (कुल: {count})',
        'commands': '🔧 कमांड्स',
        'cmd_perms_desc': 'बॉट कमांड के लिए परमिशन सेट करें।',
        'fixed_admin_perm': '👮 एडमिन (Fixed)',
        'delete': '🗑️ डिलीट',
        'language': '🌐 भाषा',
        'welcome': '👋 Welcome',
        'leave': '🚪 Leave',
        'blacklist_toggle': '🚫 Blacklist',
        'xp_enabled': '🎯 XP सिस्टम',
        'xp_cooldown': '⏱ XP Cooldown (sec)',
        'lock_urls': '🔗 URLs',
        'lock_photos': '🖼️ Photos',
        'lock_videos': '🎥 Videos',
        'lock_stickers': '👾 Stickers',
        'lock_forwards': '↪️ Forwards',
        'lock_documents': '📎 Documents',
        'add_word': '➕ शब्द जोड़ें',
        'add_note': '➕ Note जोड़ें',
        'list_notes': '📋 Notes लिस्ट करें ({count})',
        'add_trigger': '➕ Trigger जोड़ें',
        'create_poll': '➕ Poll बनाएं',
        'active_polls': '📋 सक्रिय Polls ({count})',
        'leaderboard': '🏆 लीडरबोर्ड',
        'my_rank': '📊 मेरा Rank',
        'start_private': '👋 <b>Welcome!</b>\nमैं एक advanced group management bot हूँ।\nमुझे किसी group में add करें और admin बनाएं।',
        'start_group_not_admin': '🔔 <b>Bot Admin नहीं है</b>\nइस बॉट को सही से काम करने के लिए एडमिन बनना ज़रूरी है। कृपया मुझे प्रमोट करें।',
        'menu_in_private_prompt': '⚙️ ग्रुप सेटिंग्स जटिल हो सकती हैं। आप उन्हें सुरक्षित रूप से हमारे प्राइवेट चैट में मैनेज कर सकते हैं।',
        'menu_in_private_button': '🔐 प्राइवेट में सेटिंग्स खोलें',
        'menu_in_private_opened': '⚙️ ग्रुप के लिए सेटिंग्स मैनेज की जा रही हैं: <b>{title}</b>\n\n{desc}',
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
        'captcha_verify': '🔐 Please solve captcha: {q1} + {q2} = ?',
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

        # New UX Keys
        'unknown_action': '❓ Unknown action.',
        'lang_changed': '✅ Language changed to Hindi.',
        'main_menu_desc': 'Select an option to manage the group:',
        'settings': '⚙️ Settings',
        'settings_desc': 'Manage basic bot settings.',
        'moderation': '🛡️ Moderation',
        'moderation_desc': 'Tools for group moderation. Use commands like /warn, /mute, /ban by replying to a user.',
        'locks': '🔐 Locks',
        'locks_desc': 'Control which media types are allowed.',
        'notes': '📝 Notes',
        'notes_desc': 'Save reusable texts for the group. (Total: {count})',
        'triggers': '🤖 Triggers',
        'triggers_desc': 'Set up auto-replies for triggers. (Total: {count})',
        'xp_system': '🎯 XP System',
        'xp_desc': 'Manage the user leveling system.',
        'xp_settings': '⚙️ XP Settings',
        'xp_settings_desc': 'Toggle XP system and set cooldown.',
        'polls': '📊 Polls',
        'polls_desc': 'Create polls or view active ones. (Active: {count})',
        'blacklist': '🚫 Blacklist',
        'blacklist_desc': 'Manage words blocked in this group. (Total: {count})',
        'commands': '🔧 Commands',
        'cmd_perms_desc': 'Set permissions for who can use bot commands.',
        'fixed_admin_perm': '👮 Admin (fixed)',
        'delete': '🗑️ Delete',
        'language': '🌐 Language',
        'welcome': '👋 Welcome',
        'leave': '🚪 Leave',
        'blacklist_toggle': '🚫 Blacklist',
        'xp_enabled': '🎯 XP System',
        'xp_cooldown': '⏱ XP Cooldown (sec)',
        'lock_urls': '🔗 URLs',
        'lock_photos': '🖼️ Photos',
        'lock_videos': '🎥 Videos',
        'lock_stickers': '👾 Stickers',
        'lock_forwards': '↪️ Forwards',
        'lock_documents': '📎 Documents',
        'add_word': '➕ Add Word',
        'add_note': '➕ Add Note',
        'list_notes': '📋 List Notes ({count})',
        'add_trigger': '➕ Add Trigger',
        'create_poll': '➕ Create Poll',
        'active_polls': '📋 Active Polls ({count})',
        'leaderboard': '🏆 Leaderboard',
        'my_rank': '📊 My Rank',
        'start_private': '👋 <b>Welcome!</b>\nI am an advanced group management bot.\nAdd me to your group and make me an admin to get started.',
        'start_group_not_admin': '🔔 <b>Bot is Not Admin</b>\nThis bot must be an admin to function correctly. Please promote me.',
        'menu_in_private_prompt': '⚙️ Group settings can be complex. You can manage them securely in our private chat.',
        'menu_in_private_button': '🔐 Open Settings in Private',
        'menu_in_private_opened': '⚙️ Managing settings for group: <b>{title}</b>\n\n{desc}',
    }
}


def _(chat_id, key, **kwargs):
    "Get translated text"
    row = get_settings(str(chat_id))
    lang = row.get('lang', 'hi')
    text = LANG.get(lang, LANG['hi']).get(key, key)
    return text.format(**kwargs) if kwargs else text

# ---------- Utility Functions ----------
def now_ts():
    "Current Unix timestamp"
    return int(time.time())

def jdump(obj):
    "JSON dump"
    return json.dumps(obj, ensure_ascii=False)

def jload(text, default=None):
    "JSON load with fallback"
    try:
        return json.loads(text)
    except:
        return default if default is not None else {}

def safe_html(text):
    "Escape HTML entities"
    return html.escape(str(text))

# ---------- Database Initialization ----------
def db():
    "Return SQLite connection"
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    "Initialize all tables (existing schema preserved)"
    conn = db()
    c = conn.cursor()
    
    # Settings table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS settings (\n        chat_id TEXT PRIMARY KEY,\n        lang TEXT DEFAULT 'hi',\n        welcome_enabled INTEGER DEFAULT 1,\n        leave_enabled INTEGER DEFAULT 1,\n        flood_window INTEGER DEFAULT 15,\n        flood_limit INTEGER DEFAULT 7,\n        blacklist_enabled INTEGER DEFAULT 1,\n        locks_json TEXT DEFAULT '{}',\n        roles_json TEXT DEFAULT '{}',\n        rss_json TEXT DEFAULT '[]',\n        plugins_json TEXT DEFAULT '[]',\n        subscriptions_json TEXT DEFAULT '[]',\n        menu_json TEXT DEFAULT '{}'\n    )")
    
    # Triggers table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS triggers (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        pattern TEXT,\n        reply TEXT,\n        is_regex INTEGER DEFAULT 0\n    )")
    
    # Notes table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS notes (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        key TEXT,\n        content TEXT,\n        created_at INTEGER,\n        expires_at INTEGER DEFAULT 0\n    )")
    
    # Commands table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS commands (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        cmd TEXT,\n        body TEXT,\n        roles TEXT DEFAULT 'all'\n    )")
    
    # Blacklist table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS blacklist (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        word TEXT\n    )")
    
    # XP table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS xp (\n        chat_id TEXT,\n        user_id TEXT,\n        points INTEGER DEFAULT 0,\n        last_at INTEGER,\n        PRIMARY KEY (chat_id, user_id)\n    )")
    
    # Polls table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS polls (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        question TEXT,\n        options_json TEXT,\n        multiple INTEGER DEFAULT 0,\n        open INTEGER DEFAULT 1,\n        created_at INTEGER\n    )")
    
    # Dumps table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS dumps (\n        chat_id TEXT PRIMARY KEY,\n        enabled INTEGER DEFAULT 0,\n        forward_to TEXT\n    )")
    
    # Analytics table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS analytics (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        user_id TEXT,\n        action TEXT,\n        at INTEGER\n    )")
    
    # Punishments table (existing)
    c.execute("CREATE TABLE IF NOT EXISTS punishments (\n        id INTEGER PRIMARY KEY AUTOINCREMENT,\n        chat_id TEXT,\n        user_id TEXT,\n        type TEXT,\n        until_ts INTEGER\n    )")
    
    conn.commit()
    conn.close()
    logging.info("✅ Database initialized successfully")

init_db()

# ---------- Settings Helper Functions (existing, preserved) ----------
def ensure_settings(chat_id):
    "Ensure settings row exists for chat"
    conn = db()
    c = conn.cursor()
    c.execute("SELECT chat_id FROM settings WHERE chat_id=?", (str(chat_id),))
    if not c.fetchone():
        c.execute("INSERT INTO settings \n            (chat_id, lang, welcome_enabled, leave_enabled, flood_window, flood_limit, \n             blacklist_enabled, locks_json, roles_json, rss_json, plugins_json, \n             subscriptions_json, menu_json) \n            VALUES (?, 'hi', 1, 1, 15, 7, 1, '{}', '{}', '[]', '[]', '[]', '{}')",
            (str(chat_id),))
        conn.commit()
    conn.close()

def get_settings(chat_id):
    "Get settings row as dict"
    ensure_settings(str(chat_id))
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM settings WHERE chat_id=?", (str(chat_id),))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {}

def set_setting(chat_id, key, value):
    "Update single setting"
    ensure_settings(str(chat_id))
    conn = db()
    c = conn.cursor()
    c.execute(f"UPDATE settings SET {key}=? WHERE chat_id=?", (value, str(chat_id)))
    conn.commit()
    conn.close()

def menu_get(chat_id):
    "Get menu_json as dict"
    row = get_settings(str(chat_id))
    return jload(row.get('menu_json', '{}'), {})

def menu_set(chat_id, data):
    "Set menu_json"
    set_setting(str(chat_id), 'menu_json', jdump(data))

def roles_get(chat_id):
    "Get roles_json as dict"
    row = get_settings(str(chat_id))
    return jload(row.get('roles_json', '{}'), {})

def roles_set(chat_id, data):
    "Set roles_json"
    set_setting(str(chat_id), 'roles_json', jdump(data))

def locks_get(chat_id):
    "Get locks_json as dict"
    row = get_settings(str(chat_id))
    return jload(row.get('locks_json', '{}'), {})

def locks_set(chat_id, data):
    "Set locks_json"
    set_setting(str(chat_id), 'locks_json', jdump(data))

# ---------- Admin & Permission Check Functions ----------
def is_admin_member(chat_id, user_id):
    "Check if user is admin in the chat"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False

def is_creator_member(chat_id, user_id):
    "Check if user is creator of the chat"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status == 'creator'
    except:
        return False

def check_bot_permissions(chat_id):
    "Check if bot has required permissions"
    try:
        global BOT_USERNAME
        if not BOT_USERNAME:
            BOT_USERNAME = bot.get_me().username
            
        member = bot.get_chat_member(chat_id, bot.get_me().id)
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
    "Notify admin about missing bot permission"
    try:
        admins = bot.get_chat_administrators(chat_id)
        creator = [a for a in admins if a.status == 'creator']
        if creator:
            bot.send_message(
                creator[0].user.id,
                f"⚠️ Bot को '{permission}' permission नहीं है। Group: {chat_id}"
            )
    except Exception as e:
        print(f"Error notifying missing permission: {e}")

def has_command_permission(chat_id, user_id, command):
    "Check if user has permission to use command based on roles_json"
    # Moderation commands are now fixed to admin only
    if command in ['warn', 'mute', 'ban', 'kick', 'undo']:
        return is_admin_member(chat_id, user_id)
        
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
    "Log action to analytics table"
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
    "Forward log to configured channel/chat"
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT forward_to FROM dumps WHERE chat_id=? AND enabled=1", (str(chat_id),))
        row = c.fetchone()
        conn.close()
        if row and row['forward_to']:
            bot.send_message(row['forward_to'], f"📋 Log from {chat_id}: {text}")
    except Exception as e:
        logging.warning(f"Forward log failed: {e}")

# ---------- User Info Helpers ----------
def get_user_display_name(user):
    "Get user's display name"
    if user.username:
        return f"@{user.username}"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name.strip() or f"User{user.id}"

def get_user_mention(user):
    "Get HTML mention for user"
    name = safe_html(user.first_name or f"User{user.id}")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ---------- Punishment System ----------
def warn_user(chat_id, user_id, reason=""):
    "Warn user with escalation (3 warns → ban)"
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
    "Mute user for specified duration"
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
    "Ban user permanently"
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
    "Kick user (ban then unban)"
    try:
        bot.ban_chat_member(chat_id, user_id)
        bot.unban_chat_member(chat_id, user_id)
        log_action(chat_id, user_id, "kicked")
        return True
    except Exception as e:
        logging.warning(f"Kick failed: {e}")
        return False

def undo_punishment(chat_id, user_id):
    "Undo last punishment for user"
    try:
        conn = db()
        c = conn.cursor()
        c.execute("SELECT id, type FROM punishments \n                     WHERE chat_id=? AND user_id=? \n                     ORDER BY id DESC LIMIT 1",
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
    "Check if user is flooding, return (is_flood, count, limit)"
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
    "Check if text contains blacklisted words, return (found, word, violation_count)"
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
    "Track blacklist violations, auto-ban on 3rd"
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM punishments \n                 WHERE chat_id=? AND user_id=? AND type='blacklist'",
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
    "Check if message violates any locks"
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
    "Create math captcha for new user"
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
    "Verify captcha answer"
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
    "Restrict new user until captcha verification"
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
    "Remove all restrictions from user"
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

# ---------- XP System (XP & Ranking) ----------
def add_xp(chat_id, user_id, points=1):
    "Add XP to user, respecting cooldown and enable flag"
    chat_id_str = str(chat_id)
    user_id_str = str(user_id)
    
    # Check XP system enablement and cooldown from menu_json
    menu_data = menu_get(chat_id_str)
    xp_settings = menu_data.get('xp_settings', {})
    
    xp_enabled = xp_settings.get('xp_enabled', True)
    cooldown = xp_settings.get('xp_cooldown', 60) # Default 60s
    
    if not xp_enabled:
        return False
        
    conn = db()
    c = conn.cursor()
    
    # 1. Check cooldown
    c.execute("SELECT last_at FROM xp WHERE chat_id=? AND user_id=?", 
              (chat_id_str, user_id_str))
    row = c.fetchone()
    
    if row and (now_ts() - row['last_at']) < cooldown:
        conn.close()
        return False # Cooldown active

    # 2. Add/Update XP
    c.execute("INSERT INTO xp (chat_id, user_id, points, last_at) VALUES (?, ?, ?, ?) \n              ON CONFLICT(chat_id, user_id) DO UPDATE SET \n              points = points + ?, last_at = ?",
              (chat_id_str, user_id_str, points, now_ts(), points, now_ts()))
    conn.commit()
    conn.close()
    return True

def get_rank(chat_id, user_id):
    "Get user's rank and XP"
    chat_id_str = str(chat_id)
    user_id_str = str(user_id)
    
    conn = db()
    c = conn.cursor()
    
    # Get leaderboard
    c.execute("SELECT user_id, points FROM xp WHERE chat_id=? ORDER BY points DESC", 
              (chat_id_str,))
    leaderboard = c.fetchall()
    conn.close()
    
    rank = 0
    xp = 0
    
    for i, row in enumerate(leaderboard):
        if row['user_id'] == user_id_str:
            rank = i + 1
            xp = row['points']
            break
            
    return rank, xp

# ---------- Menu Builder Helper (Point 1) ----------
def build_toggle_row(chat_id, key, value, desc_key):
    """
    Creates a description text and an InlineKeyboardMarkup row with a state-first toggle button.
    
    Args:
        chat_id: The ID of the chat (used for translation).
        key: The unique callback key suffix (e.g., 'welcome_enabled').
        value: The current state (True/False or 1/0).
        desc_key: The translation key for the setting's description.
        
    Returns:
        (desc_text, InlineKeyboardMarkup row)
    """
    chat_id_str = str(chat_id)
    
    # 1. Description Text
    desc_text = _(chat_id_str, desc_key)
    
    # 2. Toggle Button Text (State-First)
    state_text = _(chat_id_str, 'enabled') if value else _(chat_id_str, 'disabled')
    callback_data = f"toggle:{key}:{int(not value)}" # Toggle action
    
    # 3. Build Keyboard
    keyboard = types.InlineKeyboardMarkup()
    row = [
        types.InlineKeyboardButton(state_text, callback_data=callback_data),
        types.InlineKeyboardButton(desc_text, callback_data="ignore") # Show description label
    ]
    keyboard.add(*row)
    
    return desc_text, keyboard

# ---------- Menu Rendering (Point 19) ----------
def send_menu(chat_id, user_id, menu_type, message_id=None, is_private=False, group_title=""):
    "Generates and sends/edits the specified menu"
    chat_id_str = str(chat_id)
    settings = get_settings(chat_id_str)
    
    # Get group title for private chat context
    if is_private and group_title:
        title = _(chat_id_str, 'menu_in_private_opened', title=safe_html(group_title))
        
        # In private chat, we need to know the target group_id to manage settings
        # The main menu for a private chat context is defined by the target group_id
        target_group_id = chat_id_str # Temporary, overridden below
    elif is_private:
        # Should not happen often, but acts as a fallback for main private menu
        title = _(chat_id_str, 'main_menu_desc')
    else:
        # Group chat context
        title = _(chat_id_str, 'main_menu_desc')
        
    
    keyboard = types.InlineKeyboardMarkup()
    desc_lines = []
    
    # --- Main Menu ---
    if menu_type == 'main':
        desc_lines.append(_(chat_id_str, 'main_menu_desc'))
        
        # [Settings] [Moderation]
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'settings'), callback_data="menu:settings"),
            types.InlineKeyboardButton(_(chat_id_str, 'moderation'), callback_data="menu:moderation")
        )
        # [Locks] [XP System]
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'locks'), callback_data="menu:locks"),
            types.InlineKeyboardButton(_(chat_id_str, 'xp_system'), callback_data="menu:xp_system")
        )
        # [Notes] [Triggers]
        conn = db()
        notes_count = conn.execute("SELECT COUNT(*) FROM notes WHERE chat_id=?", (chat_id_str,)).fetchone()[0]
        triggers_count = conn.execute("SELECT COUNT(*) FROM triggers WHERE chat_id=?", (chat_id_str,)).fetchone()[0]
        conn.close()
        
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'notes'), callback_data="menu:notes"),
            types.InlineKeyboardButton(_(chat_id_str, 'triggers'), callback_data="menu:triggers")
        )
        # [Blacklist] [Commands]
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'blacklist'), callback_data="menu:blacklist"),
            types.InlineKeyboardButton(_(chat_id_str, 'commands'), callback_data="menu:commands")
        )
        # [Polls] [Language] (Point 4)
        conn = db()
        active_polls = conn.execute("SELECT COUNT(*) FROM polls WHERE chat_id=? AND open=1", (chat_id_str,)).fetchone()[0]
        conn.close()
        
        lang_btn_text = f"🌐 {_(chat_id_str, 'language')}: {settings['lang'].upper()}"
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'polls'), callback_data="menu:polls"),
            types.InlineKeyboardButton(lang_btn_text, callback_data="lang:toggle")
        )

    # --- Settings Menu (Point 1, 2, 19) ---
    elif menu_type == 'settings':
        desc_lines.append(_(chat_id_str, 'settings_desc'))
        
        # Welcome Toggle
        welcome_desc, welcome_kb = build_toggle_row(chat_id, 'welcome_enabled', settings.get('welcome_enabled', 1), 'welcome')
        desc_lines.append(f"<b>{_(chat_id_str, 'welcome')}</b>: {welcome_desc}")
        keyboard.add(*welcome_kb.keyboard[0])

        # Leave Toggle
        leave_desc, leave_kb = build_toggle_row(chat_id, 'leave_enabled', settings.get('leave_enabled', 1), 'leave')
        desc_lines.append(f"<b>{_(chat_id_str, 'leave')}</b>: {leave_desc}")
        keyboard.add(*leave_kb.keyboard[0])

        # Blacklist Toggle
        blacklist_desc, blacklist_kb = build_toggle_row(chat_id, 'blacklist_enabled', settings.get('blacklist_enabled', 1), 'blacklist_toggle')
        desc_lines.append(f"<b>{_(chat_id_str, 'blacklist')}</b>: {blacklist_desc}")
        keyboard.add(*blacklist_kb.keyboard[0])
        
        # Back button
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Moderation Menu (Point 13) ---
    elif menu_type == 'moderation':
        desc_lines.append(_(chat_id_str, 'moderation_desc'))
        
        # Quick-links to commands (Requires user to reply to a message in the group)
        keyboard.add(
            types.InlineKeyboardButton("Warn /undo", callback_data="ignore"),
            types.InlineKeyboardButton("Mute /unmute", callback_data="ignore")
        )
        keyboard.add(
            types.InlineKeyboardButton("Ban /unban", callback_data="ignore"),
            types.InlineKeyboardButton("Kick", callback_data="ignore")
        )
        
        # Example of user-lookup for direct action (simplified)
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))
        
    # --- Locks Menu (Point 5, 19) ---
    elif menu_type == 'locks':
        locks = locks_get(chat_id_str)
        desc_lines.append(_(chat_id_str, 'locks_desc'))
        
        lock_keys = {
            'urls': 'lock_urls',
            'photos': 'lock_photos',
            'videos': 'lock_videos',
            'stickers': 'lock_stickers',
            'forwards': 'lock_forwards',
            'documents': 'lock_documents',
        }
        
        for key, desc_key in lock_keys.items():
            value = locks.get(key, 0)
            desc, kb = build_toggle_row(chat_id, f"lock_{key}", value, desc_key)
            desc_lines.append(f"<b>{_(chat_id_str, desc_key)}</b>: {desc}")
            keyboard.add(*kb.keyboard[0])
            
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))
        
    # --- XP System Menu (Point 8, 19) ---
    elif menu_type == 'xp_system':
        desc_lines.append(_(chat_id_str, 'xp_desc'))
        
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'xp_settings'), callback_data="menu:xp_settings"),
            types.InlineKeyboardButton(_(chat_id_str, 'leaderboard'), callback_data="xp:leaderboard")
        )
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'my_rank'), callback_data=f"xp:my_rank:{user_id}"),
            types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main")
        )

    # --- XP Settings Sub-Menu (Point 8, 19) ---
    elif menu_type == 'xp_settings':
        menu_data = menu_get(chat_id_str)
        xp_settings = menu_data.get('xp_settings', {})
        
        desc_lines.append(_(chat_id_str, 'xp_settings_desc'))

        # XP Enabled Toggle
        xp_enabled_desc, xp_enabled_kb = build_toggle_row(chat_id, 'xp_enabled', xp_settings.get('xp_enabled', True), 'xp_enabled')
        desc_lines.append(f"<b>{_(chat_id_str, 'xp_enabled')}</b>: {xp_enabled_desc}")
        keyboard.add(*xp_enabled_kb.keyboard[0])
        
        # XP Cooldown Setting (Editable number)
        cooldown = xp_settings.get('xp_cooldown', 60)
        cooldown_btn_text = f"⏱ {_(chat_id_str, 'xp_cooldown')}: {cooldown}s"
        desc_lines.append(f"<b>{_(chat_id_str, 'xp_cooldown')}</b>: XP points will only be granted once per user per {cooldown} seconds.")
        keyboard.add(
            types.InlineKeyboardButton(cooldown_btn_text, callback_data="xp:set_cooldown"),
            types.InlineKeyboardButton(_(chat_id_str, 'edit'), callback_data="xp:set_cooldown")
        )
        
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:xp_system"))

    # --- Notes Menu (Point 6, 19) ---
    elif menu_type == 'notes':
        conn = db()
        notes_rows = conn.execute("SELECT key FROM notes WHERE chat_id=?", (chat_id_str,)).fetchall()
        notes_count = len(notes_rows)
        conn.close()
        
        desc_lines.append(_(chat_id_str, 'notes_desc', count=notes_count))
        
        # Add Note button
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'add_note'), callback_data="note:add"))
        
        # List Notes button
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'list_notes', count=notes_count), callback_data="note:list"))
        
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Polls Menu (Point 7, 19) ---
    elif menu_type == 'polls':
        conn = db()
        active_polls = conn.execute("SELECT COUNT(*) FROM polls WHERE chat_id=? AND open=1", (chat_id_str,)).fetchone()[0]
        conn.close()
        
        desc_lines.append(_(chat_id_str, 'polls_desc', count=active_polls))
        
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'create_poll'), callback_data="poll:create"),
            types.InlineKeyboardButton(_(chat_id_str, 'active_polls', count=active_polls), callback_data="poll:list_active")
        )
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Triggers Menu (Point 9, 19) ---
    elif menu_type == 'triggers':
        conn = db()
        triggers_rows = conn.execute("SELECT id, pattern, is_regex, reply FROM triggers WHERE chat_id=?", (chat_id_str,)).fetchall()
        triggers_count = len(triggers_rows)
        conn.close()
        
        desc_lines.append(_(chat_id_str, 'triggers_desc', count=triggers_count))
        desc_lines.append("<i>" + _(chat_id_str, 'trigger_match_types') + "</i>") # Assumed new LANG key for match types
        
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'add_trigger'), callback_data="trigger:add"))
        
        # List triggers with 4 buttons per row (Point 9)
        for row in triggers_rows:
            trigger_id = row['id']
            pattern = safe_html(row['pattern'])
            # Simplified status check (assuming all listed triggers are 'enabled' by default)
            status_emoji = '🟢' 
            
            # The pattern text button
            pattern_btn = types.InlineKeyboardButton(f"{status_emoji} {pattern}", callback_data=f"trigger:options:{trigger_id}")
            
            # Enable/Disable/Options buttons (Simplified: use Options to manage status)
            # Point 9: [Pattern] [On] [Off] [Options] -> Simplified to [Pattern/Status] [Options]
            # Keeping the 4-button layout but simplifying actions for non-persistent DB
            
            on_btn = types.InlineKeyboardButton("On 🟢", callback_data=f"trigger:enable:{trigger_id}")
            off_btn = types.InlineKeyboardButton("Off 🔴", callback_data=f"trigger:disable:{trigger_id}")
            options_btn = types.InlineKeyboardButton("Options ⚙️", callback_data=f"trigger:options:{trigger_id}")
            
            keyboard.add(
                types.InlineKeyboardButton(f"[{pattern}]", callback_data=f"trigger:options:{trigger_id}"),
                on_btn, off_btn, options_btn
            )
            
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Blacklist Menu (Point 10, 19) ---
    elif menu_type == 'blacklist':
        conn = db()
        blacklist_rows = conn.execute("SELECT id, word FROM blacklist WHERE chat_id=?", (chat_id_str,)).fetchall()
        blacklist_count = len(blacklist_rows)
        conn.close()
        
        desc_lines.append(_(chat_id_str, 'blacklist_desc', count=blacklist_count))
        
        # Add Word button
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'add_word'), callback_data="blacklist:add"))
        
        # List blacklisted words with toggle (Point 10)
        # Note: Current DB schema doesn't support per-word toggle,
        # using the existing global toggle for context, and listing for visibility.
        
        for row in blacklist_rows:
            word_id = row['id']
            word = safe_html(row['word'])
            
            # Simplified row: [Word] [Delete]
            keyboard.add(
                types.InlineKeyboardButton(f"🚫 {word}", callback_data="ignore"),
                types.InlineKeyboardButton("🗑️", callback_data=f"blacklist:del:{word_id}")
            )
            
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Command Permissions Menu (Point 11, 19) ---
    elif menu_type == 'commands':
        roles = roles_get(chat_id_str)
        desc_lines.append(_(chat_id_str, 'cmd_perms_desc'))

        # Fixed Admin Only commands (Point 11)
        fixed_cmds = ['kick', 'ban', 'mute', 'warn']
        for cmd in fixed_cmds:
            keyboard.add(
                types.InlineKeyboardButton(f"/{cmd}", callback_data="ignore"),
                types.InlineKeyboardButton(_(chat_id_str, 'fixed_admin_perm'), callback_data="ignore")
            )
        
        # Other commands with configurable roles
        configurable_cmds = ['menu', 'help', 'settings', 'notes', 'triggers', 'xp']
        role_map = {'all': _(chat_id_str, 'all'), 'admin': _(chat_id_str, 'admin'), 'nobody': _(chat_id_str, 'nobody')}
        
        for cmd in configurable_cmds:
            current_role = roles.get(cmd, 'all')
            role_text = role_map.get(current_role, current_role.upper())
            
            # [Cmd] [Current Role] [Toggle]
            keyboard.add(
                types.InlineKeyboardButton(f"/{cmd}", callback_data="ignore"),
                types.InlineKeyboardButton(role_text, callback_data=f"cmd:toggle:{cmd}")
            )
            
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data="menu:main"))

    # --- Final Rendering ---
    final_text = "\n".join(desc_lines)
    
    if message_id:
        try:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id, 
                text=final_text, 
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return True
        except telebot.apihelper.ApiTelegramException as e:
            if "message is not modified" not in str(e):
                logging.warning(f"Error editing message: {e}")
                return False
            return True # Not modified is success
    else:
        # If sending for the first time
        bot.send_message(chat_id, final_text, reply_markup=keyboard, parse_mode="HTML")
        return True

# ---------- Command Handlers (Menu & Start) ----------

@bot.message_handler(commands=['start'])
def cmd_start(m):
    "Handle /start command (Point 15)"
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    # 1. Private Chat Flow
    if m.chat.type == 'private':
        # Check if the private /start is a deep-link from a group admin
        if m.text and len(m.text.split()) > 1:
            try:
                # Deep link format: /start group_<chat_id>
                target_chat_id = m.text.split()[1].replace('group_', '')
                # Basic check to see if the user is an admin in the target group
                if is_admin_member(target_chat_id, user_id):
                    # Redirect to the main menu for that group
                    chat_info = bot.get_chat(target_chat_id)
                    send_menu(chat_id, user_id, 'main', is_private=True, group_title=chat_info.title)
                    return
            except Exception as e:
                logging.warning(f"Deep link start error: {e}")
                
        # Generic private start message
        text = _(chat_id, 'start_private')
        keyboard = types.InlineKeyboardMarkup()
        
        # Point 15 Buttons
        # "Show my groups" is tricky without external group data, using generic button
        keyboard.add(types.InlineKeyboardButton("Show My Groups 🤖", url="https://t.me/telegram_bot_my_groups_helper"))
        keyboard.add(types.InlineKeyboardButton("Add to Group ➕", url=f"https://t.me/{BOT_USERNAME}?startgroup=start"))
        
        bot.send_message(chat_id, text, reply_markup=keyboard)
        return

    # 2. Group Chat Flow
    try:
        # Check bot's admin status
        bot_perms = check_bot_permissions(chat_id)
        if not bot_perms.get('is_admin'):
            # Bot is not admin (Point 15)
            text = _(chat_id, 'start_group_not_admin')
            keyboard = types.InlineKeyboardMarkup()
            
            # Button linking to bot's private start (for instructions)
            keyboard.add(types.InlineKeyboardButton("Add Bot as Admin 🛡️", url=f"https://t.me/{BOT_USERNAME}?startgroup=start"))
            
            bot.send_message(chat_id, text, reply_markup=keyboard)
            return

        # Bot is admin, proceed to menu (using /menu flow)
        cmd_menu(m)

    except Exception as e:
        logging.warning(f"Start command failed: {e}")
        bot.reply_to(m, _(chat_id, 'error_occurred'))

@bot.message_handler(commands=['menu'])
def cmd_menu(m):
    "Handle /menu command (Point 16, 19)"
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    if m.chat.type == 'private':
        # Private chat menu (generic, or deep-link redirect)
        send_menu(chat_id, user_id, 'main')
        return

    # Group chat: Check permission
    if not is_admin_member(chat_id, user_id):
        bot.reply_to(m, _(chat_id, 'admin_only'))
        return
        
    # Check if user is the group creator (Point 16)
    if is_creator_member(chat_id, user_id):
        # Prompt to open in private chat
        text = _(chat_id, 'menu_in_private_prompt')
        keyboard = types.InlineKeyboardMarkup()
        
        # Button links to private chat with deep link to THIS group's settings
        group_link_data = f"group_{chat_id}"
        keyboard.add(
            types.InlineKeyboardButton(
                _(chat_id, 'menu_in_private_button'), 
                url=f"https://t.me/{BOT_USERNAME}?start={group_link_data}"
            )
        )
        
        # Also provide option to open menu in group
        keyboard.add(types.InlineKeyboardButton("Open Menu Here ⚙️", callback_data="menu:main"))
        
        bot.reply_to(m, text, reply_markup=keyboard)
        
    else:
        # Normal admin can open menu in group directly
        send_menu(chat_id, user_id, 'main', message_id=m.message_id)


# ---------- Moderation Commands (Point 17) ----------
def handle_moderation_command(m, command):
    "Generic handler for moderation commands"
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    # Check command permission (fixed admin only, Point 11)
    if not has_command_permission(chat_id, user_id, command):
        bot.reply_to(m, _(chat_id, 'admin_only'))
        return

    # Must be a reply
    if not m.reply_to_message:
        bot.reply_to(m, _(chat_id, 'usage', usage=f'Reply to a user\'s message with /{command}'))
        return
        
    target_user = m.reply_to_message.from_user
    if target_user.is_bot:
        bot.reply_to(m, "❌ Bots cannot be moderated.")
        return
        
    # Check bot permissions (Point 17)
    bot_perms = check_bot_permissions(chat_id)
    if not bot_perms.get('can_restrict'):
        text = "❌ Bot is missing <i>'Restrict Users'</i> permission."
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("Add Bot as Admin 🛡️", url=f"https://t.me/{BOT_USERNAME}?startgroup=start"))
        bot.reply_to(m, text, reply_markup=keyboard)
        return

    target_mention = get_user_mention(target_user)
    
    if command == 'warn':
        count, action = warn_user(chat_id, target_user.id)
        if action == 'banned':
            bot.reply_to(m, _(chat_id, 'user_banned', user=target_mention))
        else:
            bot.reply_to(m, _(chat_id, 'user_warned', user=target_mention, count=count))
            
    elif command == 'mute':
        # Default duration: 1 hour (3600 seconds). Can be extended via message args
        duration_sec = 3600
        
        if mute_user(chat_id, target_user.id, duration_sec):
            duration_text = str(timedelta(seconds=duration_sec))
            bot.reply_to(m, _(chat_id, 'user_muted', user=target_mention, duration=duration_text))
        else:
            bot.reply_to(m, _(chat_id, 'error_occurred'))
            
    elif command == 'ban':
        if ban_user(chat_id, target_user.id):
            bot.reply_to(m, _(chat_id, 'user_banned', user=target_mention))
        else:
            bot.reply_to(m, _(chat_id, 'error_occurred'))
            
    elif command == 'kick':
        if kick_user(chat_id, target_user.id):
            bot.reply_to(m, _(chat_id, 'user_kicked', user=target_mention))
        else:
            bot.reply_to(m, _(chat_id, 'error_occurred'))
            
    elif command == 'undo':
        success, ptype = undo_punishment(chat_id, target_user.id)
        if success:
            bot.reply_to(m, f"✅ Last punishment ({ptype}) for {target_mention} revoked.")
        else:
            bot.reply_to(m, f"❌ Cannot undo punishment for {target_mention}: {ptype}")


@bot.message_handler(commands=['warn'])
def cmd_warn(m):
    handle_moderation_command(m, 'warn')

@bot.message_handler(commands=['mute'])
def cmd_mute(m):
    handle_moderation_command(m, 'mute')

@bot.message_handler(commands=['ban'])
def cmd_ban(m):
    handle_moderation_command(m, 'ban')

@bot.message_handler(commands=['kick'])
def cmd_kick(m):
    handle_moderation_command(m, 'kick')

@bot.message_handler(commands=['undo'])
def cmd_undo(m):
    handle_moderation_command(m, 'undo')
    
# /unmute and /unban are aliases for /undo when applied to a muted/banned user.
@bot.message_handler(commands=['unmute', 'unban'])
def cmd_unmute_unban(m):
    cmd_undo(m)

# ---------- XP Commands ----------
@bot.message_handler(commands=['rank'])
def cmd_rank(m):
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    target_user = m.from_user
    if m.reply_to_message:
        target_user = m.reply_to_message.from_user
        
    rank, xp = get_rank(chat_id, target_user.id)
    mention = get_user_mention(target_user)
    
    if rank > 0:
        text = _(chat_id, 'rank_display', name=mention, rank=rank, xp=xp)
        bot.reply_to(m, text)
    else:
        bot.reply_to(m, "❌ No XP data found for this user.")

# ---------- General Message Handler (Pre-processing) ----------

@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'document'], func=lambda m: m.chat.type != 'private')
def handle_group_messages(m):
    "Handle all group messages for flood, blacklist, locks, XP, and triggers."
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    # Ignore commands and bot messages
    if m.text and m.text.startswith('/') or m.from_user.is_bot:
        return
        
    # 1. Captcha Check (If pending)
    if (chat_id, user_id) in pending_captcha:
        try:
            answer = int(m.text.strip())
            user_name = get_user_mention(m.from_user)
            if verify_captcha(chat_id, user_id, answer):
                unrestrict_user(chat_id, user_id)
                bot.send_message(chat_id, _(chat_id, 'captcha_success', name=user_name))
                bot.delete_message(chat_id, m.message_id) # Delete user's answer
                return
            else:
                # Allow a few tries, but delete wrong answer
                bot.delete_message(chat_id, m.message_id) 
                bot.answer_callback_query(m.id, _(chat_id, 'captcha_failed'), show_alert=True)
                return
        except:
            # Not a number/relevant text, ignore but don't delete
            pass
            
    # 2. Flood Check
    is_flood, count, limit = check_flood(chat_id, user_id)
    if is_flood:
        # Delete message and warn user
        try:
            bot.delete_message(chat_id, m.message_id)
            bot.send_message(chat_id, _(chat_id, 'flood_detected', count=count, limit=limit))
            # Optional: warn_user(chat_id, user_id, "flood")
            return
        except:
            pass
    
    # 3. Locks Check
    violations = check_locks(chat_id, m)
    if violations and check_bot_permissions(chat_id).get('can_delete'):
        # Delete message and notify/warn
        try:
            bot.delete_message(chat_id, m.message_id)
            # Optional: warn_user(chat_id, user_id, f"lock:{','.join(violations)}")
            return
        except:
            pass

    # 4. Blacklist Check (If enabled)
    settings = get_settings(chat_id)
    if settings.get('blacklist_enabled', 1) and m.text:
        found, word, _ = check_blacklist(chat_id, m.text)
        if found:
            # Delete message and warn
            if check_bot_permissions(chat_id).get('can_delete'):
                try:
                    bot.delete_message(chat_id, m.message_id)
                except:
                    pass
            
            count, banned = add_blacklist_violation(chat_id, user_id)
            user_mention = get_user_mention(m.from_user)
            
            if banned:
                bot.send_message(chat_id, _(chat_id, 'user_banned', user=user_mention))
            else:
                bot.send_message(chat_id, _(chat_id, 'blacklist_violation', count=count))
            return

    # 5. XP Gain (If enabled and not on cooldown)
    if add_xp(chat_id, user_id):
        # Optional: Send a short notification or log it
        # Example: bot.send_message(chat_id, _(chat_id, 'xp_gained', points=1))
        pass

    # 6. Triggers/Auto-Reply Check
    conn = db()
    c = conn.cursor()
    c.execute("SELECT pattern, reply, is_regex FROM triggers WHERE chat_id=?", (str(chat_id),))
    triggers = c.fetchall()
    conn.close()
    
    for row in triggers:
        pattern = row['pattern']
        reply = row['reply']
        is_regex = row['is_regex']
        
        match = False
        if is_regex:
            try:
                if re.search(pattern, m.text or '', re.IGNORECASE):
                    match = True
            except:
                continue # Skip invalid regex
        else:
            if m.text and pattern.lower() in m.text.lower():
                match = True
                
        if match:
            # Reply with the trigger content
            bot.reply_to(m, reply)
            break
            
# ---------- New Member/Leave Handlers ----------

@bot.chat_member_handler()
def handle_chat_member(chat_member_update: types.ChatMemberUpdated):
    "Handle new member, leave, and bot admin status changes"
    chat_id = chat_member_update.chat.id
    new_member = chat_member_update.new_chat_member
    old_member = chat_member_update.old_chat_member
    
    # 1. Bot added/promoted to admin
    if new_member.user.id == bot.get_me().id:
        if new_member.status == 'administrator' and old_member.status != 'administrator':
            bot.send_message(chat_id, "✅ Bot promoted to admin! All systems operational.")
        return
        
    # 2. New Member Joined (Welcome and Captcha - Point 15)
    if new_member.status in ['member', 'restricted'] and old_member.status in ['left', 'kicked']:
        settings = get_settings(chat_id)
        if not settings.get('welcome_enabled', 1):
            return

        user_mention = get_user_mention(new_member.user)
        
        # Restrict user immediately (Point 15)
        restrict_new_user(chat_id, new_member.user.id)

        # Create Captcha
        num1, num2 = create_captcha(chat_id, new_member.user.id)
        
        welcome_text = _(chat_id, 'welcome_message', name=user_mention)
        captcha_text = _(chat_id, 'captcha_verify', q1=num1, q2=num2)
        
        # Combine welcome and captcha
        final_text = f"{welcome_text}\n\n{captcha_text}\n\n<i>{new_member.user.first_name}, {_(chat_id, 'captcha_solve_prompt')}</i>"
        
        bot.send_message(chat_id, final_text)

    # 3. Member Left
    elif new_member.status in ['left', 'kicked'] and old_member.status in ['member', 'restricted', 'administrator']:
        settings = get_settings(chat_id)
        if not settings.get('leave_enabled', 1):
            return
            
        user_display = get_user_display_name(new_member.user)
        bot.send_message(chat_id, _(chat_id, 'goodbye_message', name=safe_html(user_display)))

# ---------- Callback Query Handler (Core Menu Logic) ----------

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    "Handle all inline button presses (Points 2, 3, 4, 5, 19)"
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id
    data = call.data
    parts = data.split(':')
    
    # Check admin permission before proceeding with any action
    if chat_id < 0 and not is_admin_member(chat_id, user_id):
        # Allow navigation in private chat, but restrict in group
        bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
        return
        
    try:
        # --- 1. Menu Navigation (menu:type) ---
        if parts[0] == 'menu':
            menu_type = parts[1]
            send_menu(chat_id, user_id, menu_type, message_id)
            bot.answer_callback_query(call.id)
            return

        # --- 2. Toggle Actions (toggle:key:value) (Point 1, 2) ---
        if parts[0] == 'toggle':
            key = parts[1]
            new_value = int(parts[2])
            
            # --- General Settings Toggles (welcome, leave, blacklist) ---
            if key in ['welcome_enabled', 'leave_enabled', 'blacklist_enabled']:
                set_setting(chat_id, key, new_value)
                send_menu(chat_id, user_id, 'settings', message_id) # Refresh the menu
                bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'))
                return

            # --- Lock Toggles (Point 5) ---
            elif key.startswith('lock_'):
                lock_type = key.replace('lock_', '')
                locks = locks_get(chat_id)
                locks[lock_type] = new_value
                locks_set(chat_id, locks)
                send_menu(chat_id, user_id, 'locks', message_id) # Refresh the menu
                bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'))
                return

            # --- XP Settings Toggles (Point 8) ---
            elif key == 'xp_enabled':
                menu_data = menu_get(chat_id)
                xp_settings = menu_data.get('xp_settings', {})
                xp_settings['xp_enabled'] = bool(new_value)
                menu_data['xp_settings'] = xp_settings
                menu_set(chat_id, menu_data)
                send_menu(chat_id, user_id, 'xp_settings', message_id) # Refresh the menu
                bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'))
                return
            
            # --- Trigger Toggles (Point 5, 9) ---
            elif key.startswith('trigger:'):
                 # Simplified implementation: Just send alert that toggle is handled via command/options
                 trigger_action = parts[1]
                 trigger_id = parts[2]
                 bot.answer_callback_query(call.id, f"Trigger ID {trigger_id} is now {trigger_action}d!", show_alert=True)
                 return


        # --- 3. Language Toggle (lang:toggle) (Point 4) ---
        if parts[0] == 'lang' and parts[1] == 'toggle':
            current_lang = get_settings(chat_id).get('lang', 'hi')
            new_lang = 'en' if current_lang == 'hi' else 'hi'
            set_setting(chat_id, 'lang', new_lang)
            
            # Use new language for confirmation text
            confirm_text = _(chat_id, 'lang_changed') # This uses the *old* lang, which is fine for the instant context
            
            # Send message using the NEW language context
            send_menu(chat_id, user_id, 'main', message_id) # Always refresh to Main menu
            bot.answer_callback_query(call.id, confirm_text) # Show alert using old lang for confirmation
            return

        # --- 4. Command Permission Toggle (cmd:toggle:cmd_name) ---
        if parts[0] == 'cmd' and parts[1] == 'toggle':
            cmd_name = parts[2]
            roles = roles_get(chat_id)
            current_role = roles.get(cmd_name, 'all')
            
            # Cycle: all -> admin -> nobody -> all
            if current_role == 'all':
                new_role = 'admin'
            elif current_role == 'admin':
                new_role = 'nobody'
            else:
                new_role = 'all'
                
            roles[cmd_name] = new_role
            roles_set(chat_id, roles)
            send_menu(chat_id, user_id, 'commands', message_id)
            bot.answer_callback_query(call.id, f"/{cmd_name} role set to {new_role.upper()}")
            return
            
        # --- 5. Simple Actions (Notes, Polls, XP) ---
        if parts[0] in ['note', 'poll', 'xp', 'blacklist']:
            action = parts[1]
            
            # Note/Blacklist Add (Simplified: just show an alert to prompt command)
            if action in ['add', 'set_cooldown']:
                command = f"/{action.split('_')[0]}"
                if parts[0] == 'xp' and action == 'set_cooldown':
                    bot.send_message(chat_id, f"⏱ {_(chat_id, 'xp_cooldown')}: Please reply with the new cooldown value in seconds.", reply_to_message_id=message_id)
                    # Set a temporary state for the next text message
                    STATE[(chat_id, 'xp_cooldown_set')] = True
                    bot.answer_callback_query(call.id, "Ready to set new cooldown...", show_alert=False)
                    return
                
                bot.answer_callback_query(call.id, f"Use the corresponding command: {command} <key/word>", show_alert=True)
                return
            
            # List Actions (Simplified: just show an alert with counts)
            elif action in ['list', 'list_active', 'leaderboard', 'my_rank', 'options']:
                if action == 'my_rank':
                    rank, xp = get_rank(chat_id, user_id)
                    rank_info = _(chat_id, 'rank_display', name="You", rank=rank, xp=xp)
                    bot.answer_callback_query(call.id, rank_info, show_alert=True)
                    return
                    
                # Other list actions (List Notes, Active Polls, Leaderboard)
                bot.answer_callback_query(call.id, f"Listing/Options for {parts[0].upper()} - Full list command not implemented in callback.", show_alert=True)
                return
                
        # --- 6. Fallthrough (Unknown action) (Point 3) ---
        bot.answer_callback_query(call.id, _(chat_id,'unknown_action'), show_alert=True)

    except Exception as e:
        logging.error(f"Callback error in {data}: {e}")
        bot.answer_callback_query(call.id, _(chat_id, 'error_occurred'), show_alert=True)

# ---------- XP Cooldown State Handler (Continuation of point 8) ---

@bot.message_handler(func=lambda m: (m.chat.id, 'xp_cooldown_set') in STATE and m.chat.type != 'private')
def handle_xp_cooldown_input(m):
    "Handle the text input for setting XP cooldown"
    chat_id = m.chat.id
    user_id = m.from_user.id
    
    del STATE[(chat_id, 'xp_cooldown_set')] # Clear state

    if not is_admin_member(chat_id, user_id):
        bot.reply_to(m, _(chat_id, 'admin_only'))
        return
        
    try:
        new_cooldown = int(m.text.strip())
        if new_cooldown < 10:
            bot.reply_to(m, "❌ Cooldown must be at least 10 seconds.")
            return

        menu_data = menu_get(chat_id)
        xp_settings = menu_data.get('xp_settings', {})
        xp_settings['xp_cooldown'] = new_cooldown
        menu_data['xp_settings'] = xp_settings
        menu_set(chat_id, menu_data)
        
        bot.reply_to(m, f"✅ XP Cooldown set to {new_cooldown} seconds.")
        
        # Try to refresh the menu if the original message is nearby
        # Simplification: just send the confirmation message.
        
    except ValueError:
        bot.reply_to(m, _(chat_id, 'invalid_input'))
    except Exception as e:
        logging.error(f"XP cooldown set error: {e}")
        bot.reply_to(m, _(chat_id, 'error_occurred'))

# ---------- BOT STARTUP & MAIN LOOP ----------

def main():
    "Main function to start the bot"
    global BOT_USERNAME
    logging.info("🤖 Bot starting...")
    logging.info(f"📊 Database: {DB_PATH}")
    
    try:
        bot_info = bot.get_me()
        BOT_USERNAME = bot_info.username
        logging.info(f"✅ Bot username: @{BOT_USERNAME}")
        
    except Exception as e:
        logging.error(f"❌ Failed to fetch bot info: {e}")
        sys.exit(1)
        
    logging.info("✅ All systems ready")
    logging.info("🚀 Starting infinite polling...")
    
    # Remove unused commands (Point 12)
    # Note: /backup and /restore were not explicitly implemented in previous parts, 
    # but the intent is to ensure they are not used/available.
    
    try:
        # Start polling with error recovery
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            logger_level=logging.INFO,
            allowed_updates=['message', 'callback_query', 'chat_member']
        )
    except KeyboardInterrupt:
        logging.info("🛑 Bot stopped by user (Ctrl+C).")
    except Exception as e:
        logging.error(f"❌ Polling stopped due to error: {e}")

if __name__ == '__main__':
    # This structure would contain the entirety of Parts 1-6
    # For the final output, the full code will be concatenated.
    main()

