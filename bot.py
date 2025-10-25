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
    # ---------- UI / Menu Builders & Callback Handling (Part 2) ----------
# Implements build_toggle_row, send_menu, callback_inline and related helpers.

# ---------- Inline Button / Keyboard Helpers ----------
def btn(text, callback_data=None, url=None):
    "Create InlineKeyboardButton"
    if url:
        return types.InlineKeyboardButton(text=text, url=url)
    return types.InlineKeyboardButton(text=text, callback_data=callback_data)

def row(*buttons):
    kb = types.InlineKeyboardMarkup(row_width=len(buttons))
    kb.add(*buttons)
    return kb

def build_toggle_row(chat_id, key, value, desc_key=None):
    """
    Build a row for a boolean setting.
    Rules:
    - State-first button (Enabled/Disabled)
    - Description line above buttons when inserted into message text (handled by send_menu)
    - Uses localization via _()
    - Returns InlineKeyboardMarkup row (single-row)
    """
    state_text = _(chat_id, 'enabled') if value else _(chat_id, 'disabled')
    # callback: toggle:<key>
    state_btn = types.InlineKeyboardButton(text=state_text, callback_data=f"toggle:{key}")
    # second button is an action e.g., 'Edit' or 'Options' - default to a toggle detail
    opt_btn = types.InlineKeyboardButton(text="⚙️", callback_data=f"toggle:options:{key}")
    return [state_btn, opt_btn]

# ---------- Menu Sender ----------
def send_menu(chat_id, user_id=None, private=False):
    """
    Send main menu or settings menu for a chat.
    If private=True, send a private-view tailored to group (used when group creator opens settings privately).
    """
    ensure_settings(chat_id)
    menu = menu_get(chat_id)
    locks = locks_get(chat_id)
    notes_count = count_notes(chat_id)
    triggers_count = count_triggers(chat_id)
    polls_count = count_polls(chat_id)
    blacklist_count = count_blacklist(chat_id)
    xp_meta = menu.get('xp_settings', {"xp_enabled": True, "xp_cooldown": 10})

    title = _(chat_id, 'main_menu')
    desc = _(chat_id, 'main_menu_desc')

    # Build description text with dynamic counts
    text_lines = [f"<b>{safe_html(title)}</b>", "", safe_html(desc), ""]
    # Row: Settings
    text_lines.append(f"⚙️ <b>{_(chat_id, 'settings')}</b>\n{_(chat_id, 'settings_desc')}")
    # Locks
    text_lines.append(f"\n🔐 <b>{_(chat_id, 'locks')}</b>\n{_(chat_id, 'locks_desc')}")
    # Notes
    text_lines.append(f"\n📝 <b>{_(chat_id, 'notes')}</b>\n{_(chat_id, 'notes_desc', count=notes_count)}")
    # Triggers
    text_lines.append(f"\n🤖 <b>{_(chat_id, 'triggers')}</b>\n{_(chat_id, 'triggers_desc', count=triggers_count)}")
    # XP
    text_lines.append(f"\n🎯 <b>{_(chat_id, 'xp_system')}</b>\n{_(chat_id, 'xp_desc')}")
    # Polls
    text_lines.append(f"\n📊 <b>{_(chat_id, 'polls')}</b>\n{_(chat_id, 'polls_desc', count=polls_count)}")
    # Blacklist
    text_lines.append(f"\n🚫 <b>{_(chat_id, 'blacklist')}</b>\n{_(chat_id, 'blacklist_desc', count=blacklist_count)}")

    full_text = "\n".join(text_lines)

    # Build inline keyboard rows
    kb = types.InlineKeyboardMarkup(row_width=2)

    # First row: Settings | Moderation
    kb.add(
        btn(f"{_(chat_id,'settings')}", callback_data=f"menu:settings"),
        btn(f"{_(chat_id,'moderation')}", callback_data=f"menu:moderation")
    )

    # Second row: Locks | Notes
    kb.add(
        btn(f"{_(chat_id,'locks')}", callback_data=f"menu:locks"),
        btn(f"{_(chat_id,'notes')} ({notes_count})", callback_data=f"menu:notes")
    )

    # Third row: Triggers | XP Settings
    kb.add(
        btn(f"{_(chat_id,'triggers')} ({triggers_count})", callback_data=f"menu:triggers"),
        btn(f"{_(chat_id,'xp_settings')}", callback_data=f"menu:xp_settings")
    )

    # Fourth row: Polls | Blacklist
    kb.add(
        btn(f"{_(chat_id,'polls')} ({polls_count})", callback_data=f"menu:polls"),
        btn(f"{_(chat_id,'blacklist')} ({blacklist_count})", callback_data=f"menu:blacklist")
    )

    # Language and Back/Close row
    kb.add(
        btn(f"{_(chat_id,'language')}", callback_data=f"lang:toggle"),
        btn(f"{_(chat_id,'back')}", callback_data=f"menu:back")
    )

    # Private open hint row (only for group messages shown in group): show 'Open in private chat' for group creator or admins
    if not private:
        # Provide a 'Open in private' button that opens a private chat with a deep-link
        open_text = _(chat_id, 'menu_in_private_button')
        url = f"https://t.me/{BOT_USERNAME}?start=manage_{chat_id}"
        kb.add(btn(open_text, url=url))

    # Send or edit message
    try:
        if private and user_id:
            bot.send_message(user_id, _(chat_id, 'menu_in_private_opened', title=get_chat_title(chat_id), desc=_(chat_id, 'settings_desc')), reply_markup=kb)
        else:
            bot.send_message(chat_id, full_text, reply_markup=kb)
    except Exception as e:
        logging.exception("send_menu failed")
        # fallback minimal
        try:
            bot.send_message(chat_id, _(chat_id, 'error_occurred'))
        except:
            pass

# ---------- Quick Chat Metadata Helpers ----------
def get_chat_title(chat_id):
    try:
        info = bot.get_chat(chat_id)
        return info.title or str(chat_id)
    except:
        return str(chat_id)

# ---------- Count Helpers ----------
def count_notes(chat_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM notes WHERE chat_id=?", (str(chat_id),))
    r = c.fetchone()[0]
    conn.close()
    return r

def count_triggers(chat_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM triggers WHERE chat_id=?", (str(chat_id),))
    r = c.fetchone()[0]
    conn.close()
    return r

def count_polls(chat_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM polls WHERE chat_id=? AND open=1", (str(chat_id),))
    r = c.fetchone()[0]
    conn.close()
    return r

def count_blacklist(chat_id):
    conn = db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM blacklist WHERE chat_id=?", (str(chat_id),))
    r = c.fetchone()[0]
    conn.close()
    return r

# ---------- Simple Permission Checks ----------
def is_user_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

def is_creator_or_admin(bot_obj, chat_id, user_id):
    return is_user_admin(chat_id, user_id)

def bot_is_admin(chat_id):
    try:
        me = bot.get_me()
        m = bot.get_chat_member(chat_id, me.id)
        return m.status in ['administrator', 'creator']
    except:
        return False

# ---------- /start Command Handler ----------
@bot.message_handler(commands=['start'])
def handle_start(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    # If started in private with payload like manage_<chat_id> -> open private settings for that group
    parts = (message.text or "").split()
    payload = parts[1] if len(parts) > 1 else ""
    if message.chat.type == 'private':
        # If payload present and matches manage_ we open private group settings page
        if payload.startswith("manage_"):
            target = payload.split("_",1)[1]
            # Only allow group creators/admins to open group's private view. Verify if user is admin in that group.
            try:
                if is_user_admin(target, user_id):
                    send_menu(target, user_id=user_id, private=True)
                    return
                else:
                    bot.reply_to(message, _(chat_id, 'admin_only'))
                    return
            except Exception:
                logging.exception("start.manage failed")
        # Regular private start: show welcome text (no "go to private" button)
        bot.send_message(chat_id, _(chat_id, 'start_private'))
        return
    else:
        # Group start: show group-specific setup and "Open in private chat" button when appropriate
        if not bot_is_admin(chat_id):
            # Bot is not admin - encourage to promote
            kb = types.InlineKeyboardMarkup()
            kb.add(btn(_(chat_id, 'menu_in_private_button'), url=f"https://t.me/{BOT_USERNAME}?start=manage_{chat_id}"))
            bot.send_message(chat_id, _(chat_id, 'start_group_not_admin'), reply_markup=kb)
            return
        # If group creator used /start in group, show button to open private config
        kb = types.InlineKeyboardMarkup()
        kb.add(btn(_(chat_id, 'menu_in_private_button'), url=f"https://t.me/{BOT_USERNAME}?start=manage_{chat_id}"))
        bot.send_message(chat_id, _(chat_id, 'main_menu'), reply_markup=kb)
        return

# ---------- Callback Query Handler ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    """
    Central callback handler. Parses callback_data and routes to specific functions.
    Supported patterns:
     - menu:<name>
     - toggle:<key>
     - toggle:options:<key>
     - lang:toggle
     - trigger:add|del|edit|enable|disable:...
     - note:add|list|del
     - poll:..., blacklist:add|del, xp:settings, etc.
    """
    data = call.data or ""
    chat_id = call.message.chat.id if call.message else None
    user_id = call.from_user.id
    logging.info(f"callback from {user_id} data={data}")

    # Helper to answer callback quickly
    def ack(text=None, show_alert=False):
        try:
            bot.answer_callback_query(call.id, text or "", show_alert=show_alert)
        except:
            pass

    # Menu navigation
    if data.startswith("menu:"):
        cmd = data.split(":",1)[1]
        if cmd == "settings":
            show_settings_menu(call)
            ack()
            return
        if cmd == "moderation":
            show_moderation_menu(call)
            ack()
            return
        if cmd == "locks":
            show_locks_menu(call)
            ack()
            return
        if cmd == "notes":
            show_notes_menu(call)
            ack()
            return
        if cmd == "triggers":
            show_triggers_menu(call)
            ack()
            return
        if cmd == "xp_settings":
            show_xp_settings_menu(call)
            ack()
            return
        if cmd == "polls":
            show_polls_menu(call)
            ack()
            return
        if cmd == "blacklist":
            show_blacklist_menu(call)
            ack()
            return
        if cmd == "back":
            # go to main menu
            send_menu(chat_id)
            ack()
            return

    # Language toggle
    if data == "lang:toggle":
        # toggle between hi and en
        row = get_settings(chat_id)
        cur = row.get('lang', 'hi')
        new = 'en' if cur == 'hi' else 'hi'
        set_setting(chat_id, 'lang', new)
        logging.info(f"Language changed for {chat_id} -> {new} by {user_id}")
        # update the message instantly
        try:
            bot.edit_message_text(_(chat_id, 'main_menu'), chat_id, call.message.message_id, reply_markup=None, parse_mode="HTML")
        except Exception:
            pass
        ack(_(chat_id, 'lang_changed'))
        return

    # Toggle boolean keys
    if data.startswith("toggle:"):
        parts = data.split(":")
        # toggle:key OR toggle:options:key
        if len(parts) == 2:
            key = parts[1]
            # fetch menu_json and toggle key
            menu = menu_get(chat_id)
            cur = menu.get(key, False)
            menu[key] = not cur
            menu_set(chat_id, menu)
            logging.info(f"Toggled {key} in {chat_id} -> {menu[key]} by {user_id}")
            ack(_(chat_id, 'setting_updated'))
            # refresh the relevant menu: stay on same menu
            send_menu(chat_id)
            return
        elif len(parts) == 3 and parts[1] == 'options':
            key = parts[2]
            # show options for the toggle key
            show_toggle_options(call, key)
            ack()
            return

    # Notes: add/list/delete
    if data.startswith("note:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ''
        if action == 'list':
            list_notes(call)
            ack()
            return
        if action == 'add':
            # begin conversation: ask user to send "key|content"
            bot.send_message(call.from_user.id, _(chat_id, 'add_note') + "\nFormat: key | content")
            STATE[(call.from_user.id, 'adding_note')] = {'chat_id': chat_id}
            ack()
            return
        if action == 'del':
            # delete specific note provided as third part
            key = parts[2] if len(parts) > 2 else None
            if not key:
                ack(_(chat_id, 'invalid_input'), True)
                return
            conn = db()
            c = conn.cursor()
            c.execute("DELETE FROM notes WHERE chat_id=? AND key=?", (str(chat_id), key))
            conn.commit()
            conn.close()
            ack(_(chat_id, 'note_deleted', key=key))
            send_menu(chat_id)
            return

    # Triggers: add/list/delete/enable/disable
    if data.startswith("trigger:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ''
        if action == 'list':
            list_triggers(call)
            ack()
            return
        if action == 'add':
            bot.send_message(call.from_user.id, _(chat_id, 'add_trigger') + "\nFormat: pattern | reply")
            STATE[(call.from_user.id, 'adding_trigger')] = {'chat_id': chat_id}
            ack()
            return
        if action in ['del','enable','disable']:
            # expected: trigger:del:<id> or trigger:enable:<id>
            if len(parts) < 3:
                ack(_(chat_id, 'invalid_input'), True)
                return
            trig_id = parts[2]
            try:
                conn = db()
                c = conn.cursor()
                if action == 'del':
                    c.execute("DELETE FROM triggers WHERE id=? AND chat_id=?", (int(trig_id), str(chat_id)))
                else:
                    # Use triggers_meta in menu_json for enabled/disabled
                    menu = menu_get(chat_id)
                    meta = menu.get('triggers_meta', {})
                    ent = meta.get(str(trig_id), {})
                    ent['enabled'] = (action == 'enable')
                    meta[str(trig_id)] = ent
                    menu['triggers_meta'] = meta
                    menu_set(chat_id, menu)
                conn.commit()
                conn.close()
                ack(_(chat_id, 'setting_updated'))
                send_menu(chat_id)
            except Exception:
                logging.exception("trigger action failed")
                ack(_(chat_id, 'error_occurred'))
            return

    # XP settings: open or modify
    if data.startswith("xp:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ''
        menu = menu_get(chat_id)
        xp_meta = menu.get('xp_settings', {"xp_enabled": True, "xp_cooldown": 10})
        if action == 'settings':
            show_xp_settings_menu(call)
            ack()
            return
        if action == 'toggle':
            xp_meta['xp_enabled'] = not xp_meta.get('xp_enabled', True)
            menu['xp_settings'] = xp_meta
            menu_set(chat_id, menu)
            ack(_(chat_id, 'setting_updated'))
            show_xp_settings_menu(call)
            return
        if action == 'cooldown_increase':
            xp_meta['xp_cooldown'] = min(3600, xp_meta.get('xp_cooldown',10) + 5)
            menu['xp_settings'] = xp_meta
            menu_set(chat_id, menu)
            ack(_(chat_id, 'setting_updated'))
            show_xp_settings_menu(call)
            return
        if action == 'cooldown_decrease':
            xp_meta['xp_cooldown'] = max(1, xp_meta.get('xp_cooldown',10) - 5)
            menu['xp_settings'] = xp_meta
            menu_set(chat_id, menu)
            ack(_(chat_id, 'setting_updated'))
            show_xp_settings_menu(call)
            return

    # Blacklist add/delete
    if data.startswith("blacklist:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ''
        if action == 'add':
            bot.send_message(call.from_user.id, _(chat_id, 'add_word') + "\nSend the word to blacklist")
            STATE[(call.from_user.id, 'adding_blacklist')] = {'chat_id': chat_id}
            ack()
            return
        if action == 'list':
            list_blacklist(call)
            ack()
            return
        if action == 'del':
            word = parts[2] if len(parts) > 2 else None
            if not word:
                ack(_(chat_id, 'invalid_input'), True)
                return
            conn = db()
            c = conn.cursor()
            c.execute("DELETE FROM blacklist WHERE chat_id=? AND word=?", (str(chat_id), word))
            conn.commit()
            conn.close()
            ack(_(chat_id, 'setting_updated'))
            send_menu(chat_id)
            return

    # Poll actions (simple open/close)
    if data.startswith("poll:"):
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ''
        if action == 'create':
            bot.send_message(call.from_user.id, _(chat_id, 'create_poll') + "\nFormat: question | option1;option2;option3")
            STATE[(call.from_user.id, 'creating_poll')] = {'chat_id': chat_id}
            ack()
            return
        if action == 'list':
            list_polls(call)
            ack()
            return
        if action in ['close','open']:
            poll_id = parts[2] if len(parts) > 2 else None
            if not poll_id:
                ack(_(chat_id, 'invalid_input'))
                return
            conn = db()
            c = conn.cursor()
            if action == 'close':
                c.execute("UPDATE polls SET open=0 WHERE id=? AND chat_id=?", (int(poll_id), str(chat_id)))
            else:
                c.execute("UPDATE polls SET open=1 WHERE id=? AND chat_id=?", (int(poll_id), str(chat_id)))
            conn.commit()
            conn.close()
            ack(_(chat_id, 'setting_updated'))
            send_menu(chat_id)
            return

    # Fallback: unknown action
    logging.warning(f"Unknown callback action: {data}")
    try:
        bot.answer_callback_query(call.id, _(chat_id, 'unknown_action'), show_alert=True)
    except:
        pass

# ---------- Menu Sub-views Implementations ----------
def show_settings_menu(call):
    chat_id = call.message.chat.id
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        btn(f"{_(chat_id,'locks')}", callback_data=f"menu:locks"),
        btn(f"{_(chat_id,'commands')}", callback_data=f"menu:commands")
    )
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'settings')}</b>\n{_(chat_id,'settings_desc')}", chat_id, call.message.message_id, reply_markup=kb)

def show_moderation_menu(call):
    chat_id = call.message.chat.id
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        btn("⚠️ Warn", callback_data=f"mod:warn"),
        btn("🔇 Mute", callback_data=f"mod:mute")
    )
    kb.add(
        btn("🚫 Ban", callback_data=f"mod:ban"),
        btn("👢 Kick", callback_data=f"mod:kick")
    )
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'moderation')}</b>\n{_(chat_id,'moderation_desc')}", chat_id, call.message.message_id, reply_markup=kb)

def show_locks_menu(call):
    chat_id = call.message.chat.id
    locks = locks_get(chat_id)
    # default locks
    def lock_val(k): return locks.get(k, False)
    kb = types.InlineKeyboardMarkup(row_width=2)
    # build rows using build_toggle_row
    for key_label, key in [(_('lock_urls','lock_urls'), 'lock_urls'), ('🖼️ Photos','lock_photos'), ('🎥 Videos','lock_videos'), ('👾 Stickers','lock_stickers')]:
        # Using consistent callbacks
        state = lock_val(key)
        state_text = _(chat_id, 'enabled') if state else _(chat_id, 'disabled')
        kb.add(btn(f"{state_text} {key_label}", callback_data=f"lock:toggle:{key}"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'locks')}</b>\n{_(chat_id,'locks_desc')}", chat_id, call.message.message_id, reply_markup=kb)

def show_notes_menu(call):
    chat_id = call.message.chat.id
    notes_count = count_notes(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(btn(_(chat_id,'add_note'), callback_data="note:add"), btn(_(chat_id,'list_notes', count=notes_count), callback_data="note:list"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'notes')}</b>\n{_(chat_id,'notes_desc', count=notes_count)}", chat_id, call.message.message_id, reply_markup=kb)

def show_triggers_menu(call):
    chat_id = call.message.chat.id
    triggers_count = count_triggers(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(btn(_(chat_id,'add_trigger'), callback_data="trigger:add"), btn(f"📋 List ({triggers_count})", callback_data="trigger:list"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'triggers')}</b>\n{_(chat_id,'triggers_desc', count=triggers_count)}", chat_id, call.message.message_id, reply_markup=kb)

def show_xp_settings_menu(call):
    chat_id = call.message.chat.id
    menu = menu_get(chat_id)
    xp_meta = menu.get('xp_settings', {"xp_enabled": True, "xp_cooldown": 10})
    kb = types.InlineKeyboardMarkup(row_width=3)
    # State-first button
    state_text = _(chat_id, 'enabled') if xp_meta.get('xp_enabled', True) else _(chat_id, 'disabled')
    kb.add(btn(f"{state_text} {_(chat_id,'xp_enabled')}", callback_data="xp:toggle"))
    # cooldown controls
    kb.add(
        btn("➖", callback_data="xp:cooldown_decrease"),
        btn(f"{_(chat_id,'xp_cooldown')}: {xp_meta.get('xp_cooldown',10)}s", callback_data="xp:settings"),
        btn("➕", callback_data="xp:cooldown_increase")
    )
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'xp_settings')}</b>\n{_(chat_id,'xp_settings_desc')}", chat_id, call.message.message_id, reply_markup=kb)

def show_polls_menu(call):
    chat_id = call.message.chat.id
    polls_count = count_polls(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(btn(_(chat_id,'create_poll'), callback_data="poll:create"), btn(_(chat_id,'active_polls', count=polls_count), callback_data="poll:list"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'polls')}</b>\n{_(chat_id,'polls_desc', count=polls_count)}", chat_id, call.message.message_id, reply_markup=kb)

def show_blacklist_menu(call):
    chat_id = call.message.chat.id
    bl_count = count_blacklist(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(btn(_(chat_id,'add_word'), callback_data="blacklist:add"), btn(f"📋 List ({bl_count})", callback_data="blacklist:list"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text(f"<b>{_(chat_id,'blacklist')}</b>\n{_(chat_id,'blacklist_desc', count=bl_count)}", chat_id, call.message.message_id, reply_markup=kb)

# ---------- Listing Helpers ----------
def list_notes(call):
    chat_id = call.message.chat.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, key FROM notes WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.answer_callback_query(call.id, "No notes found.", show_alert=True)
        return
    # build message
    lines = ["<b>Notes</b>"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in rows:
        lines.append(f"- {safe_html(r['key'])}")
        kb.add(btn(f"🗑️ {r['key']}", callback_data=f"note:del:{r['key']}"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=kb)

def list_triggers(call):
    chat_id = call.message.chat.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, pattern, reply FROM triggers WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.answer_callback_query(call.id, "No triggers.", show_alert=True)
        return
    lines = ["<b>Triggers</b>"]
    kb = types.InlineKeyboardMarkup(row_width=3)
    menu = menu_get(chat_id)
    meta = menu.get('triggers_meta', {})
    for r in rows:
        tid = r['id']
        ent = meta.get(str(tid), {"enabled": True})
        state_text = _(chat_id, 'enabled') if ent.get('enabled', True) else _(chat_id, 'disabled')
        lines.append(f"- [{state_text}] {safe_html(r['pattern'])} -> {safe_html(r['reply'])}")
        # buttons: state toggle | delete
        kb.add(btn(state_text, callback_data=f"trigger:{'enable' if not ent.get('enabled', True) else 'disable'}:{tid}"),
               btn("🗑️", callback_data=f"trigger:del:{tid}"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=kb)

def list_blacklist(call):
    chat_id = call.message.chat.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, word FROM blacklist WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.answer_callback_query(call.id, "No blacklist entries.", show_alert=True)
        return
    lines = ["<b>Blacklist</b>"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in rows:
        lines.append(f"- {safe_html(r['word'])}")
        kb.add(btn(f"🗑️ {r['word']}", callback_data=f"blacklist:del:{r['word']}"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=kb)

def list_polls(call):
    chat_id = call.message.chat.id
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, question, options_json, open FROM polls WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.answer_callback_query(call.id, "No polls.", show_alert=True)
        return
    lines = ["<b>Polls</b>"]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for r in rows:
        status = "Open" if r['open'] else "Closed"
        lines.append(f"- ({status}) {safe_html(r['question'])}")
        # add action button to toggle open/close
        action = "close" if r['open'] else "open"
        kb.add(btn(f"{action.title()}", callback_data=f"poll:{action}:{r['id']}"))
    kb.add(btn(_(chat_id,'back'), callback_data="menu:back"))
    bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=kb)

# ---------- Message Handlers for Multi-step states ----------
@bot.message_handler(func=lambda m: (m.from_user.id, 'adding_note') in STATE, content_types=['text'])
def handle_adding_note(message):
    key = message.text.split("|",1)[0].strip() if "|" in message.text else None
    content = message.text.split("|",1)[1].strip() if "|" in message.text else None
    st = STATE.pop((message.from_user.id, 'adding_note'), None)
    if not st or not key or not content:
        bot.reply_to(message, _(message.chat.id, 'invalid_input'))
        return
    chat_id = st['chat_id']
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO notes (chat_id, key, content, created_at) VALUES (?, ?, ?, ?)", (str(chat_id), key, content, now_ts()))
    conn.commit()
    conn.close()
    bot.reply_to(message, _(chat_id, 'note_added', key=key))
    # notify group optionally
    try:
        bot.send_message(chat_id, f"📝 Note added: {safe_html(key)}")
    except:
        pass

@bot.message_handler(func=lambda m: (m.from_user.id, 'adding_trigger') in STATE, content_types=['text'])
def handle_adding_trigger(message):
    st = STATE.pop((message.from_user.id, 'adding_trigger'), None)
    if not st:
        bot.reply_to(message, _(message.chat.id, 'invalid_input'))
        return
    chat_id = st['chat_id']
    if "|" not in message.text:
        bot.reply_to(message, _(chat_id, 'invalid_input'))
        return
    pattern, reply = [p.strip() for p in message.text.split("|",1)]
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO triggers (chat_id, pattern, reply) VALUES (?, ?, ?)", (str(chat_id), pattern, reply))
    conn.commit()
    trig_id = c.lastrowid
    conn.close()
    # default triggers_meta enabled
    menu = menu_get(chat_id)
    meta = menu.get('triggers_meta', {})
    meta[str(trig_id)] = {"enabled": True, "match_type": "text"}
    menu['triggers_meta'] = meta
    menu_set(chat_id, menu)
    bot.reply_to(message, _(chat_id, 'trigger_added'))
    try:
        bot.send_message(chat_id, f"🤖 Trigger added: {safe_html(pattern)}")
    except:
        pass

@bot.message_handler(func=lambda m: (m.from_user.id, 'adding_blacklist') in STATE, content_types=['text'])
def handle_adding_blacklist(message):
    st = STATE.pop((message.from_user.id, 'adding_blacklist'), None)
    if not st:
        bot.reply_to(message, _(message.chat.id, 'invalid_input'))
        return
    chat_id = st['chat_id']
    word = message.text.strip()
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO blacklist (chat_id, word) VALUES (?, ?)", (str(chat_id), word))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Blacklist word added: {safe_html(word)}")
    try:
        bot.send_message(chat_id, f"🚫 Word blacklisted: {safe_html(word)}")
    except:
        pass

@bot.message_handler(func=lambda m: (m.from_user.id, 'creating_poll') in STATE, content_types=['text'])
def handle_creating_poll(message):
    st = STATE.pop((message.from_user.id, 'creating_poll'), None)
    if not st:
        bot.reply_to(message, _(message.chat.id, 'invalid_input'))
        return
    chat_id = st['chat_id']
    if "|" not in message.text:
        bot.reply_to(message, _(chat_id, 'invalid_input'))
        return
    q, opts = [p.strip() for p in message.text.split("|",1)]
    options = [o.strip() for o in opts.split(";") if o.strip()]
    if len(options) < 2:
        bot.reply_to(message, _(chat_id, 'invalid_input'))
        return
    conn = db()
    c = conn.cursor()
    c.execute("INSERT INTO polls (chat_id, question, options_json, multiple, open, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (str(chat_id), q, json.dumps(options, ensure_ascii=False), 0, 1, now_ts()))
    conn.commit()
    conn.close()
    bot.reply_to(message, _(chat_id, 'poll_created'))
    try:
        # send a Telegram native poll to the group
        bot.send_poll(chat_id, q, options, is_anonymous=False)
    except:
        pass

# ---------- Lock toggle handling (simple) ----------
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("lock:"))
def handle_lock_callbacks(call):
    data = call.data
    chat_id = call.message.chat.id
    parts = data.split(":")
    if len(parts) >= 3 and parts[1] == 'toggle':
        key = parts[2]
        locks = locks_get(chat_id)
        locks[key] = not locks.get(key, False)
        locks_set(chat_id, locks)
        bot.answer_callback_query(call.id, _(chat_id, 'setting_updated'))
        show_locks_menu(call)
        return

# ---------- Moderation (reaction buttons) ----------
@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("mod:"))
def handle_mod_callbacks(call):
    data = call.data
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    if not is_user_admin(chat_id, user_id):
        bot.answer_callback_query(call.id, _(chat_id, 'admin_only'), show_alert=True)
        return
    cmd = data.split(":")[1]
    # These actions require context (reply). We'll instruct user how to apply.
    if cmd in ['warn','mute','ban','kick']:
        bot.answer_callback_query(call.id, f"Use this by replying to a user's message with /{cmd}", show_alert=True)
    else:
        bot.answer_callback_query(call.id, _(chat_id, 'unknown_action'), show_alert=True)

# ---------- Message Processing: XP, Triggers, Blacklist ----------
def add_xp_for_message(chat_id, user_id):
    """
    Award XP respecting xp_enabled and cooldown.
    """
    menu = menu_get(chat_id)
    xp_meta = menu.get('xp_settings', {"xp_enabled": True, "xp_cooldown": 10})
    if not xp_meta.get('xp_enabled', True):
        return
    cooldown = xp_meta.get('xp_cooldown', 10)
    conn = db()
    c = conn.cursor()
    c.execute("SELECT points, last_at FROM xp WHERE chat_id=? AND user_id=?", (str(chat_id), str(user_id)))
    row = c.fetchone()
    nowt = now_ts()
    if row:
        last = row['last_at'] or 0
        if nowt - last < cooldown:
            conn.close()
            return
        new_points = row['points'] + random.randint(1,3)
        c.execute("UPDATE xp SET points=?, last_at=? WHERE chat_id=? AND user_id=?", (new_points, nowt, str(chat_id), str(user_id)))
    else:
        new_points = random.randint(1,3)
        c.execute("INSERT INTO xp (chat_id, user_id, points, last_at) VALUES (?, ?, ?, ?)", (str(chat_id), str(user_id), new_points, nowt))
    conn.commit()
    conn.close()
    # Optionally send a small message (we avoid spamming; only send if user reaches multiples of 50)
    if new_points % 50 == 0:
        try:
            bot.send_message(chat_id, _(chat_id, 'xp_gained', points=new_points))
        except:
            pass

# Triggers processing
def process_triggers(message):
    chat_id = message.chat.id
    text = message.text or ""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT id, pattern, reply, is_regex FROM triggers WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return
    menu = menu_get(chat_id)
    meta = menu.get('triggers_meta', {})
    for r in rows:
        tid = str(r['id'])
        ent = meta.get(tid, {"enabled": True})
        if not ent.get('enabled', True):
            continue
        try:
            if r['is_regex']:
                if re.search(r['pattern'], text, re.IGNORECASE):
                    bot.reply_to(message, r['reply'])
                    return
            else:
                if r['pattern'].lower() in text.lower():
                    bot.reply_to(message, r['reply'])
                    return
        except Exception:
            logging.exception("trigger eval failed")

# Blacklist processing
def process_blacklist(message):
    chat_id = message.chat.id
    text = message.text or ""
    conn = db()
    c = conn.cursor()
    c.execute("SELECT word FROM blacklist WHERE chat_id=?", (str(chat_id),))
    rows = c.fetchall()
    conn.close()
    if not rows:
        return
    for r in rows:
        w = r['word']
        if w.lower() in text.lower():
            # simple action: delete message if bot has rights, warn user
            try:
                bot.delete_message(chat_id, message.message_id)
            except:
                pass
            bot.send_message(chat_id, _(chat_id, 'blacklist_violation', count=1))
            return

# Message handler for text messages to run XP, triggers, blacklist
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'sticker', 'document'])
def handle_all_messages(message):
    chat_type = message.chat.type
    # Only process group messages for trigger/blacklist/xp
    if chat_type in ['group', 'supergroup']:
        # XP
        try:
            add_xp_for_message(message.chat.id, message.from_user.id)
        except Exception:
            logging.exception("XP awarding failed")
        # Triggers
        try:
            process_triggers(message)
        except Exception:
            logging.exception("Triggers processing failed")
        # Blacklist
        try:
            process_blacklist(message)
        except Exception:
            logging.exception("Blacklist processing failed")
    # Additionally handle replies that are admin commands / note retrieval
    if message.text and message.text.startswith("/note"):
        parts = message.text.split(maxsplit=1)
        key = parts[1].strip() if len(parts) > 1 else None
        if key:
            conn = db()
            c = conn.cursor()
            c.execute("SELECT content FROM notes WHERE chat_id=? AND key=?", (str(message.chat.id), key))
            row = c.fetchone()
            conn.close()
            if row:
                bot.reply_to(message, row['content'])
            else:
                bot.reply_to(message, _(message.chat.id, 'user_not_found'))
                
                # ---------- Admin Commands for Testing / Utility ----------
@bot.message_handler(commands=['menu'])
def handle_menu_command(message):
    chat_id = message.chat.id
    if message.chat.type == 'private':
        # private menu: show direct
        send_menu(chat_id, private=True)
    else:
        # group menu: only for admins
        if not is_user_admin(chat_id, message.from_user.id):
            bot.reply_to(message, _(chat_id, 'admin_only'))
            return
        send_menu(chat_id)

@bot.message_handler(commands=['warn'])
def handle_warn_command(message):
    chat_id = message.chat.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, _(chat_id, 'admin_only'))
        return
    if not message.reply_to_message:
        bot.reply_to(message, _(chat_id, 'usage', usage="/warn <reply a user>"))
        return
    user = message.reply_to_message.from_user
    # For demo, we just reply with warn message
    bot.reply_to(message, _(chat_id, 'user_warned', user=user.first_name, count=1))

@bot.message_handler(commands=['mute'])
def handle_mute_command(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, _(chat_id, 'admin_only'))
        return
    if not message.reply_to_message:
        bot.reply_to(message, _(chat_id, 'usage', usage="/mute <reply>"))
        return
    user = message.reply_to_message.from_user
    duration = "10m"
    try:
        bot.restrict_chat_member(chat_id, user.id, permissions=telebot.types.ChatPermissions(can_send_messages=False))
        bot.reply_to(message, _(chat_id, 'user_muted', user=user.first_name, duration=duration))
    except Exception:
        bot.reply_to(message, _(chat_id, 'start_group_not_admin'))

@bot.message_handler(commands=['ban'])
def handle_ban_command(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, _(chat_id, 'admin_only'))
        return
    if not message.reply_to_message:
        bot.reply_to(message, _(chat_id, 'usage', usage="/ban <reply>"))
        return
    user = message.reply_to_message.from_user
    try:
        bot.ban_chat_member(chat_id, user.id)
        bot.reply_to(message, _(chat_id, 'user_banned', user=user.first_name))
    except Exception:
        bot.reply_to(message, _(chat_id, 'start_group_not_admin'))

@bot.message_handler(commands=['kick'])
def handle_kick_command(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, _(chat_id, 'admin_only'))
        return
    if not message.reply_to_message:
        bot.reply_to(message, _(chat_id, 'usage', usage="/kick <reply>"))
        return
    user = message.reply_to_message.from_user
    try:
        bot.unban_chat_member(chat_id, user.id)  # works as kick
        bot.reply_to(message, _(chat_id, 'user_kicked', user=user.first_name))
    except Exception:
        bot.reply_to(message, _(chat_id, 'start_group_not_admin'))


# ---------- Error Logging ----------
@bot.message_handler(func=lambda m: True, content_types=['new_chat_members'])
def handle_new_member(message):
    chat_id = message.chat.id
    for member in message.new_chat_members:
        try:
            bot.send_message(chat_id, _(chat_id, 'welcome_message', name=member.first_name))
        except Exception:
            pass

@bot.message_handler(func=lambda m: True, content_types=['left_chat_member'])
def handle_left_member(message):
    chat_id = message.chat.id
    try:
        name = message.left_chat_member.first_name
        bot.send_message(chat_id, _(chat_id, 'goodbye_message', name=name))
    except Exception:
        pass

@bot.message_handler(commands=['lang'])
def handle_lang_command(message):
    chat_id = message.chat.id
    cur = get_settings(chat_id).get('lang', 'hi')
    new = 'en' if cur == 'hi' else 'hi'
    set_setting(chat_id, 'lang', new)
    bot.reply_to(message, _(chat_id, 'lang_changed'))
    send_menu(chat_id)

# ---------- Safe Polling with Retry ----------
def safe_polling():
    while True:
        try:
            logging.info("🤖 Bot polling started.")
            bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            logging.exception("Polling error, retrying in 10s...")
            time.sleep(10)

# ---------- Startup ----------
if __name__ == "__main__":
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username
        logging.info(f"✅ Bot logged in as {me.first_name} (@{BOT_USERNAME})")
    except Exception as e:
        logging.exception("Failed to fetch bot info.")
        sys.exit(1)
    safe_polling()