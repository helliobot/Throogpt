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
        'settings_desc': 'ग्रुप में एंट्री, एग्जिट और ब्लैकलिस्ट टॉगल करें।',
        'moderation': '🛡️ मॉडरेशन',
        'moderation_desc': 'ग्रुप मॉडरेशन टूल्स। किसी यूजर को /warn, /mute, /ban, /kick करने के लिए उसके मैसेज को रिप्लाई करें।',
        'locks': '🔐 Locks',
        'locks_desc': 'कंट्रोल करें कि कौन से मीडिया प्रकारों की अनुमति है।',
        'notes': '📝 Notes',
        'notes_desc': 'पुन: प्रयोज्य टेक्स्ट सेव करें।',
        'triggers': '🤖 Triggers',
        'triggers_desc': 'ऑटो-रिप्लाई सेट करें।',
        'xp_system': '🎯 XP सिस्टम',
        'xp_desc': 'यूजर लेवलिंग सिस्टम को मैनेज करें।',
        'xp_settings': '⚙️ XP सेटिंग्स',
        'xp_settings_desc': 'XP सिस्टम को टॉगल करें और कूलडाउन सेट करें।',
        'polls': '📊 Polls',
        'polls_desc': 'Polls बनाएं या सक्रिय Polls देखें।',
        'blacklist': '🚫 Blacklist',
        'blacklist_desc': 'ग्रुप में शब्दों को ब्लॉक करें।',
        'commands': '🔧 कमांड्स',
        'cmd_perms_desc': 'बॉट कमांड के लिए परमिशन सेट करें।',
        'fixed_admin_perm': '👮 एडमिन (Fixed)',
        'delete': '🗑️ डिलीट',
        'language': '🌐 भाषा',
        'welcome': '👋 Welcome',
        'welcome_enabled_desc': 'नए यूजर्स के लिए स्वागत संदेश और CAPTCHA (यदि कॉन्फ़िगर किया गया हो)।',
        'leave': '🚪 Leave',
        'leave_enabled_desc': 'ग्रुप छोड़ने पर विदाई संदेश।',
        'blacklist_toggle': '🚫 Blacklist',
        'blacklist_enabled_desc': 'ब्लैकलिस्ट किए गए शब्दों का पता लगने पर कार्रवाई करें।',
        'xp_enabled_desc': 'XP सिस्टम को ऑन/ऑफ करता है।',
        'xp_cooldown': '⏱ XP Cooldown (sec)',
        'xp_cooldown_desc': 'एक यूजर को दोबारा XP कमाने से पहले का इंतज़ार समय (सेकंड में)।',
        'lock_urls': '🔗 URLs',
        'lock_urls_desc': 'ग्रुप में URLs/लिंक्स को ब्लॉक करें।',
        'lock_photos': '🖼️ Photos',
        'lock_photos_desc': 'ग्रुप में फ़ोटो (चित्रों) को ब्लॉक करें।',
        'lock_videos': '🎥 Videos',
        'lock_videos_desc': 'ग्रुप में वीडियोज़ को ब्लॉक करें।',
        'lock_stickers': '👾 Stickers',
        'lock_stickers_desc': 'ग्रुप में स्टिकर्स को ब्लॉक करें।',
        'lock_forwards': '↪️ Forwards',
        'lock_forwards_desc': 'ग्रुप में किसी भी फॉरवर्ड किए गए संदेश को ब्लॉक करें।',
        'lock_documents': '📎 Documents',
        'lock_documents_desc': 'ग्रुप में फ़ाइलें/दस्तावेजों को ब्लॉक करें।',
        'add_word': '➕ शब्द जोड़ें',
        'list_words': '📋 शब्द लिस्ट करें',
        'add_note': '➕ Note जोड़ें',
        'list_notes': '📋 Notes लिस्ट करें',
        'add_trigger': '➕ Trigger जोड़ें',
        'list_triggers': '📋 Triggers लिस्ट करें',
        'create_poll': '➕ Poll बनाएं',
        'active_polls': '📋 सक्रिय Polls',
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
        'settings_desc': 'Toggle entry, exit, and blacklist in the group.',
        'moderation': '🛡️ Moderation',
        'moderation_desc': 'Tools for group moderation. Use commands like /warn, /mute, /ban by replying to a user.',
        'locks': '🔐 Locks',
        'locks_desc': 'Control which media types are allowed.',
        'notes': '📝 Notes',
        'notes_desc': 'Save reusable texts for the group.',
        'triggers': '🤖 Triggers',
        'triggers_desc': 'Set up auto-replies for triggers.',
        'xp_system': '🎯 XP System',
        'xp_desc': 'Manage the user leveling system.',
        'xp_settings': '⚙️ XP Settings',
        'xp_settings_desc': 'Toggle XP system and set cooldown.',
        'polls': '📊 Polls',
        'polls_desc': 'Create polls or view active ones.',
        'blacklist': '🚫 Blacklist',
        'blacklist_desc': 'Manage words blocked in this group.',
        'commands': '🔧 Commands',
        'cmd_perms_desc': 'Set permissions for who can use bot commands.',
        'fixed_admin_perm': '👮 Admin (fixed)',
        'delete': '🗑️ Delete',
        'language': '🌐 Language',
        'welcome': '👋 Welcome',
        'welcome_enabled_desc': 'Welcome message and CAPTCHA (if configured) for new users.',
        'leave': '🚪 Leave',
        'leave_enabled_desc': 'Goodbye message when a user leaves the group.',
        'blacklist_toggle': '🚫 Blacklist',
        'blacklist_enabled_desc': 'Take action when blacklisted words are detected.',
        'xp_enabled_desc': 'Turns the XP system ON/OFF.',
        'xp_cooldown': '⏱ XP Cooldown (sec)',
        'xp_cooldown_desc': 'The wait time (in seconds) before a user can earn XP again.',
        'lock_urls': '🔗 URLs',
        'lock_urls_desc': 'Block URLs/links in the group.',
        'lock_photos': '🖼️ Photos',
        'lock_photos_desc': 'Block photos (images) in the group.',
        'lock_videos': '🎥 Videos',
        'lock_videos_desc': 'Block videos in the group.',
        'lock_stickers': '👾 Stickers',
        'lock_stickers_desc': 'Block stickers in the group.',
        'lock_forwards': '↪️ Forwards',
        'lock_forwards_desc': 'Block any forwarded messages in the group.',
        'lock_documents': '📎 Documents',
        'lock_documents_desc': 'Block files/documents in the group.',
        'add_word': '➕ Add Word',
        'list_words': '📋 List Words',
        'add_note': '➕ Add Note',
        'list_notes': '📋 List Notes',
        'add_trigger': '➕ Add Trigger',
        'list_triggers': '📋 List Triggers',
        'create_poll': '➕ Create Poll',
        'active_polls': '📋 Active Polls',
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

# ---------- Utility Functions (No change to core logic) ----------
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

# ---------- Database Initialization & Helpers (Schema Preserved) ----------
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

# ---------- Admin & Permission Check Functions (existing, preserved) ----------
def is_admin_member(chat_id, user_id):
    "Check if user is admin in the chat"
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False
        
# -------------------- नया हेल्पर फ़ंक्शन (Add this block) --------------------
def get_user_managed_groups(user_id):
    """
    यूज़र द्वारा प्रबंधित ग्रुप (जहाँ यूज़र क्रिएटर है और बॉट एक्टिव है) की सूची लाता है।
    यह फ़ंक्शन मानता है कि 'settings' टेबल में बॉट के एक्टिव सभी ग्रुप_आईडी मौजूद हैं।
    """
    conn = db()
    c = conn.cursor()
    # उन सभी chat_id को चुनें जो ग्रुप (नेगेटिव ID) हैं
    c.execute("SELECT DISTINCT chat_id FROM settings WHERE chat_id LIKE '-%'")
    all_group_ids = [row['chat_id'] for row in c.fetchall()]
    conn.close()
    
    managed_groups = []
    for chat_id in all_group_ids:
        # क्रिएटर की जाँच करें (is_creator_member फ़ंक्शन का उपयोग करके)
        if is_creator_member(chat_id, user_id):
            # ग्रुप का टाइटल प्राप्त करने का प्रयास करें
            try:
                # यदि बॉट ग्रुप से हटा दिया गया है, तो यह API कॉल विफल हो जाएगा
                group_info = bot.get_chat(chat_id) 
                
                # सुनिश्चित करें कि बॉट अभी भी ग्रुप में है (get_chat() सफल होने का मतलब है कि ग्रुप मौजूद है)
                
                managed_groups.append({
                    'id': chat_id, 
                    'title': group_info.title
                })
            except telebot.apihelper.ApiTelegramException as e:
                # यदि चैट नहीं मिली (बॉट को हटा दिया गया या पहुँच नहीं है), तो इसे नज़रअंदाज़ करें
                if 'chat not found' in str(e) or 'not a member of the chat' in str(e):
                    logging.warning(f"Bot removed or chat not found for ID: {chat_id}")
                else:
                    logging.error(f"Error fetching chat info for {chat_id}: {e}")
                pass
            except Exception as e:
                logging.error(f"Unexpected error fetching chat info for {chat_id}: {e}")
                pass
    return managed_groups
    

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

# ---------- Logging & Analytics (existing, preserved) ----------
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

# ---------- User Info Helpers (existing, preserved) ----------
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

# ---------- Punishment System (existing, preserved) ----------
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

# ---------- Flood Protection (existing, preserved) ----------
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

# ---------- Blacklist System (existing, preserved) ----------
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

# ---------- Locks System (existing, preserved) ----------
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

# ---------- Captcha System (existing, preserved) ----------
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
        try:
            if int(answer) == correct:
                del pending_captcha[key]
                return True
        except ValueError:
            pass # Invalid input, treat as incorrect
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

# ---------- XP System (XP & Ranking) (existing, preserved logic) ----------
def add_xp(chat_id, user_id, points=1):
    "Add XP to user, respecting cooldown and enable flag"
    chat_id_str = str(chat_id)
    user_id_str = str(user_id)
    
    # Check XP system enablement and cooldown from menu_json
    menu_data = menu_get(chat_id_str)
    xp_settings = menu_data.get('xp_settings', {})
    
    # Default to enabled=True and 60s cooldown if not set
    xp_enabled = xp_settings.get('xp_enabled', 1) 
    cooldown = xp_settings.get('xp_cooldown', 60)
    
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

# ----------------------------------------------------------------------
# -------------------- UX/Menu Overhaul Functions ----------------------
# ----------------------------------------------------------------------

# ---------- Menu Builder Helper (Point 1, 19) ----------
def build_toggle_row(chat_id, key, value, desc_key, target_id=None):
    """
    Creates a description text and an InlineKeyboardMarkup row with a state-first toggle button.
    
    Args:
        chat_id: The ID of the chat (used for translation).
        key: The unique callback key suffix (e.g., 'welcome_enabled').
        value: The current state (True/False or 1/0).
        desc_key: The translation key for the setting's title (e.g., 'welcome').
        target_id: The target group chat_id if operating in private chat context.
        
    Returns:
        (desc_html_line: str, keyboard_row: list of InlineKeyboardButton)
    """
    chat_id_str = str(chat_id)
    
    # 1. Description Text (UX Rule 1)
    desc_title = _(chat_id_str, desc_key)
    desc_full_key = desc_key + '_desc' # Use key_desc for full description
    desc_full = _(chat_id_str, desc_full_key) 
    
    # 2. Toggle Button Text (State-First) (UX Rule 2)
    is_enabled = bool(value)
    state_text = _(chat_id_str, 'enabled') if is_enabled else _(chat_id_str, 'disabled')
    
    # Prefix callback data with target_id if in private context (Point 16)
    target_id_prefix = f"{target_id}:" if target_id else ""
    # format: toggle:[target_id]:[key]:[new_value]
    callback_data = f"toggle:{target_id_prefix}{key}:{int(not is_enabled)}" 
    
    # HTML formatted description line
    desc_html_line = f"<b>{desc_title}</b>: <i>{desc_full}</i>"
    
    # Keyboard row (State-first button + descriptive label/empty button)
    row = [
        types.InlineKeyboardButton(state_text, callback_data=callback_data),
        types.InlineKeyboardButton(desc_title, callback_data="ignore_label") 
    ]
    
    return desc_html_line, row

def _get_db_counts(chat_id):
    """Helper to get counts for menu descriptions."""
    conn = db()
    counts = {
        'notes': conn.execute("SELECT COUNT(*) FROM notes WHERE chat_id=?", (str(chat_id),)).fetchone()[0],
        'triggers': conn.execute("SELECT COUNT(*) FROM triggers WHERE chat_id=?", (str(chat_id),)).fetchone()[0],
        'polls': conn.execute("SELECT COUNT(*) FROM polls WHERE chat_id=? AND open=1", (str(chat_id),)).fetchone()[0],
        'blacklist': conn.execute("SELECT COUNT(*) FROM blacklist WHERE chat_id=?", (str(chat_id),)).fetchone()[0],
    }
    conn.close()
    return counts

# ---------- Sub-Menu Builder Implementations (Point 2, 4, 6, 8, 10, 11) ----------

def _build_settings_menu(chat_id, settings, target_id):
    """Builds the main settings menu with toggles."""
    chat_id_str = str(chat_id)
    
    desc_lines = [_(chat_id_str, 'settings_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    # Welcome Toggle
    welcome_desc, welcome_kb = build_toggle_row(chat_id, 'welcome_enabled', settings.get('welcome_enabled', 1), 'welcome', target_id)
    desc_lines.append(welcome_desc)
    keyboard.add(*welcome_kb)
    
    # Leave Toggle
    leave_desc, leave_kb = build_toggle_row(chat_id, 'leave_enabled', settings.get('leave_enabled', 1), 'leave', target_id)
    desc_lines.append(leave_desc)
    keyboard.add(*leave_kb)
    
    # Blacklist Toggle
    blacklist_desc, blacklist_kb = build_toggle_row(chat_id, 'blacklist_enabled', settings.get('blacklist_enabled', 1), 'blacklist_toggle', target_id)
    desc_lines.append(blacklist_desc)
    keyboard.add(*blacklist_kb)

    return "\n\n".join(desc_lines), keyboard

def _build_locks_menu(chat_id, locks, target_id):
    """Builds the Locks menu with all lock toggles."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'locks_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    # Lock Keys: {db_key: lang_key}
    lock_keys = {
        'urls': 'lock_urls', 
        'photos': 'lock_photos', 
        'videos': 'lock_videos',
        'stickers': 'lock_stickers', 
        'forwards': 'lock_forwards', 
        'documents': 'lock_documents',
    }
    
    # Rows of two toggles
    row = []
    for key, desc_key in lock_keys.items():
        value = locks.get(key, 0)
        desc, kb = build_toggle_row(chat_id, f"lock_{key}", value, desc_key, target_id)
        
        # Add the toggle button, ignoring the descriptive part of kb
        row.append(kb[0]) 
        
        # Every two buttons forms a row (or the last one alone)
        if len(row) == 2:
            keyboard.add(*row)
            row = []
        
        # The description line is added outside the loop based on the descriptive kb part
        desc_lines.append(desc) 
    
    if row:
        keyboard.add(*row)
    
    return "\n\n".join(desc_lines), keyboard

def _build_xp_system_menu(chat_id, target_id):
    """Builds the XP system main menu."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'xp_desc')]
    keyboard = types.InlineKeyboardMarkup()

    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'xp_settings'), callback_data=f"menu:{target_id}:xp_settings"),
        types.InlineKeyboardButton(_(chat_id_str, 'leaderboard'), callback_data=f"xp:{target_id}:leaderboard")
    )
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'my_rank'), callback_data=f"xp:{target_id}:my_rank")
    )

    return "\n\n".join(desc_lines), keyboard

def _build_xp_settings_menu(chat_id, menu_data, target_id):
    """Builds the XP Settings sub-menu (Point 4)."""
    chat_id_str = str(chat_id)
    xp_settings = menu_data.get('xp_settings', {})
    
    desc_lines = [_(chat_id_str, 'xp_settings_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    # XP Enabled Toggle
    # Note: 'xp_enabled' toggle uses 'menu:xp_settings:xp_enabled' as key, so the toggle: handler must be generic
    xp_enabled = xp_settings.get('xp_enabled', 1) 
    xp_desc, xp_kb = build_toggle_row(chat_id, 'menu:xp_settings:xp_enabled', xp_enabled, 'xp_enabled', target_id)
    desc_lines.append(xp_desc)
    keyboard.add(*xp_kb)

    # Cooldown Setting
    cooldown = xp_settings.get('xp_cooldown', 60)
    cooldown_desc = _(chat_id_str, 'xp_cooldown_desc')
    
    desc_lines.append(f"\n<b>{_(chat_id_str, 'xp_cooldown')}:</b> {cooldown}s <i>({cooldown_desc})</i>")
    
    # Cooldown buttons (Point 4 - control)
    keyboard.add(
        types.InlineKeyboardButton("-10s", callback_data=f"xp:{target_id}:cooldown:-10"),
        types.InlineKeyboardButton(f"Cool: {cooldown}s", callback_data="ignore_label"),
        types.InlineKeyboardButton("+10s", callback_data=f"xp:{target_id}:cooldown:+10")
    )
    
    return "\n\n".join(desc_lines), keyboard

def _build_triggers_menu(chat_id, counts, target_id):
    """Builds the Triggers menu (Point 5, 6)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'triggers_desc')]
    keyboard = types.InlineKeyboardMarkup()

    desc_lines.append(f"<i>{_(chat_id_str, 'triggers_desc')}</i> (<b>{_(chat_id_str, 'notes')}: {counts['triggers']}</b>)")
    
    # Add/List buttons
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'add_trigger'), callback_data=f"trigger:{target_id}:add"),
        types.InlineKeyboardButton(_(chat_id_str, 'list_triggers'), callback_data=f"trigger:{target_id}:list")
    )
    
    # Placeholder for displaying existing triggers (Point 5)
    # The list view will be a separate menu type (not implemented here yet)
    desc_lines.append(f"\n💡 {_(chat_id_str, 'list_triggers')} बटन दबाकर सक्रिय ट्रिगर्स देखें।")
    
    return "\n\n".join(desc_lines), keyboard

def _build_notes_menu(chat_id, counts, target_id):
    """Builds the Notes menu (Point 6)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'notes_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    desc_lines.append(f"<i>{_(chat_id_str, 'notes_desc')}</i> (<b>{_(chat_id_str, 'notes')}: {counts['notes']}</b>)")

    # Add/List buttons
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'add_note'), callback_data=f"note:{target_id}:add"),
        types.InlineKeyboardButton(_(chat_id_str, 'list_notes'), callback_data=f"note:{target_id}:list")
    )
    
    return "\n\n".join(desc_lines), keyboard

def _build_blacklist_menu(chat_id, counts, target_id):
    """Builds the Blacklist menu (Point 8)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'blacklist_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    desc_lines.append(f"<i>{_(chat_id_str, 'blacklist_desc')}</i> (<b>{_(chat_id_str, 'blacklist')}: {counts['blacklist']}</b>)")
    
    # Add/List buttons
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'add_word'), callback_data=f"blacklist:{target_id}:add"),
        types.InlineKeyboardButton(_(chat_id_str, 'list_words'), callback_data=f"blacklist:{target_id}:list")
    )
    
    return "\n\n".join(desc_lines), keyboard

def _build_commands_menu(chat_id, target_id):
    """Builds the Commands menu (Point 9)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'cmd_perms_desc')]
    keyboard = types.InlineKeyboardMarkup()

    # Moderation commands are fixed (Point 9)
    desc_lines.append(f"🛡️ <b>Moderation Commands:</b> <i>/warn, /mute, /ban, /kick</i>\n   - {_(chat_id_str, 'fixed_admin_perm')}")
    
    # Placeholder for other custom command permission management
    keyboard.add(
        types.InlineKeyboardButton(f"{_(chat_id_str, 'commands')} - WIP", callback_data="unknown") 
    )

    return "\n\n".join(desc_lines), keyboard

def _build_polls_menu(chat_id, counts, target_id):
    """Builds the Polls menu (Point 7)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'polls_desc')]
    keyboard = types.InlineKeyboardMarkup()
    
    desc_lines.append(f"<i>{_(chat_id_str, 'polls_desc')}</i> (<b>{_(chat_id_str, 'polls')}: {counts['polls']}</b>)")

    # Create/Active buttons
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'create_poll'), callback_data=f"poll:{target_id}:create"),
        types.InlineKeyboardButton(_(chat_id_str, 'active_polls'), callback_data=f"poll:{target_id}:active")
    )
    
    return "\n\n".join(desc_lines), keyboard

def _build_moderation_menu(chat_id):
    """Builds the Moderation menu (Point 10)."""
    chat_id_str = str(chat_id)
    desc_lines = [_(chat_id_str, 'moderation_desc')]
    keyboard = types.InlineKeyboardMarkup()

    # Inform the user how to use commands
    desc_lines.append("\n💡 <b>Usage:</b> किसी भी मैसेज को <b>reply</b> करके कमांड का उपयोग करें।\n   जैसे: <i>/warn</i>, <i>/mute 1h</i>, <i>/ban</i>")
    
    # Dummy buttons for visual guidance (no action, only ignore_label)
    keyboard.add(
        types.InlineKeyboardButton("Warn", callback_data="ignore_label"),
        types.InlineKeyboardButton("Mute", callback_data="ignore_label"),
        types.InlineKeyboardButton("Ban", callback_data="ignore_label"),
        types.InlineKeyboardButton("Kick", callback_data="ignore_label")
    )

    return "\n\n".join(desc_lines), keyboard


# ---------- Menu Rendering (Point 2, 12, 13, 18, 19) ----------
def send_menu(chat_id, user_id, menu_type, message_id=None, is_private=False, group_title="", target_group_id=None):
    "Generates and sends/edits the specified menu"
    chat_id_str = str(chat_id)
    settings = get_settings(chat_id_str)
    
    # Contextual chat ID for settings actions (private mode uses target_group_id)
    # If target_group_id is provided (for private chat), use it for data fetching
    data_chat_id = str(target_group_id) if target_group_id else chat_id_str
    
    # 1. Fetch data required for descriptions/menus
    data_settings = get_settings(data_chat_id)
    data_locks = locks_get(data_chat_id)
    data_menu = menu_get(data_chat_id)
    counts = _get_db_counts(data_chat_id)
    
    # 2. Build Menu
    keyboard = types.InlineKeyboardMarkup()
    
    # Initial description line
    if is_private and target_group_id:
        # Private chat context for a specific group
        title_line = _(chat_id_str, 'menu_in_private_opened', title=safe_html(group_title))
    else:
        # Normal main menu in group or private
        title_line = _(chat_id_str, 'main_menu_desc')
    
    desc_lines = [title_line]
    
    # Target ID for callback data (used in sub-menus)
    callback_target_id = f"{data_chat_id}" 
    
    # --- Main Menu ---
    if menu_type == 'main':
        
        # [Settings] [Moderation]
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'settings'), callback_data=f"menu:{callback_target_id}:settings"),
            types.InlineKeyboardButton(_(chat_id_str, 'moderation'), callback_data=f"menu:{callback_target_id}:moderation")
        )
        
        # [Locks] [XP System]
        keyboard.add(
            types.InlineKeyboardButton(_(chat_id_str, 'locks'), callback_data=f"menu:{callback_target_id}:locks"),
            types.InlineKeyboardButton(_(chat_id_str, 'xp_system'), callback_data=f"menu:{callback_target_id}:xp_system")
        )
        
        # [Notes] [Triggers]
        notes_btn_text = f"{_(chat_id_str, 'notes')} ({counts['notes']})"
        triggers_btn_text = f"{_(chat_id_str, 'triggers')} ({counts['triggers']})"
        keyboard.add(
            types.InlineKeyboardButton(notes_btn_text, callback_data=f"menu:{callback_target_id}:notes"),
            types.InlineKeyboardButton(triggers_btn_text, callback_data=f"menu:{callback_target_id}:triggers")
        )
        
        # [Blacklist] [Commands]
        blacklist_btn_text = f"{_(chat_id_str, 'blacklist')} ({counts['blacklist']})"
        keyboard.add(
            types.InlineKeyboardButton(blacklist_btn_text, callback_data=f"menu:{callback_target_id}:blacklist"),
            types.InlineKeyboardButton(_(chat_id_str, 'commands'), callback_data=f"menu:{callback_target_id}:commands")
        )
        
        # [Polls] [Language] (Point 4)
        polls_btn_text = f"{_(chat_id_str, 'polls')} ({counts['polls']})"
        lang_btn_text = f"🌐 {_(chat_id_str, 'language')}: {data_settings['lang'].upper()}"
        keyboard.add(
            types.InlineKeyboardButton(polls_btn_text, callback_data=f"menu:{callback_target_id}:polls"),
            types.InlineKeyboardButton(lang_btn_text, callback_data=f"lang:{callback_target_id}:toggle")
        )
        
    # --- Settings Menu (Point 1, 2, 19) ---
    elif menu_type == 'settings':
        desc, kb = _build_settings_menu(chat_id, data_settings, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard # Replace keyboard rows
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))
    
    # --- Moderation Menu (Point 10) ---
    elif menu_type == 'moderation':
        desc, kb = _build_moderation_menu(chat_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))

    # --- Locks Menu (Point 5, 19) ---
    elif menu_type == 'locks':
        desc, kb = _build_locks_menu(chat_id, data_locks, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))
        
    # --- XP System Menu (Point 8, 19) ---
    elif menu_type == 'xp_system':
        desc, kb = _build_xp_system_menu(chat_id, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))

    # --- XP Settings Sub-Menu (Point 4, 19) ---
    elif menu_type == 'xp_settings':
        desc, kb = _build_xp_settings_menu(chat_id, data_menu, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:xp_system"))

    # --- Triggers Menu (Point 5, 19) ---
    elif menu_type == 'triggers':
        desc, kb = _build_triggers_menu(chat_id, counts, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))
        
    # --- Notes Menu (Point 6, 19) ---
    elif menu_type == 'notes':
        desc, kb = _build_notes_menu(chat_id, counts, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))

    # --- Blacklist Menu (Point 8, 19) ---
    elif menu_type == 'blacklist':
        desc, kb = _build_blacklist_menu(chat_id, counts, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))

    # --- Commands Menu (Point 9, 19) ---
    elif menu_type == 'commands':
        desc, kb = _build_commands_menu(chat_id, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))

    # --- Polls Menu (Point 7, 19) ---
    elif menu_type == 'polls':
        desc, kb = _build_polls_menu(chat_id, counts, callback_target_id)
        desc_lines.append(desc)
        keyboard.keyboard = kb.keyboard
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{callback_target_id}:main"))
        
    # --- Fallback/Unknown Menu ---
    else:
        desc_lines.append(_(chat_id_str, 'unknown_action'))
        keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'main_menu'), callback_data=f"menu:{callback_target_id}:main"))
        
    # Final message assembly
    menu_text = "\n\n".join(desc_lines)
    
    try:
        if message_id:
            # Edit existing message
            bot.edit_message_text(
                menu_text,
                chat_id,
                message_id,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            # Send new message
            bot.send_message(
                chat_id,
                menu_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
    except Exception as e:
        # Handle message not modified error
        if 'message is not modified' in str(e):
            logging.info(f"Menu not modified: {menu_type} in {chat_id}")
        else:
            logging.error(f"Error sending/editing menu: {e}")


# -------------------- Telegram Message Handler (इस ब्लॉक से मौजूदा handle_start_menu फ़ंक्शन को बदलें) --------------------

# ---------- Commands: /start and /menu (Modified for private chat UX) ----------
@bot.message_handler(commands=['start', 'menu'])
def handle_start_menu(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # 1. Private Chat Flow
    if message.chat.type == 'private':
        
        # A. Deep-linking Check (e.g., /start -123456789)
        # यह तब होता है जब यूज़र ग्रुप से 'Open in private' बटन क्लिक करता है।
        try:
            # message.text.split() यह सुनिश्चित करता है कि यह /start के बाद के पैरामीटर को उठाता है।
            parts = message.text.split()
            if len(parts) > 1:
                target_group_id = parts[1]
                # ID नेगेटिव होनी चाहिए (ग्रुप/सुपरग्रुप)
                if target_group_id.startswith('-100') or target_group_id.startswith('-'):
                    
                    # 1. जाँच करें कि यूज़र उस ग्रुप का क्रिएटर है या नहीं
                    if not is_creator_member(target_group_id, user_id):
                        bot.send_message(
                            chat_id, 
                            "❌ आप इस ग्रुप के क्रिएटर नहीं हैं, इसलिए सेटिंग्स को एक्सेस नहीं कर सकते।"
                        )
                        return
                        
                    # 2. Group info प्राप्त करें
                    try:
                        group_info = bot.get_chat(target_group_id)
                        group_title = group_info.title
                    except Exception:
                        group_title = target_group_id
                        
                    # सीधे ग्रुप की main settings मेन्यू भेजें
                    send_menu(chat_id, user_id, 'main', is_private=True, group_title=group_title, target_group_id=target_group_id)
                    return
        
        except Exception:
            # IndexError या अन्य त्रुटि, जिसका अर्थ है कि यह सामान्य /start है
            pass 
            
        # B. Normal /start in private chat (Your requested UX)
        
        managed_groups = get_user_managed_groups(user_id)
        keyboard = types.InlineKeyboardMarkup()

        # 1. Add Bot to Group Button
        add_bot_url = f"https://t.me/{BOT_USERNAME}?startgroup=start"
        keyboard.add(
             types.InlineKeyboardButton("➕ Bot को ग्रुप में जोड़ें (Add to Group)", url=add_bot_url)
        )
        
        menu_text = "👋 Bot में आपका स्वागत है!\n\nनीचे अपने ग्रुप को प्रबंधित करने या बॉट को नए ग्रुप में जोड़ने का विकल्प चुनें।"
        
        # 2. Managed Groups Buttons
        if managed_groups:
            keyboard.add(types.InlineKeyboardButton("➖", callback_data="ignore_label")) # Separator
            keyboard.add(types.InlineKeyboardButton("⚙️ आपके प्रबंधित ग्रुप ⚙️", callback_data="ignore_label"))
            for group in managed_groups:
                # यह बटन deep-linking URL का उपयोग करता है: /start <group_id>
                manage_link = f"https://t.me/{BOT_USERNAME}?start={group['id']}"
                keyboard.add(
                    types.InlineKeyboardButton(f"➡️ {group['title']}", url=manage_link)
                )
        else:
             menu_text = menu_text + "\n\n**कोई प्रबंधित ग्रुप नहीं मिला।** Bot को अपने ग्रुप में जोड़ें और सुनिश्चित करें कि आप ग्रुप क्रिएटर हैं।"

        bot.send_message(
            chat_id, 
            menu_text, 
            disable_web_page_preview=True,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    # 2. Group Chat Flow (or Supergroup - logic remains same)
    if message.chat.type in ['group', 'supergroup']:
        chat_id_str = str(chat_id)
        
        # Check bot permissions
        permissions = check_bot_permissions(chat_id)
        is_admin = permissions.get('is_admin', False)
        
        # Check if the user running the command is the group creator (Point 13)
        is_creator = is_creator_member(chat_id, user_id)
        
        keyboard = types.InlineKeyboardMarkup()
        
        if not is_admin:
            # Bot is not admin (show setup message/button)
            menu_text = _(chat_id_str, 'start_group_not_admin')
            # Add a button to easily find the bot (optional, but good UX)
            keyboard.add(
                 types.InlineKeyboardButton("➕ Add Bot as Admin", url=f"https://t.me/{BOT_USERNAME}?startgroup=start")
            )
            bot.send_message(chat_id, menu_text, reply_markup=keyboard)
            return

        # Bot is admin, show main menu
        if is_creator:
            # Group creator can see the main menu directly in the group, 
            # and gets an option to move to private chat (Point 12)
            
            # 1. Build the main menu
            # Send as new message if /start, edit if /menu (if message_id is available)
            send_menu(chat_id, user_id, 'main') 
            
            # 2. Add the private chat prompt/button (Point 13)
            private_kb = types.InlineKeyboardMarkup()
            # Callback is handled by Telegram's deep-linking /start command
            private_link = f"https://t.me/{BOT_USERNAME}?start={chat_id_str}"
            private_kb.add(
                types.InlineKeyboardButton(_(chat_id_str, 'menu_in_private_button'), url=private_link)
            )
            
            # Send the prompt separately
            bot.send_message(
                chat_id,
                f"<i>{_(chat_id_str, 'menu_in_private_prompt')}</i>",
                reply_markup=private_kb,
                parse_mode="HTML"
            )
            
        else:
            # Regular admin/user in group: show a simple message that only the creator can access settings
            bot.reply_to(message, _(chat_id_str, 'admin_only'))

            
# ---------- Callback Inline Handler (Point 3, 15, 16, 17) ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id
    data = call.data
    
    # Logging the callback (Point 17)
    logging.info(f"Callback from {user_id} in {chat_id}: {data}")

    # --- Pre-Check: Admin/Creator check ---
    # In private chat, the user must be the creator of the target group
    # Format: action:target_id:key:value
    
    # Parse data: [action, target_id, ...]
    parts = data.split(':')
    action = parts[0]
    
    # Determine the chat ID where settings are applied (target_id)
    # If in private chat, the target_id is the group's chat_id
    target_id = parts[1] if len(parts) > 1 and parts[1].startswith('-') else str(chat_id)

    # If in private chat mode (target_id is a group ID), check if user is creator of that group
    if str(chat_id).startswith('-') and target_id == str(chat_id):
        # User clicked a button in a group, target is the same group
        is_allowed = is_creator_member(chat_id, user_id)
        if not is_allowed:
            bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
            return
    elif str(chat_id).startswith('-') and target_id.startswith('-'):
        # User clicked a button in a group, but target_id is different (shouldn't happen with current flow)
        is_allowed = is_creator_member(target_id, user_id)
        if not is_allowed:
            bot.answer_callback_query(call.id, _(target_id, 'admin_only'), show_alert=True)
            return
    elif not str(chat_id).startswith('-') and target_id.startswith('-'):
        # User clicked a button in private chat, target is a group (Must be creator of target_id)
        is_allowed = is_creator_member(target_id, user_id)
        if not is_allowed:
            bot.answer_callback_query(call.id, _(target_id, 'admin_only'), show_alert=True)
            return
    elif not str(chat_id).startswith('-') and target_id == str(chat_id):
        # User clicked a button in private chat, target is private chat itself (like language toggle)
        is_allowed = True # Always allowed in private chat
    else:
        # User clicked a button in a group, target is the same group (Standard check)
        is_allowed = is_admin_member(chat_id, user_id)
        if not is_allowed:
            bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
            return


    # --- Ignore Label ---
    if data == 'ignore_label':
        bot.answer_callback_query(call.id, "")
        return
        
    # --- Menu Navigation (Point 2) ---
    if action == 'menu':
        menu_type = parts[2]
        # In private chat context, need to pass group title for re-rendering the header
        group_title = ""
        if not str(chat_id).startswith('-'):
            try:
                group_title = bot.get_chat(target_id).title
            except:
                pass

        send_menu(chat_id, user_id, menu_type, message_id=message_id, is_private=True, group_title=group_title, target_group_id=target_id)
        bot.answer_callback_query(call.id)
        return

    # --- Language Toggle (Point 3, 15) ---
    elif action == 'lang':
        old_lang = get_settings(target_id).get('lang', 'hi')
        new_lang = 'en' if old_lang == 'hi' else 'hi'
        set_setting(target_id, 'lang', new_lang)
        
        # Log language change
        log_action(target_id, user_id, f"lang_change:{new_lang}")
        
        # Re-render the menu instantly
        send_menu(chat_id, user_id, 'main', message_id=message_id, target_group_id=target_id)
        bot.answer_callback_query(call.id, _(target_id, 'lang_changed'))
        return

    # --- Generic Toggle Handler (Point 1, 3, 16) ---
    elif action == 'toggle':
        # Data format: toggle:[target_id]:[key]:[new_value]
        key = parts[2]
        value = int(parts[3])
        
        setting_key = key
        
        # Check if it's a menu_json key (e.g., menu:xp_settings:xp_enabled)
        if key.startswith('menu:'):
            # Format: menu:submenu:setting_key
            _, submenu, setting_key = key.split(':') 
            menu_data = menu_get(target_id)
            if submenu not in menu_data:
                menu_data[submenu] = {}
            menu_data[submenu][setting_key] = value
            menu_set(target_id, menu_data)
            menu_type = submenu # Use submenu to re-render the correct view
        
        # Check if it's a lock setting (e.g., lock_urls)
        elif key.startswith('lock_'):
            lock_key = key.replace('lock_', '')
            locks_data = locks_get(target_id)
            locks_data[lock_key] = value
            locks_set(target_id, locks_data)
            menu_type = 'locks' # Use 'locks' to re-render
            
        # Standard settings (e.g., welcome_enabled)
        else:
            set_setting(target_id, setting_key, value)
            menu_type = 'settings' # Use 'settings' to re-render
        
        # Log the action (Point 17)
        log_action(target_id, user_id, f"toggle:{key}:{value}")
        
        # Re-render the menu instantly
        # If in private chat, target_id is the group.
        group_title = ""
        if not str(chat_id).startswith('-'):
            try:
                group_title = bot.get_chat(target_id).title
            except:
                pass
                
        send_menu(chat_id, user_id, menu_type, message_id=message_id, is_private=True, group_title=group_title, target_group_id=target_id)
        bot.answer_callback_query(call.id, _(target_id, 'setting_updated'))
        return

    # --- XP Cooldown Change (Point 4) ---
    elif action == 'xp':
        sub_action = parts[2]
        
        if sub_action == 'cooldown':
            change = int(parts[3])
            
            menu_data = menu_get(target_id)
            xp_settings = menu_data.get('xp_settings', {})
            current_cooldown = xp_settings.get('xp_cooldown', 60)
            
            new_cooldown = max(5, current_cooldown + change) # Minimum 5 seconds
            
            xp_settings['xp_cooldown'] = new_cooldown
            menu_data['xp_settings'] = xp_settings
            menu_set(target_id, menu_data)
            
            log_action(target_id, user_id, f"xp_cooldown:{new_cooldown}")
            
            # Re-render XP settings menu
            send_menu(chat_id, user_id, 'xp_settings', message_id=message_id, target_group_id=target_id)
            bot.answer_callback_query(call.id, _(target_id, 'setting_updated'))
            return

        elif sub_action == 'leaderboard' or sub_action == 'my_rank':
            # Basic implementation for now (Point 4 - functional)
            
            if sub_action == 'my_rank':
                # Get rank and XP for the user who clicked the button (user_id)
                rank, xp = get_rank(target_id, user_id)
                user_info = bot.get_chat_member(target_id, user_id).user
                name = get_user_display_name(user_info)
                
                response_text = _(target_id, 'rank_display', name=safe_html(name), rank=rank, xp=xp)
                bot.answer_callback_query(call.id, response_text, show_alert=True)
                return
            
            elif sub_action == 'leaderboard':
                # Fetch leaderboard
                conn = db()
                c = conn.cursor()
                c.execute("SELECT user_id, points FROM xp WHERE chat_id=? ORDER BY points DESC LIMIT 10", 
                          (target_id,))
                leaderboard = c.fetchall()
                conn.close()
                
                # Build leaderboard message
                lb_text = "🏆 <b>Top 10 Leaderboard</b> 🏆\n\n"
                for i, row in enumerate(leaderboard):
                    try:
                        member = bot.get_chat_member(target_id, row['user_id'])
                        name = get_user_display_name(member.user)
                    except:
                        name = f"User {row['user_id']}"
                        
                    lb_text += f"#{i+1}: {safe_html(name)} - {row['points']} XP\n"
                    
                if not leaderboard:
                    lb_text += "No XP data yet."
                    
                bot.answer_callback_query(call.id, "Leaderboard fetched.", show_alert=False)
                bot.send_message(chat_id, lb_text)
                return

    # --- Other Modules (Notes, Triggers, Blacklist, Polls) - Basic Wiring ---
    # These will initiate multi-step STATE flow or list functions (Point 3, 5, 6, 7, 8)
    elif action in ['note', 'trigger', 'blacklist', 'poll']:
        sub_action = parts[2]
        
        # Example: Initiating 'add' flow (which requires state handling)
        if sub_action == 'add' or sub_action == 'create':
            # Set state for the next user message to be captured
            STATE[(chat_id, user_id)] = {'action': f'{action}_wait_for_key', 'target_id': target_id}
            
            if action == 'note':
                prompt = _(target_id, 'usage', usage="Note key और content भेजें, जैसे: <code>!rules The group rules are...</code>")
            elif action == 'trigger':
                prompt = _(target_id, 'usage', usage="Trigger pattern और reply भेजें, जैसे: <code>!hello Hi there!</code>")
            elif action == 'blacklist':
                prompt = _(target_id, 'usage', usage="ब्लैकलिस्ट करने के लिए शब्द भेजें। एक समय में एक शब्द।")
            elif action == 'poll':
                prompt = _(target_id, 'usage', usage="Poll का प्रश्न और विकल्पों को नई लाइन में भेजें। \nउदाहरण: \n<code>Favourite colour?\nRed\nBlue\nGreen</code>")
            else:
                prompt = _(target_id, 'invalid_input')
                
            bot.send_message(chat_id, prompt)
            bot.answer_callback_query(call.id, f"Waiting for {action} input...")
            return
            
        # Example: Listing flow (requires fetching data)
        elif sub_action == 'list' or sub_action == 'active':
            # Placeholder for listing logic (to be expanded in subsequent parts)
            list_text = f"📋 {action.capitalize()} List (WIP)\n"
            
            conn = db()
            c = conn.cursor()
            
            if action == 'note':
                c.execute("SELECT key, content FROM notes WHERE chat_id=?", (target_id,))
                for row in c.fetchall():
                    list_text += f"<b>{safe_html(row['key'])}</b>: {safe_html(row['content'][:30])}...\n"
                
            elif action == 'trigger':
                c.execute("SELECT pattern, reply FROM triggers WHERE chat_id=?", (target_id,))
                for row in c.fetchall():
                    list_text += f"<b>{safe_html(row['pattern'])}</b>: {safe_html(row['reply'][:30])}...\n"
            
            elif action == 'blacklist':
                c.execute("SELECT word FROM blacklist WHERE chat_id=?", (target_id,))
                words = [row['word'] for row in c.fetchall()]
                list_text += ", ".join(words)
            
            elif action == 'poll':
                c.execute("SELECT id, question FROM polls WHERE chat_id=? AND open=1", (target_id,))
                for row in c.fetchall():
                    list_text += f"<b>ID {row['id']}</b>: {safe_html(row['question'][:50])}...\n"
                
            conn.close()
            
            bot.send_message(chat_id, list_text)
            bot.answer_callback_query(call.id, f"Listing {action}s...")
            return

    # --- Fallback for Unknown Action (Point 17) ---
    else:
        logging.warning(f"Unknown callback action: {data}")
        bot.answer_callback_query(call.id, _(target_id, 'unknown_action'), show_alert=True)
        # Re-render main menu as a safe fallback
        send_menu(chat_id, user_id, 'main', message_id=message_id, target_group_id=target_id)
        return

# ---------- Message Handler (Text & All Content) ----------
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text)
def handle_group_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text
    
    # Ignore commands (handled elsewhere)
    if text.startswith('/') and len(text.split()) > 0 and text.split()[0][1:] in ['start', 'menu', 'warn', 'mute', 'ban', 'kick', 'undo', 'rank', 'leaderboard']:
        return
        
    # 1. Captcha Check (If user is pending)
    if (chat_id, user_id) in pending_captcha:
        if verify_captcha(chat_id, user_id, text):
            # Captcha success
            unrestrict_user(chat_id, user_id)
            name = get_user_mention(message.from_user)
            bot.reply_to(message, _(chat_id, 'captcha_success', name=name))
            log_action(chat_id, user_id, "captcha_passed")
        else:
            # Captcha failure
            # Delete message and re-ask
            try:
                bot.delete_message(chat_id, message.message_id)
            except:
                pass
            
            q1, q2 = pending_captcha[(chat_id, user_id)]['q1'], pending_captcha[(chat_id, user_id)]['q2']
            bot.send_message(chat_id, _(chat_id, 'captcha_failed') + " " + _(chat_id, 'captcha_verify', q1=q1, q2=q2))
            log_action(chat_id, user_id, "captcha_failed")
        return
        
    # 2. Command Permissions Check (if user sends non-standard commands)
    # The default command handlers will do the check, but this ensures a fallback message
    # for custom commands (not fully implemented here, but preserved logic)
    
    # 3. Flood Check
    is_flood, count, limit = check_flood(chat_id, user_id)
    if is_flood:
        bot.delete_message(chat_id, message.message_id)
        bot.send_message(chat_id, _(chat_id, 'flood_detected', count=count, limit=limit))
        mute_user(chat_id, user_id, 300) # Mute for 5 minutes
        log_action(chat_id, user_id, "auto_mute:flood")
        return
        
    # 4. Blacklist Check (settings must be enabled)
    settings = get_settings(chat_id)
    if settings.get('blacklist_enabled'):
        found, word, _ = check_blacklist(chat_id, text)
        if found:
            bot.delete_message(chat_id, message.message_id)
            count, is_banned = add_blacklist_violation(chat_id, user_id)
            user_mention = get_user_mention(message.from_user)
            
            if is_banned:
                action_text = _(chat_id, 'user_banned', user=user_mention)
            else:
                action_text = _(chat_id, 'blacklist_violation', count=count)
                
            bot.send_message(chat_id, action_text)
            return
            
    # 5. Lock Check (for text-based locks like URLs)
    violations = check_locks(chat_id, message)
    if 'urls' in violations:
        bot.delete_message(chat_id, message.message_id)
        bot.send_message(chat_id, f"❌ {_(chat_id, 'lock_urls')} {_(chat_id, 'disabled')}")
        return

    # 6. XP Gain (If enabled and not on cooldown)
    if add_xp(chat_id, user_id, 1):
        # Notify user of XP gain (optional, but requested in past logic)
        # bot.send_message(chat_id, _(chat_id, 'xp_gained', points=1), reply_to_message_id=message.message_id)
        pass
        
    # 7. Trigger Check (Basic logic preserved)
    conn = db()
    c = conn.cursor()
    c.execute("SELECT reply, is_regex FROM triggers WHERE chat_id=?", (str(chat_id),))
    triggers = c.fetchall()
    conn.close()
    
    for row in triggers:
        pattern = row['pattern']
        reply = row['reply']
        is_regex = row['is_regex']
        
        match = False
        if is_regex:
            try:
                if re.search(pattern, text, re.IGNORECASE):
                    match = True
            except re.error:
                # Log bad regex
                pass 
        elif text.lower().startswith(pattern.lower()):
            match = True
            
        if match:
            bot.send_message(chat_id, reply)
            log_action(chat_id, user_id, f"trigger_match:{pattern}")
            return


# ---------- Message Handler (All Content - for Locks/Forwards) ----------
@bot.message_handler(content_types=['photo', 'video', 'sticker', 'document', 'forward', 'audio', 'voice', 'video_note', 'new_chat_members', 'left_chat_member', 'location', 'contact', 'animation', 'poll', 'game', 'dice'])
def handle_all_content(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Ignore new/left members events for lock check
    if message.content_type in ['new_chat_members', 'left_chat_member']:
        return
        
    # 1. Lock Check (for media/forwards)
    violations = check_locks(chat_id, message)
    
    if violations:
        # Delete message and notify (Point 14)
        try:
            bot.delete_message(chat_id, message.message_id)
            
            # Use the first violation type for the notification
            violation_key = f"lock_{violations[0]}" 
            
            # Send a localized lock message
            bot.send_message(
                chat_id, 
                f"❌ {_(chat_id, violation_key)} {_(chat_id, 'disabled')}",
                parse_mode="HTML"
            )
            log_action(chat_id, user_id, f"lock_violation:{violations[0]}")
            
        except telebot.apihelper.ApiTelegramException as e:
            # Bot might not have permission to delete
            if 'admin_rights_insufficient' in str(e):
                 # Notify the creator once (Point 14)
                 notify_missing_permission(chat_id, "delete messages")
                 # Fallback: Just log and don't delete
                 logging.warning(f"Failed to delete locked content in {chat_id}: {e}")
            pass
        return
        
    # 2. XP Gain for all content types
    if add_xp(chat_id, user_id, 1):
        # XP gained
        pass


# ---------- Group Member Status Handlers (Welcome/Leave) ----------
@bot.message_handler(content_types=['new_chat_members'])
def handle_new_members(message):
    chat_id = message.chat.id
    settings = get_settings(chat_id)
    
    for user in message.new_chat_members:
        if user.is_bot:
            continue
            
        # 1. Welcome Message
        if settings.get('welcome_enabled', 1):
            name = get_user_mention(user)
            welcome_text = _(chat_id, 'welcome_message', name=name)
            
            # 2. CAPTCHA Check (simple check for now, can be extended)
            if user.id not in rejoin_tracker[chat_id]: # Simple check to avoid captcha on re-join
                # Restrict user
                restrict_new_user(chat_id, user.id)
                
                # Create captcha
                q1, q2 = create_captcha(chat_id, user.id)
                captcha_text = _(chat_id, 'captcha_verify', q1=q1, q2=q2)
                
                # Send combined message
                bot.send_message(
                    chat_id, 
                    f"{welcome_text}\n\n{captcha_text}", 
                    parse_mode="HTML"
                )
                log_action(chat_id, user.id, "welcome_captcha")
            else:
                # No captcha for assumed rejoiner
                bot.send_message(chat_id, welcome_text, parse_mode="HTML")
                unrestrict_user(chat_id, user.id) # Ensure they are unrestricted
                log_action(chat_id, user.id, "welcome_rejoin")
            
        # Add user to rejoin tracker
        rejoin_tracker[chat_id].add(user.id)
            
@bot.message_handler(content_types=['left_chat_member'])
def handle_left_members(message):
    chat_id = message.chat.id
    user = message.left_chat_member
    settings = get_settings(chat_id)
    
    if user.is_bot:
        return
        
    # 1. Goodbye Message
    if settings.get('leave_enabled', 1):
        name = get_user_mention(user)
        goodbye_text = _(chat_id, 'goodbye_message', name=name)
        bot.send_message(chat_id, goodbye_text, parse_mode="HTML")
        log_action(chat_id, user.id, "leave")
        
    # Remove from pending captcha
    if (chat_id, user.id) in pending_captcha:
        del pending_captcha[(chat_id, user.id)]
        
# ---------- Moderation Commands (Point 9, 14) ----------
# All mod commands require a reply to a message and admin status
@bot.message_handler(commands=['warn', 'mute', 'ban', 'kick', 'undo'])
def handle_moderation_commands(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    command = message.text.split()[0].replace('/', '').split('@')[0]
    
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "❌ यह कमांड सिर्फ़ ग्रुप्स में काम करता है।")
        return
        
    # 1. Admin Permission Check (Fixed Admin only - Point 9)
    if not is_admin_member(chat_id, user_id):
        bot.reply_to(message, _(chat_id, 'admin_only'))
        return
        
    # 2. Check for Reply
    if not message.reply_to_message:
        bot.reply_to(message, _(chat_id, 'usage', usage=f"/{command} का इस्तेमाल करने के लिए किसी मैसेज को reply करें।"))
        return
        
    target_user = message.reply_to_message.from_user
    target_id = target_user.id
    
    # Cannot moderate oneself
    if target_id == user_id:
        bot.reply_to(message, "❌ आप खुद को moderate नहीं कर सकते।")
        return
        
    # Cannot moderate bot or other admins (except Creator)
    if target_user.is_bot or is_admin_member(chat_id, target_id):
        if not is_creator_member(chat_id, user_id): # Only creator can touch other admins
            bot.reply_to(message, "❌ आप किसी admin या bot को moderate नहीं कर सकते।")
            return
    
    user_mention = get_user_mention(target_user)
    
    # 3. Check Bot Permissions (Point 14)
    permissions = check_bot_permissions(chat_id)

    # --- Warn ---
    if command == 'warn':
        count, action = warn_user(chat_id, target_id)
        if action == 'banned':
            # Send banned message and notify bot permission error if any
            if not permissions.get('can_restrict'):
                 notify_missing_permission(chat_id, "restrict/ban members")
                 bot.reply_to(message, _(chat_id, 'user_warned', user=user_mention, count=count)) # Warn message only
                 bot.send_message(chat_id, f"🚫 {user_mention} 3 warns के कारण ban हो गया। (Bot permission missing, may not be permanent)")
            else:
                bot.reply_to(message, _(chat_id, 'user_banned', user=user_mention))
        else:
            bot.reply_to(message, _(chat_id, 'user_warned', user=user_mention, count=count))
            
    # --- Mute ---
    elif command == 'mute':
        if not permissions.get('can_restrict'):
             bot.reply_to(message, _(chat_id, 'admin_only') + " (Bot needs 'restrict members' permission)")
             notify_missing_permission(chat_id, "restrict members")
             return
             
        # Extract duration: /mute 1h, /mute 30m etc. (default 1h)
        duration_sec = 3600
        duration_str = '1h'
        try:
            parts = message.text.split()
            if len(parts) > 1:
                match = re.match(r"(\d+)([mhd])", parts[1].lower())
                if match:
                    value, unit = match.groups()
                    value = int(value)
                    if unit == 'm':
                        duration_sec = value * 60
                        duration_str = f"{value}m"
                    elif unit == 'h':
                        duration_sec = value * 3600
                        duration_str = f"{value}h"
                    elif unit == 'd':
                        duration_sec = value * 86400
                        duration_str = f"{value}d"
        except:
            pass # Use default
            
        if mute_user(chat_id, target_id, duration_sec):
            bot.reply_to(message, _(chat_id, 'user_muted', user=user_mention, duration=duration_str))
        else:
            bot.reply_to(message, _(chat_id, 'error_occurred'))
            
    # --- Ban ---
    elif command == 'ban':
        if not permissions.get('can_restrict'):
             bot.reply_to(message, _(chat_id, 'admin_only') + " (Bot needs 'restrict members' permission)")
             notify_missing_permission(chat_id, "restrict/ban members")
             return
             
        if ban_user(chat_id, target_id):
            bot.reply_to(message, _(chat_id, 'user_banned', user=user_mention))
        else:
            bot.reply_to(message, _(chat_id, 'error_occurred'))
            
    # --- Kick ---
    elif command == 'kick':
        if not permissions.get('can_restrict'):
             bot.reply_to(message, _(chat_id, 'admin_only') + " (Bot needs 'restrict members' permission)")
             notify_missing_permission(chat_id, "restrict/ban members")
             return
             
        if kick_user(chat_id, target_id):
            bot.reply_to(message, _(chat_id, 'user_kicked', user=user_mention))
        else:
            bot.reply_to(message, _(chat_id, 'error_occurred'))
            
    # --- Undo ---
    elif command == 'undo':
        success, ptype = undo_punishment(chat_id, target_id)
        if success:
            bot.reply_to(message, f"✅ {user_mention} से आख़िरी {ptype} कार्रवाई हटा दी गई।")
        else:
            bot.reply_to(message, f"❌ {ptype}")


# ---------- Fallback Handler (For all other messages in private chat, including state handling) ----------
@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_private_messages(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Check if user is in a multi-step state
    state_key = (chat_id, user_id)
    if state_key in STATE:
        state_data = STATE[state_key]
        action = state_data['action']
        target_id = state_data['target_id']
        text = message.text
        
        # Note/Trigger/Poll/Blacklist ADD flow (Point 6, 5, 8, 7)
        if action.endswith('_wait_for_key'):
            module = action.split('_')[0] # 'note', 'trigger', 'blacklist', 'poll'
            
            # Note/Trigger/Blacklist: Expecting key/word
            if module in ['note', 'trigger', 'blacklist']:
                
                parts = text.split(maxsplit=1)
                
                if len(parts) < 1 and module != 'blacklist':
                    bot.send_message(chat_id, _(target_id, 'invalid_input'))
                    return
                
                key = parts[0]
                content = parts[1] if len(parts) > 1 else ""
                
                if module == 'blacklist':
                    word = text.lower().strip()
                    if not word:
                         bot.send_message(chat_id, _(target_id, 'invalid_input'))
                         return
                    
                    # Store blacklist word directly (simple implementation)
                    conn = db()
                    c = conn.cursor()
                    c.execute("INSERT INTO blacklist (chat_id, word) VALUES (?,?)", (target_id, word))
                    conn.commit()
                    conn.close()
                    
                    bot.send_message(chat_id, _(target_id, 'note_added', key=word)) # Reusing note_added for confirmation
                    log_action(target_id, user_id, f"blacklist_add:{word}")
                    
                else: # note or trigger
                    # Save key and ask for content
                    STATE[state_key] = {'action': f'{module}_wait_for_content', 'target_id': target_id, 'key': key, 'content': content}
                    
                    if module == 'note':
                        # Note: content is already given in same line
                        conn = db()
                        c = conn.cursor()
                        c.execute("INSERT INTO notes (chat_id, key, content, created_at) VALUES (?,?,?,?)", (target_id, key, content, now_ts()))
                        conn.commit()
                        conn.close()
                        
                        bot.send_message(chat_id, _(target_id, 'note_added', key=key))
                        log_action(target_id, user_id, f"note_add:{key}")
                        
                    elif module == 'trigger':
                         # Trigger: content is reply
                        conn = db()
                        c = conn.cursor()
                        c.execute("INSERT INTO triggers (chat_id, pattern, reply, is_regex) VALUES (?,?,?,?)", (target_id, key, content, 0)) # Default to non-regex
                        conn.commit()
                        conn.close()
                        
                        bot.send_message(chat_id, _(target_id, 'trigger_added'))
                        log_action(target_id, user_id, f"trigger_add:{key}")
                        
                # Clear state after completion
                del STATE[state_key] 
                
            elif module == 'poll':
                # Poll creation: Question + options, one per line
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                question = lines[0]
                options = lines[1:]
                
                if not question or len(options) < 2 or len(options) > 10:
                    bot.send_message(chat_id, "❌ Poll के लिए कम से कम 2 और अधिकतम 10 विकल्प चाहिए।")
                    return
                    
                # Store poll details (Point 7 - initial creation)
                conn = db()
                c = conn.cursor()
                c.execute("INSERT INTO polls (chat_id, question, options_json, multiple, open, created_at) VALUES (?,?,?,?,?,?)", 
                          (target_id, question, jdump(options), 0, 1, now_ts()))
                poll_id = c.lastrowid
                conn.commit()
                conn.close()
                
                # Send the poll to the group (Telegram's native poll functionality is better, but this uses custom DB for consistency)
                # Since the prompt asks for polls menu/list, we assume it's custom.
                bot.send_message(
                    target_id, 
                    f"📊 <b>New Poll:</b> {safe_html(question)}",
                    reply_markup=_build_custom_poll_keyboard(poll_id, target_id, options)
                )
                
                bot.send_message(chat_id, _(target_id, 'poll_created'))
                log_action(target_id, user_id, f"poll_create:{question}")
                del STATE[state_key]
                
        
        # Fallback for unknown state (should not happen)
        else:
            bot.send_message(chat_id, f"{_(chat_id, 'invalid_input')}\n{_(chat_id, 'cancel')} कमांड चलाकर इसे रद्द करें।")
            
    # Default message if not in state
    else:
        bot.send_message(chat_id, _(chat_id, 'start_private'))


# --- Placeholder for custom poll keyboard builder (Point 7) ---
def _build_custom_poll_keyboard(poll_id, chat_id, options):
    """Builds an inline keyboard for a custom poll."""
    keyboard = types.InlineKeyboardMarkup()
    chat_id_str = str(chat_id)
    
    # For simplicity, we just add the vote options
    for i, option in enumerate(options):
        # Callback format: poll:vote:poll_id:option_index
        keyboard.add(types.InlineKeyboardButton(f"🗳️ {safe_html(option)}", callback_data=f"poll:vote:{poll_id}:{i}"))

    # Add refresh/close buttons
    keyboard.add(
        types.InlineKeyboardButton(_(chat_id_str, 'active_polls'), callback_data=f"poll:{chat_id_str}:active"),
        types.InlineKeyboardButton("❌ Close Poll", callback_data=f"poll:close:{poll_id}")
    )
    return keyboard

# ... continue in next part ...
# ----------------------------------------------------------------------
# -------------------- Telegram Message Handlers (Continued from Part 2) ----------------
# ----------------------------------------------------------------------

# --- Placeholder for custom poll keyboard builder (Point 7) ---
def _build_custom_poll_keyboard(poll_id, target_id, options_data):
    """Builds an inline keyboard for a custom poll with updated counts."""
    keyboard = types.InlineKeyboardMarkup()
    chat_id_str = str(target_id)
    
    # options_data is a list of {"text": str, "voters": list}
    total_votes = sum(len(opt['voters']) for opt in options_data)
    
    for i, option in enumerate(options_data):
        count = len(option['voters'])
        percentage = (count / total_votes * 100) if total_votes > 0 else 0
        
        # Display: [Option Text] [Count] [Percentage]
        button_text = f"🗳️ {safe_html(option['text'])} ({count}) [{percentage:.0f}%]"
        
        # Callback format: poll:vote:poll_id:option_index
        keyboard.add(types.InlineKeyboardButton(button_text, callback_data=f"poll:vote:{poll_id}:{i}"))

    # Add refresh/close buttons
    keyboard.add(
        types.InlineKeyboardButton("🔄 Refresh / My Vote", callback_data=f"poll:vote:{poll_id}:-1"),
        types.InlineKeyboardButton("❌ Close Poll", callback_data=f"poll:close:{poll_id}")
    )
    return keyboard

# --- Helper function to get/update poll data ---
def get_poll_data(poll_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT * FROM polls WHERE id=?", (poll_id,))
    row = c.fetchone()
    conn.close()
    if row:
        data = dict(row)
        # Ensure options_json is correctly structured for voting: [{"text": str, "voters": list}]
        try:
            options_data = jload(data['options_json'])
            if options_data and isinstance(options_data[0], str):
                # Initialize for first time voting
                data['options_json'] = jdump([{'text': opt, 'voters': []} for opt in options_data])
            elif options_data and 'voters' not in options_data[0]:
                # Update old structure
                data['options_json'] = jdump([{'text': opt['text'], 'voters': []} for opt in options_data])
            elif not options_data:
                 return None
            return data
        except Exception as e:
            logging.error(f"Error loading poll options_json: {e}")
            return None
    return None

def update_poll_options(poll_id, options_data):
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE polls SET options_json=? WHERE id=?", (jdump(options_data), poll_id))
    conn.commit()
    conn.close()
    
# --- Extend callback_inline for Poll Voting/Closing (Point 7) ---
# NOTE: To fit within the continuous code structure, this function assumes the main 
# callback_inline handler in Part 2 is modified to delegate poll actions here.
@bot.callback_query_handler(func=lambda call: call.data.startswith('poll:vote:') or call.data.startswith('poll:close:'))
def handle_poll_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id
    data = call.data
    parts = data.split(':')
    action = parts[1] # 'vote' or 'close'
    poll_id = int(parts[2])
    
    # 1. Close Poll
    if action == 'close':
        if not is_admin_member(chat_id, user_id):
            bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
            return

        conn = db()
        c = conn.cursor()
        c.execute("UPDATE polls SET open=0 WHERE id=?", (poll_id,))
        conn.commit()
        conn.close()
        
        # Re-fetch poll to show final results
        poll_row = get_poll_data(poll_id)
        if poll_row:
            final_text = f"📊 <b>POLL CLOSED:</b> {safe_html(poll_row['question'])}\n\n"
            options_data = jload(poll_row['options_json'])
            total_votes = sum(len(opt['voters']) for opt in options_data)
            
            for opt in options_data:
                count = len(opt['voters'])
                percentage = (count / total_votes * 100) if total_votes > 0 else 0
                final_text += f"🗳️ {safe_html(opt['text'])}: {count} votes ({percentage:.0f}%)\n"
            
            # Remove inline keyboard
            bot.edit_message_text(final_text, chat_id, message_id, reply_markup=None, parse_mode="HTML")
            bot.answer_callback_query(call.id, "✅ Poll closed.")
        else:
            bot.answer_callback_query(call.id, "⚠️ Poll not found.")
        return

    # 2. Vote
    elif action == 'vote':
        vote_index = int(parts[3])
        poll_row = get_poll_data(poll_id)
        
        if not poll_row or not poll_row['open']:
            bot.answer_callback_query(call.id, "❌ This poll is closed.", show_alert=True)
            return
            
        options_data = jload(poll_row['options_json'])
        
        already_voted_index = -1
        for i, opt in enumerate(options_data):
            if str(user_id) in opt['voters']:
                already_voted_index = i
                break
                
        # Handle Refresh / My Vote click (vote_index == -1)
        if vote_index == -1:
            if already_voted_index != -1:
                opt_text = options_data[already_voted_index]['text']
                bot.answer_callback_query(call.id, f"✅ You have voted for: {safe_html(opt_text)}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "🗳️ You have not voted yet.")
                new_keyboard = _build_custom_poll_keyboard(poll_id, chat_id, options_data)
                bot.edit_message_reply_markup(chat_id, message_id, reply_markup=new_keyboard)
                
        
        # Process the actual vote
        elif 0 <= vote_index < len(options_data):
            if already_voted_index == vote_index:
                bot.answer_callback_query(call.id, "✅ Your vote is already counted.")
                return
            else:
                # Remove vote from old option (assuming single choice)
                if already_voted_index != -1:
                     options_data[already_voted_index]['voters'].remove(str(user_id))
                     
                # Add vote to new option
                options_data[vote_index]['voters'].append(str(user_id))
                
                # Update DB and refresh keyboard
                update_poll_options(poll_id, options_data)
                
                # Re-render the message with new counts
                new_keyboard = _build_custom_poll_keyboard(poll_id, chat_id, options_data)
                bot.edit_message_reply_markup(chat_id, message_id, reply_markup=new_keyboard)
                
                bot.answer_callback_query(call.id, "✅ Vote counted.")
        else:
            bot.answer_callback_query(call.id, _(chat_id, 'error_occurred'))

# --- Helper function to render a list and allow deletion (for Note/Trigger/Blacklist) ---
def _build_list_menu(chat_id, user_id, module, target_id):
    chat_id_str = str(chat_id)
    keyboard = types.InlineKeyboardMarkup()
    desc_lines = [f"📋 <b>{_(chat_id_str, module.capitalize())} List</b> (Click 🗑️ to Delete)"]
    
    conn = db()
    c = conn.cursor()
    
    if module == 'note':
        c.execute("SELECT id, key, content FROM notes WHERE chat_id=?", (target_id,))
    elif module == 'trigger':
        c.execute("SELECT id, pattern as key, reply FROM triggers WHERE chat_id=?", (target_id,))
    elif module == 'blacklist':
        c.execute("SELECT id, word as key, word as content FROM blacklist WHERE chat_id=?", (target_id,))
    else:
        conn.close()
        return "\n".join(desc_lines), keyboard

    rows = c.fetchall()
    conn.close()
    
    if not rows:
        desc_lines.append(f"<i>No active {module}s found.</i>")
    
    for row in rows:
        key = row['key']
        item_id = row['id']
        
        # Display text: [Key] (Optional reply snippet)
        content_snippet = row.get('content', row.get('reply', ''))
        display_text = safe_html(key)
        if content_snippet:
             display_text += f" -> {safe_html(content_snippet[:20])}..."
             
        # Button: [Key/Pattern] [Delete]
        keyboard.add(
            types.InlineKeyboardButton(display_text, callback_data="ignore_label"),
            # Callback format: module:target_id:del:item_id
            types.InlineKeyboardButton("🗑️", callback_data=f"{module}:{target_id}:del:{item_id}")
        )
        
    # Back button to the main menu of the module
    keyboard.add(types.InlineKeyboardButton(_(chat_id_str, 'back'), callback_data=f"menu:{target_id}:{module}"))
    
    return "\n".join(desc_lines), keyboard

# --- Extend callback_inline for listing and deletion (Point 3, 5, 6, 8) ---
# NOTE: This dedicated handler assumes the main callback_inline function (in Part 2) 
# routes all 'list' and 'del' actions here.
@bot.callback_query_handler(func=lambda call: call.data.endswith(':list') or call.data.endswith(':active') or 'del' in call.data.split(':'))
def handle_list_delete_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    message_id = call.message.message_id
    data = call.data
    parts = data.split(':')
    
    module = parts[0]
    action = parts[2] if len(parts) > 2 else parts[1] # Check for delete action
    target_id = parts[1]
    
    # 1. Permission Check
    if not str(chat_id).startswith('-') and target_id.startswith('-'):
        is_allowed = is_creator_member(target_id, user_id)
    else:
        is_allowed = is_admin_member(chat_id, user_id)
        
    if not is_allowed:
        bot.answer_callback_query(call.id, _(target_id, 'admin_only'), show_alert=True)
        return
    
    # 2. Listing Menu (list/active)
    if action == 'list' or action == 'active':
        
        desc, kb = _build_list_menu(chat_id, user_id, module, target_id)
        
        try:
             bot.edit_message_text(
                desc,
                chat_id,
                message_id,
                reply_markup=kb,
                parse_mode="HTML"
            )
             bot.answer_callback_query(call.id)
        except Exception as e:
            if 'message is not modified' in str(e):
                bot.answer_callback_query(call.id, f"✅ {module.capitalize()} list up-to-date.")
            else:
                 bot.answer_callback_query(call.id, _(target_id, 'error_occurred'), show_alert=True)
        return
        
    # 3. Deletion (Format: module:target_id:del:item_id)
    elif action == 'del':
        item_id = int(parts[3])
        
        conn = db()
        c = conn.cursor()
        deleted_key = ""
        
        if module == 'note':
            c.execute("SELECT key FROM notes WHERE id=? AND chat_id=?", (item_id, target_id))
            row = c.fetchone()
            if row:
                deleted_key = row['key']
                c.execute("DELETE FROM notes WHERE id=? AND chat_id=?", (item_id, target_id))
                
        elif module == 'trigger':
            c.execute("SELECT pattern FROM triggers WHERE id=? AND chat_id=?", (item_id, target_id))
            row = c.fetchone()
            if row:
                deleted_key = row['pattern']
                c.execute("DELETE FROM triggers WHERE id=? AND chat_id=?", (item_id, target_id))
                
        elif module == 'blacklist':
            c.execute("SELECT word FROM blacklist WHERE id=? AND chat_id=?", (item_id, target_id))
            row = c.fetchone()
            if row:
                deleted_key = row['word']
                c.execute("DELETE FROM blacklist WHERE id=? AND chat_id=?", (item_id, target_id))

        conn.commit()
        conn.close()
        
        if deleted_key:
            log_action(target_id, user_id, f"{module}_delete:{deleted_key}")
            # Reusing 'note_deleted' for generic deletion confirmation
            bot.answer_callback_query(call.id, _(target_id, 'note_deleted', key=deleted_key)) 
            
            # Re-render the list menu instantly
            desc, kb = _build_list_menu(chat_id, user_id, module, target_id)
            bot.edit_message_text(desc, chat_id, message_id, reply_markup=kb, parse_mode="HTML")
        else:
            bot.answer_callback_query(call.id, "⚠️ Item not found or already deleted.", show_alert=True)
        return


# ----------------------------------------------------------------------
# -------------------- BOT STARTUP & MAIN LOOP (Point 18, 20) ----------
# ----------------------------------------------------------------------

# --- Auto Cleanup Thread ---
def auto_cleanup_thread():
    """Periodically cleans up expired captcha attempts."""
    while True:
        try:
            now = now_ts()
            
            # 1. Cleanup expired captcha (5 mins expiry)
            with CAPTCHA_LOCK:
                # Remove restriction for users who timed out on captcha
                expired_keys = [key for key, data in pending_captcha.items() if (now - data['created_at']) > 300] 
                for chat_id, user_id in expired_keys:
                    unrestrict_user(chat_id, user_id)
                    logging.info(f"Captcha expired/timed out for {user_id} in {chat_id}")
                    del pending_captcha[(chat_id, user_id)]
            
        except Exception as e:
            logging.error(f"Auto-cleanup error: {e}")
            
        # Wait for 30 seconds before next check
        time.sleep(30)


def main():
    "Main function to start the bot"
    global BOT_USERNAME
    logging.info("🤖 Bot starting...")
    logging.info(f"📊 Database: {DB_PATH}")
    
    # 1. Initialize Database
    init_db() 
    
    # 2. Fetch Bot Info
    try:
        bot_info = bot.get_me()
        BOT_USERNAME = bot_info.username
        logging.info(f"✅ Bot username: @{BOT_USERNAME}")
        
    except Exception as e:
        logging.error(f"❌ Failed to fetch bot info: {e}")
        sys.exit(1)
        
    # 3. Start Auto Cleanup Thread 
    thread = Thread(target=auto_cleanup_thread)
    thread.daemon = True
    thread.start()
    logging.info("✅ Auto cleanup thread started.")
        
    logging.info("✅ All systems ready")
    logging.info("🚀 Starting infinite polling...")
    
    # 4. Start Polling
    try:
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
    main()

# ----------------------------------------------------------------------
# -------------------- END OF bot.py CODE ------------------------------
# ----------------------------------------------------------------------

