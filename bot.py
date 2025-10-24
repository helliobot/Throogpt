import sqlite3
import telebot
import os
import json
import time
import random
import re
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
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logging.error("❌ BOT_TOKEN not found! Check your Choreo Environment Variables.")
    exit()
bot = telebot.TeleBot(TOKEN)

# Global locks and caches
flood_locks = defaultdict(Lock)
user_messages = defaultdict(list)
MENU_CACHE = {}
bot.temp_data = {}  # For state management

# Language translations
translations = {
    'en': {
        'main_menu': "🔧 MAIN MENU\n\n"
                     "🛡️ Verify: User verification settings\n"
                     "👋 Welcome: Greetings for new members\n"
                     "📬 Triggers: Auto-responses to keywords\n"
                     "⏰ Schedule: Timed messages\n"
                     "🔒 Moderation: Locks and penalties\n"
                     "🧹 Clean: Auto-delete rules\n"
                     "🚫 Block: Block lists\n"
                     "🌐 Lang: Language settings\n"
                     "⚙️ Advanced: Extra tools",
        'group_menu': "🏛️ GROUP MANAGEMENT\n\n"
                      "🔒 Locks: Restrict content types\n"
                      "🛡️ CAPTCHA: Verify new users\n"
                      "📊 Analytics: Group stats\n"
                      "🎯 Triggers: Keyword responses\n"
                      "👋 Welcome: Join/leave messages\n"
                      "🛡️ Flood: Anti-spam limits\n"
                      "📢 Broadcast: Mass messages\n"
                      "🚫 Blacklists: Word filters\n"
                      "👑 Permissions: User roles\n"
                      "⚙️ Commands: Custom cmds\n"
                      "📊 Polls: Advanced voting\n"
                      "📝 Notes: Tagged notes\n"
                      "📰 RSS: Feed updates\n"
                      "💰 Subs: User plans\n"
                      "🔗 Federation: Linked groups\n"
                      "🎲 Captcha: Verification types\n"
                      "💾 Dump: Deleted msg logs\n"
                      "🔌 Plugins: Extra modules",
        'analytics_menu': "📊 ANALYTICS MENU\n\n{stats}\n\n"
                          "📈 Weekly: Last 7 days stats\n"
                          "📉 Monthly: Last 30 days stats\n"
                          "📤 Report: Export data",
        'triggers_menu': "🎯 TRIGGERS MENU\n\n"
                         "➕ Add: Create new trigger\n"
                         "📝 List: View all triggers\n"
                         "✏️ Edit: Modify existing\n"
                         "🗑️ Delete: Remove trigger",
        'welcome_menu': "👋 WELCOME MESSAGES\n\n"
                        "👋 Set Welcome: Greeting for joins\n"
                        "👋 Preview: See current\n"
                        "🚪 Set Leave: Farewell for leaves",
        'flood_menu': "🛡️ ANTI-FLOOD MENU\n\n"
                      "🛡️ Enable: Turn on/off\n"
                      "⚙️ Set Limit: Msgs per min\n"
                      "📊 Stats: Flood incidents",
        'broadcast_menu': "📢 BROADCAST MENU\n\n"
                          "📢 Send Now: Immediate msg\n"
                          "👥 Select Groups: Target groups\n"
                          "📋 Preview: See msg",
        'blacklist_menu': "🚫 BLACKLISTS MENU\n\n"
                          "➕ Add Word: Simple word filter\n"
                          "⚡ Add Regex: Pattern filter\n"
                          "📝 List: View filters\n"
                          "🗑️ Remove: Delete filter",
        'advanced_menu': "⚙️ ADVANCED TOOLS\n\n"
                         "👑 Permissions: Role management\n"
                         "⚙️ Custom Cmds: User-defined commands\n"
                         "📊 Polls: Voting systems\n"
                         "📝 Notes: Tagged reminders\n"
                         "📰 RSS: Feed subscriptions\n"
                         "💰 Subscriptions: User plans\n"
                         "🔗 Federation: Group linking\n"
                         "🎲 Captcha Types: Verification options\n"
                         "💾 Message Dump: Deleted logs\n"
                         "🔌 Plugins: Extra features",
        'permissions_menu': "👑 PERMISSIONS MENU\n\n"
                            "👑 Grant Role: Assign mod/admin\n"
                            "📋 List Roles: View assigned\n"
                            "⚙️ Set Commands: Role permissions\n"
                            "⏰ Set Duration: Time-limited roles",
        'customcmd_menu': "⚙️ CUSTOM COMMANDS MENU\n\n"
                          "➕ Create: New command\n"
                          "📝 List: View commands\n"
                          "✏️ Edit: Modify command",
        'polls_menu': "📊 POLLS MENU\n\n"
                      "📊 New Poll: Create poll\n"
                      "⚙️ Settings: Poll options\n"
                      "📋 Active: View polls",
        'notes_menu': "📝 NOTES MENU\n\n"
                      "➕ Save Note: Add tagged note\n"
                      "🔍 Search: Find notes\n"
                      "📤 Share: Send note",
        'rss_menu': "📰 RSS MENU\n\n"
                    "➕ Add Feed: New URL\n"
                    "📝 List: View feeds\n"
                    "✏️ Edit: Modify feed",
        'subs_menu': "💰 SUBSCRIPTIONS MENU\n\n"
                     "➕ Grant Plan: Assign to user\n"
                     "📝 List: View subs\n"
                     "✏️ Edit: Modify plan",
        'fed_menu': "🔗 FEDERATION MENU\n\n"
                    "🔗 Link Group: Connect groups\n"
                    "📝 List: View links\n"
                    "⚙️ Sync: Action sync settings",
        'captcha_menu': "🎲 CAPTCHA MENU\n\n"
                        "⚙️ Set Type: Math/text/image\n"
                        "📊 Difficulty: Easy/hard\n"
                        "⏰ Time Limit: Fail timeout\n"
                        "🛑 Fail Action: Kick/mute",
        'dump_menu': "💾 MESSAGE DUMP MENU\n\n"
                     "🛑 Enable: Turn on/off\n"
                     "📤 Channel: Set dump channel\n"
                     "📝 View: See dumped messages",
        'plugins_menu': "🔌 PLUGINS MENU\n\n"
                        "➕ Install: Add new plugin\n"
                        "📝 List: View plugins\n"
                        "⚙️ Config: Plugin settings",
        'moderation_lock_menu': "🔒 MODERATION LOCKS\n\n"
                                "🔗 Links: {links_status}\n"
                                "📸 Media: {media_status}\n"
                                "😀 Stickers: {stickers_status}\n"
                                "📤 Forwards: {forwards_status}",
        'lang_menu': "🌐 LANGUAGE MENU\n\n"
                     "🇬🇧 English: Set to English\n"
                     "🇮🇳 Hindi: Set to Hindi",
        'commands_list': "📋 AVAILABLE COMMANDS\n\n"
                         "/start - Start bot\n"
                         "/status - Group settings\n"
                         "/warn @user reason - Warn user\n"
                         "/unwarn @user - Remove warn\n"
                         "/ban @user reason - Ban user\n"
                         "/unban @user - Unban user\n"
                         "/mute @user time reason - Mute user\n"
                         "/unmute @user - Unmute user\n"
                         "/settings - Open settings\n"
                         "/lang - Change language",
        'start_private': "{user}, Ultimate Advanced Bot!",
        'start_group': "🤖 Advanced Group Bot Active!",
        'admin_only': "Group creator or admin only!",
        'welcome_default': "Welcome!",
        'leave_default': "Goodbye!",
        'trigger_added': "✅ Trigger added!",
        'trigger_exists': "❌ Trigger already exists!",
        'trigger_updated': "✅ Trigger '{keyword}' updated!",
        'trigger_deleted': "✅ Trigger deleted!",
        'trigger_not_found': "❌ Trigger not found!",
        'trigger_too_long': "❌ Keyword or response too long!",
        'invalid_regex': "❌ Invalid regex pattern!",
        'welcome_set': "✅ Message set!",
        'welcome_empty': "❌ Message cannot be empty!",
        'flood_enabled': "✅ Flood {status}!",
        'flood_limit_set': "✅ Limit set to {limit}!",
        'flood_invalid_limit': "❌ Limit must be between 1 and 50!",
        'flood_invalid_number': "❌ Invalid number!",
        'flood_violation': "🛑 Slow down! Message deleted.",
        'flood_mute': "🛑 You are muted for flooding!",
        'flood_ban': "🛑 You are banned for flooding!",
        'blacklist_added': "✅ Blacklist added!",
        'blacklist_exists': "❌ Word already blacklisted!",
        'blacklist_blocked': "🚫 Blocked!",
        'blacklist_too_long': "❌ Word too long!",
        'blacklist_removed': "✅ Blacklist removed!",
        'captcha_expired': "❌ Captcha expired!",
        'captcha_timeout': "❌ Captcha timed out!",
        'captcha_verified': "✅ Verified!",
        'captcha_wrong': "❌ Wrong answer!",
        'role_granted': "✅ {role} granted to {user_name} (ID: {user_id})!",
        'role_error': "❌ Error granting role!",
        'command_added': "✅ Custom command added!",
        'command_exists': "❌ Command already exists!",
        'command_updated': "✅ Command /{trigger} updated!",
        'command_too_long': "❌ Trigger or response too long!",
        'poll_created': "✅ Poll {poll_id} created!",
        'poll_invalid': "❌ Invalid anonymous or timer value!",
        'note_saved': "✅ Note saved!",
        'note_invalid_expire': "❌ Invalid expire format (e.g., 1d)!",
        'note_shared': "✅ Note shared!",
        'rss_added': "✅ RSS added!",
        'rss_invalid_url': "❌ Invalid URL!",
        'rss_invalid_interval': "❌ Invalid interval format (e.g., 1h)!",
        'rss_updated': "✅ RSS feed updated!",
        'sub_granted': "✅ Subscription granted!",
        'sub_invalid_duration': "❌ Invalid duration format (e.g., 1m)!",
        'sub_updated': "✅ Subscription updated!",
        'fed_linked': "✅ Group linked!",
        'fed_error': "❌ Error linking group!",
        'fed_sync_set': "✅ Sync settings updated!",
        'captcha_saved': "✅ CAPTCHA settings saved!",
        'captcha_error': "❌ Error saving CAPTCHA settings!",
        'captcha_invalid_difficulty': "❌ Invalid difficulty! Use easy/medium/hard.",
        'captcha_invalid_time': "❌ Invalid time format (e.g., 5m)!",
        'captcha_invalid_action': "❌ Invalid action! Use kick/mute.",
        'dump_enabled': "✅ Message dump {status}!",
        'dump_channel_set': "✅ Dump channel set!",
        'dump_invalid_channel': "❌ Invalid channel ID!",
        'dump_error': "❌ Error updating dump settings!",
        'plugin_installed': "✅ Plugin installed!",
        'plugin_error': "❌ Error installing plugin!",
        'plugin_configured': "✅ Plugin configured!",
        'lock_set': "✅ {action} lock {status}!",
        'lock_error': "❌ Error setting {action} lock!",
        'invalid_input': "❌ Invalid input! Use 'on' or 'off'.",
        'lang_set': "✅ Language set to {lang}!",
        'lang_error': "❌ Invalid language! Use 'english' or 'hindi'.",
        'broadcast_sent': "✅ Broadcast sent!",
        'broadcast_error': "❌ Error sending broadcast!",
        'permissions_updated': "✅ Permissions updated!",
        'permissions_invalid': "❌ Invalid commands format!",
    },
    'hi': {
        'main_menu': "🔧 मुख्य मेन्यू\n\n"
                     "🛡️ सत्यापन: उपयोगकर्ता सत्यापन सेटिंग्स\n"
                     "👋 स्वागत: नए सदस्यों के लिए अभिवादन\n"
                     "📬 ट्रिगर्स: कीवर्ड्स के लिए ऑटो-रिस्पॉन्स\n"
                     "⏰ शेड्यूल: समयबद्ध संदेश\n"
                     "🔒 मॉडरेशन: लॉक और दंड\n"
                     "🧹 सफाई: ऑटो-डिलीट नियम\n"
                     "🚫 ब्लॉक: ब्लॉक लिस्ट\n"
                     "🌐 भाषा: भाषा सेटिंग्स\n"
                     "⚙️ उन्नत: अतिरिक्त उपकरण",
        'group_menu': "🏛️ समूह प्रबंधन\n\n"
                      "🔒 लॉक: सामग्री प्रकार प्रतिबंधित करें\n"
                      "🛡️ कैप्चा: नए उपयोगकर्ताओं का सत्यापन\n"
                      "📊 एनालिटिक्स: समूह आँकड़े\n"
                      "🎯 ट्रिगर्स: कीवर्ड रिस्पॉन्स\n"
                      "👋 स्वागत: शामिल/छोड़ने के संदेश\n"
                      "🛡️ फ्लड: एंटी-स्पैम सीमाएँ\n"
                      "📢 प्रसारण: सामूहिक संदेश\n"
                      "🚫 ब्लैकलिस्ट: शब्द फिल्टर\n"
                      "👑 अनुमतियाँ: उपयोगकर्ता भूमिकाएँ\n"
                      "⚙️ कमांड्स: कस्टम कमांड्स\n"
                      "📊 पोल्स: उन्नत मतदान\n"
                      "📝 नोट्स: टैग किए गए नोट्स\n"
                      "📰 RSS: फ़ीड अपडेट्स\n"
                      "💰 सदस्यताएँ: उपयोगकर्ता योजनाएँ\n"
                      "🔗 फेडरेशन: लिंक्ड समूह\n"
                      "🎲 कैप्चा: सत्यापन प्रकार\n"
                      "💾 डंप: हटाए गए संदेश लॉग\n"
                      "🔌 प्लगइन्स: अतिरिक्त मॉड्यूल",
        'analytics_menu': "📊 एनालिटिक्स मेन्यू\n\n{stats}\n\n"
                          "📈 साप्ताहिक: पिछले 7 दिन के आँकड़े\n"
                          "📉 मासिक: पिछले 30 दिन के आँकड़े\n"
                          "📤 रिपोर्ट: डेटा निर्यात करें",
        'triggers_menu': "🎯 ट्रिगर्स मेन्यू\n\n"
                         "➕ जोड़ें: नया ट्रिगर बनाएँ\n"
                         "📝 सूची: सभी ट्रिगर्स देखें\n"
                         "✏️ संपादन: मौजूदा में बदलाव\n"
                         "🗑️ हटाएँ: ट्रिगर हटाएँ",
        'welcome_menu': "👋 स्वागत संदेश\n\n"
                        "👋 स्वागत सेट करें: शामिल होने के लिए अभिवादन\n"
                        "👋 पूर्वावलोकन: वर्तमान देखें\n"
                        "🚪 छोड़ने का संदेश: अलविदा संदेश",
        'flood_menu': "🛡️ एंटी-फ्लड मेन्यू\n\n"
                      "🛡️ सक्षम करें: चालू/बंद करें\n"
                      "⚙️ सीमा सेट करें: प्रति मिनट संदेश\n"
                      "📊 आँकड़े: फ्लड घटनाएँ",
        'broadcast_menu': "📢 प्रसारण मेन्यू\n\n"
                          "📢 अभी भेजें: तत्काल संदेश\n"
                          "👥 समूह चुनें: लक्षित समूह\n"
                          "📋 पूर्वावलोकन: संदेश देखें",
        'blacklist_menu': "🚫 ब्लैकलिस्ट मेन्यू\n\n"
                          "➕ शब्द जोड़ें: साधारण शब्द फिल्टर\n"
                          "⚡ रेगेक्स जोड़ें: पैटर्न फिल्टर\n"
                          "📝 सूची: फिल्टर देखें\n"
                          "🗑️ हटाएँ: फिल्टर हटाएँ",
        'advanced_menu': "⚙️ उन्नत उपकरण\n\n"
                         "👑 अनुमतियाँ: भूमिका प्रबंधन\n"
                         "⚙️ कस्टम कमांड्स: उपयोगकर्ता-परिभाषित कमांड्स\n"
                         "📊 पोल्स: मतदान सिस्टम\n"
                         "📝 नोट्स: टैग किए गए रिमाइंडर\n"
                         "📰 RSS: फ़ीड सदस्यताएँ\n"
                         "💰 सदस्यताएँ: उपयोगकर्ता योजनाएँ\n"
                         "🔗 फेडरेशन: समूह लिंकिंग\n"
                         "🎲 कैप्चा प्रकार: सत्यापन विकल्प\n"
                         "💾 संदेश डंप: हटाए गए लॉग\n"
                         "🔌 प्लगइन्स: अतिरिक्त सुविधाएँ",
        'permissions_menu': "👑 अनुमतियाँ मेन्यू\n\n"
                            "👑 भूमिका प्रदान करें: मॉड/एडमिन असाइन करें\n"
                            "📋 भूमिकाएँ सूची: असाइन की गई देखें\n"
                            "⚙️ कमांड्स सेट करें: भूमिका अनुमतियाँ\n"
                            "⏰ अवधि सेट करें: समय-सीमित भूमिकाएँ",
        'customcmd_menu': "⚙️ कस्टम कमांड्स मेन्यू\n\n"
                          "➕ बनाएँ: नया कमांड\n"
                          "📝 सूची: कमांड्स देखें\n"
                          "✏️ संपादन: कमांड में बदलाव",
        'polls_menu': "📊 पोल्स मेन्यू\n\n"
                      "📊 नया पोल: पोल बनाएँ\n"
                      "⚙️ सेटिंग्स: पोल विकल्प\n"
                      "📋 सक्रिय: पोल्स देखें",
        'notes_menu': "📝 नोट्स मेन्यू\n\n"
                      "➕ नोट सहेजें: टैग किया नोट जोड़ें\n"
                      "🔍 खोजें: नोट्स खोजें\n"
                      "📤 साझा करें: नोट भेजें",
        'rss_menu': "📰 RSS मेन्यू\n\n"
                    "➕ फ़ीड जोड़ें: नया URL\n"
                    "📝 सूची: फ़ीड्स देखें\n"
                    "✏️ संपादन: फ़ीड में बदलाव",
        'subs_menu': "💰 सदस्यताएँ मेन्यू\n\n"
                     "➕ योजना प्रदान करें: उपयोगकर्ता को असाइन करें\n"
                     "📝 सूची: सदस्यताएँ देखें\n"
                     "✏️ संपादन: योजना में बदलाव",
        'fed_menu': "🔗 फेडरेशन मेन्यू\n\n"
                    "🔗 समूह लिंक करें: समूहों को जोड़ें\n"
                    "📝 सूची: लिंक देखें\n"
                    "⚙️ सिंक: एक्शन सिंक सेटिंग्स",
        'captcha_menu': "🎲 कैप्चा मेन्यू\n\n"
                        "⚙️ प्रकार सेट करें: गणित/टेक्स्ट/इमेज\n"
                        "📊 कठिनाई: आसान/कठिन\n"
                        "⏰ समय सीमा: असफल होने की समय-सीमा\n"
                        "🛑 असफल एक्शन: किक/म्यूट",
        'dump_menu': "💾 संदेश डंप मेन्यू\n\n"
                     "🛑 सक्षम करें: चालू/बंद करें\n"
                     "📤 चैनल: डंप चैनल सेट करें\n"
                     "📝 देखें: हटाए गए संदेश देखें",
        'plugins_menu': "🔌 प्लगइन्स मेन्यू\n\n"
                        "➕ इंस्टॉल करें: नया प्लगइन जोड़ें\n"
                        "📝 सूची: प्लगइन्स देखें\n"
                        "⚙️ कॉन्फ़िग: प्लगइन सेटिंग्स",
        'moderation_lock_menu': "🔒 मॉडरेशन लॉक\n\n"
                                "🔗 लिंक: {links_status}\n"
                                "📸 मीडिया: {media_status}\n"
                                "😀 स्टिकर्स: {stickers_status}\n"
                                "📤 फ़ॉरवर्ड: {forwards_status}",
        'lang_menu': "🌐 भाषा मेन्यू\n\n"
                     "🇬🇧 अंग्रेजी: अंग्रेजी में सेट करें\n"
                     "🇮🇳 हिंदी: हिंदी में सेट करें",
        'commands_list': "📋 उपलब्ध कमांड्स\n\n"
                         "/start - बॉट शुरू करें\n"
                         "/status - समूह सेटिंग्स\n"
                         "/warn @user कारण - उपयोगकर्ता को चेतावनी दें\n"
                         "/unwarn @user - चेतावनी हटाएँ\n"
                         "/ban @user कारण - उपयोगकर्ता को प्रतिबंधित करें\n"
                         "/unban @user - प्रतिबंध हटाएँ\n"
                         "/mute @user समय कारण - उपयोगकर्ता को म्यूट करें\n"
                         "/unmute @user - म्यूट हटाएँ\n"
                         "/settings - सेटिंग्स खोलें\n"
                         "/lang - भाषा बदलें",
        'start_private': "{user}, अल्टिमेट एडवांस्ड बॉट!",
        'start_group': "🤖 उन्नत समूह बॉट सक्रिय!",
        'admin_only': "केवल समूह निर्माता या एडमिन!",
        'welcome_default': "स्वागत है!",
        'leave_default': "अलविदा!",
        'trigger_added': "✅ ट्रिगर जोड़ा गया!",
        'trigger_exists': "❌ ट्रिगर पहले से मौजूद है!",
        'trigger_updated': "✅ ट्रिगर '{keyword}' अपडेट किया गया!",
        'trigger_deleted': "✅ ट्रिगर हटाया गया!",
        'trigger_not_found': "❌ ट्रिगर नहीं मिला!",
        'trigger_too_long': "❌ कीवर्ड या रिस्पॉन्स बहुत लंबा है!",
        'invalid_regex': "❌ अमान्य रेगेक्स पैटर्न!",
        'welcome_set': "✅ संदेश सेट किया गया!",
        'welcome_empty': "❌ संदेश खाली नहीं हो सकता!",
        'flood_enabled': "✅ फ्लड {status}!",
        'flood_limit_set': "✅ सीमा {limit} पर सेट की गई!",
        'flood_invalid_limit': "❌ सीमा 1 और 50 के बीच होनी चाहिए!",
        'flood_invalid_number': "❌ अमान्य संख्या!",
        'flood_violation': "🛑 धीमे करें! संदेश हटाया गया।",
        'flood_mute': "🛑 फ्लडिंग के लिए आपको म्यूट किया गया!",
        'flood_ban': "🛑 फ्लडिंग के लिए आपको प्रतिबंधित किया गया!",
        'blacklist_added': "✅ ब्लैकलिस्ट जोड़ा गया!",
        'blacklist_exists': "❌ शब्द पहले से ब्लैकलिस्ट में है!",
        'blacklist_blocked': "🚫 अवरुद्ध!",
        'blacklist_too_long': "❌ शब्द बहुत लंबा है!",
        'blacklist_removed': "✅ ब्लैकलिस्ट हटाया गया!",
        'captcha_expired': "❌ कैप्चा समाप्त हो गया!",
        'captcha_timeout': "❌ कैप्चा समय समाप्त!",
        'captcha_verified': "✅ सत्यापित!",
        'captcha_wrong': "❌ गलत जवाब!",
        'role_granted': "✅ {role} {user_name} (ID: {user_id}) को प्रदान किया गया!",
        'role_error': "❌ भूमिका प्रदान करने में त्रुटि!",
        'command_added': "✅ कस्टम कमांड जोड़ा गया!",
        'command_exists': "❌ कमांड पहले से मौजूद है!",
        'command_updated': "✅ कमांड /{trigger} अपडेट किया गया!",
        'command_too_long': "❌ ट्रिगर या रिस्पॉन्स बहुत लंबा है!",
        'poll_created': "✅ पोल {poll_id} बनाया गया!",
        'poll_invalid': "❌ अमान्य अनाम या टाइमर मान!",
        'note_saved': "✅ नोट सहेजा गया!",
        'note_invalid_expire': "❌ अमान्य समाप्ति प्रारूप (उदा., 1d)!",
        'note_shared': "✅ नोट साझा किया गया!",
        'rss_added': "✅ RSS जोड़ा गया!",
        'rss_invalid_url': "❌ अमान्य URL!",
        'rss_invalid_interval': "❌ अमान्य अंतराल प्रारूप (उदा., 1h)!",
        'rss_updated': "✅ RSS फ़ीड अपडेट किया गया!",
        'sub_granted': "✅ सदस्यता प्रदान की गई!",
        'sub_invalid_duration': "❌ अमान्य अवधि प्रारूप (उदा., 1m)!",
        'sub_updated': "✅ सदस्यता अपडेट की गई!",
        'fed_linked': "✅ समूह लिंक किया गया!",
        'fed_error': "❌ समूह लिंक करने में त्रुटि!",
        'fed_sync_set': "✅ सिंक सेटिंग्स अपडेट की गईं!",
        'captcha_saved': "✅ कैप्चा सेटिंग्स सहेजी गईं!",
        'captcha_error': "❌ कैप्चा सेटिंग्स सहेजने में त्रुटि!",
        'captcha_invalid_difficulty': "❌ अमान्य कठिनाई! आसान/मध्यम/कठिन का उपयोग करें।",
        'captcha_invalid_time': "❌ अमान्य समय प्रारूप (उदा., 5m)!",
        'captcha_invalid_action': "❌ अमान्य एक्शन! किक/म्यूट का उपयोग करें।",
        'dump_enabled': "✅ संदेश डंप {status}!",
        'dump_channel_set': "✅ डंप चैनल सेट किया गया!",
        'dump_invalid_channel': "❌ अमान्य चैनल ID!",
        'dump_error': "❌ डंप सेटिंग्स अपडेट करने में त्रुटि!",
        'plugin_installed': "✅ प्लगइन इंस्टॉल किया गया!",
        'plugin_error': "❌ प्लगइन इंस्टॉल करने में त्रुटि!",
        'plugin_configured': "✅ प्लगइन कॉन्फ़िगर किया गया!",
        'lock_set': "✅ {action} लॉक {status}!",
        'lock_error': "❌ {action} लॉक सेट करने में त्रुटि!",
        'invalid_input': "❌ अमान्य इनपुट! 'on' या 'off' का उपयोग करें।",
        'lang_set': "✅ भाषा {lang} पर सेट की गई!",
        'lang_error': "❌ अमान्य भाषा! 'english' या 'hindi' का उपयोग करें।",
        'broadcast_sent': "✅ प्रसारण भेजा गया!",
        'broadcast_error': "❌ प्रसारण भेजने में त्रुटि!",
        'permissions_updated': "✅ अनुमतियाँ अपडेट की गईं!",
        'permissions_invalid': "❌ अमान्य कमांड्स प्रारूप!",
    }
}

# DATABASE SETUP
def init_db():
    try:
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
                     (chat_id TEXT, message TEXT, sent INTEGER, groups TEXT)''')
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
        c.execute('''CREATE TABLE IF NOT EXISTS language_settings 
                     (chat_id TEXT, language TEXT)''')
        
        # Indexes for performance
        for table in ['settings', 'responses', 'schedules', 'blocks', 'warns', 'logs', 'analytics', 'triggers', 'welcome', 'flood_settings', 
                      'broadcasts', 'blacklists', 'permissions', 'custom_commands', 'polls', 'notes', 'rss_feeds', 'subscriptions', 
                      'federations', 'captchas', 'message_dump', 'plugins', 'language_settings']:
            c.execute(f'CREATE INDEX IF NOT EXISTS idx_{table}_chat ON {table}(chat_id)')
        
        conn.commit()
    except Exception as e:
        logging.error(f"Database setup error: {e}")
    finally:
        conn.close()

init_db()

# UTILITY FUNCTIONS
def delete_previous_reply(chat_id):
    key = f"last_reply_{chat_id}"
    if key in bot.temp_data:
        try:
            bot.delete_message(chat_id, bot.temp_data[key])
        except:
            pass
        del bot.temp_data[key]

def get_language(chat_id):
    try:
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        c.execute("SELECT language FROM language_settings WHERE chat_id=?", (chat_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 'en'
    except Exception as e:
        logging.error(f"Error getting language: {e}")
        return 'en'

def translate(key, chat_id, **kwargs):
    lang = get_language(chat_id)
    text = translations.get(lang, translations['en']).get(key, translations['en'][key])
    return text.format(**kwargs)

def sanitize_input(text):
    if not text:
        raise ValueError("Input cannot be empty")
    text = html.escape(text.strip())
    if len(text) > 4096:
        raise ValueError("Input too long (max 4096 characters)")
    return text

def validate_url(url):
    url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
    return bool(url_pattern.match(url))

def validate_time_format(time_str):
    time_pattern = re.compile(r'^\d+[smhd]$')
    return bool(time_pattern.match(time_str))

def validate_regex(regex_str):
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
    try:
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        if operation == "execute":
            c.execute(query, params)
        elif operation == "fetch":
            c.execute(query, params)
            return c.fetchall()
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def get_all_settings(chat_id):
    if chat_id in MENU_CACHE: 
        return MENU_CACHE[chat_id]
    settings = {}
    try:
        rows = safe_db_operation("SELECT feature, subfeature, data FROM settings WHERE chat_id=?", (chat_id,), "fetch")
        if rows:
            for row in rows:
                try:
                    settings[f"{row[0]}_{row[1]}"] = json.loads(row[2]) if row[2] else {'status': 'off'}
                except json.JSONDecodeError as e:
                    logging.error(f"JSON decode error for settings {row[0]}_{row[1]}: {e}")
                    settings[f"{row[0]}_{row[1]}"] = {'status': 'off'}
        MENU_CACHE[chat_id] = settings
    except Exception as e:
        logging.error(f"Error fetching settings for chat {chat_id}: {e}")
    return settings

def safe_json(data):
    try:
        parsed = json.loads(data) if data else {'status': 'off'}
        if not isinstance(parsed, dict):
            logging.error(f"Invalid JSON data, expected dict, got {type(parsed)}")
            return {'status': 'off'}
        return parsed if 'status' in parsed else {**parsed, 'status': 'off'}
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error: {e}")
        return {'status': 'off'}

def cleanup_temp_data():
    now = time.time()
    for key in list(bot.temp_data.keys()):
        if isinstance(bot.temp_data[key], dict) and 'timeout' in bot.temp_data[key] and now > bot.temp_data[key]['timeout']:
            del bot.temp_data[key]

# Run cleanup periodically
Thread(target=lambda: [cleanup_temp_data() or time.sleep(60) for _ in iter(int, 1)], daemon=True).start()

# FLOOD PROTECTION
def check_flood(chat_id, user_id):
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
    return translate('analytics_menu', chat_id, stats=f"📊 {total} actions, {users} users ({period})")

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
    default = translate('welcome_default', chat_id) if is_welcome else translate('leave_default', chat_id)
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
    
    delete_previous_reply(chat_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('main_menu', chat_id).split('\n')[0], callback_data='main'),
        types.InlineKeyboardButton(translate('commands_list', chat_id).split('\n')[0], callback_data='show_commands')
    )
    
    if message.chat.type == 'private':
        markup.add(
            types.InlineKeyboardButton("➕ Add to Group", url=f"t.me/{bot.get_me().username}?startgroup=true"),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='help')
        )
        text = translate('start_private', chat_id, user=user.first_name)
        sent_message = bot.reply_to(message, text, reply_markup=markup)
    else:
        markup.add(
            types.InlineKeyboardButton(translate('analytics_menu', chat_id).split('\n')[0], callback_data='analytics_menu'),
            types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[0], callback_data='triggers_menu'),
            types.InlineKeyboardButton(translate('welcome_menu', chat_id).split('\n')[0], callback_data='welcome_menu'),
            types.InlineKeyboardButton(translate('flood_menu', chat_id).split('\n')[0], callback_data='flood_menu'),
            types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[0], callback_data='broadcast_menu'),
            types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[0], callback_data='blacklist_menu')
        )
        text = translate('start_group', chat_id)
        sent_message = bot.send_message(chat_id, text, reply_markup=markup)
    
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# STATUS COMMAND
@bot.message_handler(commands=['status'])
def status_command(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    delete_previous_reply(chat_id)
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
        status_data = safe_json(settings.get(key, '{}'))
        status = status_data.get('status', 'off')
        status_text += f"{name}: {'✅' if status == 'on' else '❌'}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu'),
        types.InlineKeyboardButton(translate('commands_list', chat_id).split('\n')[0], callback_data='show_commands')
    )
    sent_message = bot.reply_to(message, status_text, reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# LANGUAGE COMMAND
@bot.message_handler(commands=['lang'])
def lang_command(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    delete_previous_reply(chat_id)
    bot.temp_data[chat_id] = {'action': 'lang_set', 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data='lang_english'),
        types.InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hindi'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='main')
    )
    sent_message = bot.reply_to(message, translate('lang_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# CONTENT HANDLER
@bot.message_handler(content_types=['text'])
def content_handler(message):
    chat_id = str(message.chat.id)
    text = sanitize_input(message.text)
    user_id = str(message.from_user.id)
    log_activity(chat_id, user_id, 'message', {'text': text})
    
    # Save message to dump if enabled
    settings = get_all_settings(chat_id)
    dump_settings = safe_json(settings.get('message_dump', '{}'))
    if dump_settings.get('status', 'off') == 'on':
        rows = safe_db_operation("SELECT dump_channel FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
        if rows:
            safe_db_operation("INSERT INTO message_dump VALUES (?, ?, ?, ?, ?)", 
                            (chat_id, text, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rows[0][0]))
    
    # ANTI-FLOOD
    flood_action = check_flood(chat_id, user_id)
    if flood_action:
        bot.delete_message(chat_id, message.message_id)
        delete_previous_reply(chat_id)
        if flood_action == 'mute':
            bot.restrict_chat_member(chat_id, user_id, permissions={'can_send_messages': False})
            sent_message = bot.reply_to(message, translate('flood_mute', chat_id))
        elif flood_action == 'ban':
            bot.kick_chat_member(chat_id, user_id)
            sent_message = bot.reply_to(message, translate('flood_ban', chat_id))
        else:
            sent_message = bot.reply_to(message, translate('flood_violation', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    # BLACKLIST
    if check_blacklist(chat_id, text):
        bot.delete_message(chat_id, message.message_id)
        log_activity(chat_id, user_id, 'blacklist_hit')
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_blocked', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    # TRIGGERS
    trigger = check_triggers(chat_id, text)
    if trigger:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, trigger)
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    # ORIGINAL LOCKS
    if message.entities and any(e.type == 'url' for e in message.entities):
        lock_links = safe_json(settings.get('moderation_lock_links', '{}'))
        if lock_links.get('status', 'off') == 'on':
            bot.delete_message(chat_id, message.message_id)
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('lock_set', chat_id, action='Links', status='enabled'))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
    
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
                'blacklist_remove': handle_blacklist_remove,
                'customcmd_create': handle_customcmd_create,
                'customcmd_edit': handle_customcmd_edit,
                'poll_new': handle_poll_new,
                'note_save': handle_note_save,
                'note_share': handle_note_share,
                'rss_add': handle_rss_add,
                'rss_edit': handle_rss_edit,
                'sub_grant': handle_sub_grant,
                'sub_edit': handle_sub_edit,
                'fed_link': handle_fed_link,
                'fed_sync': handle_fed_sync,
                'captcha_set': handle_captcha_set,
                'dump_set': handle_dump_set,
                'plugin_install': handle_plugin_install,
                'plugin_config': handle_plugin_config,
                'lang_set': handle_lang_set
            }
            if action in handlers:
                handlers[action](message)
                return

# HANDLERS
def handle_triggers_edit_delete(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    action = bot.temp_data[chat_id]['action']
    keyword = sanitize_input(message.text)
    
    if action == 'triggers_edit' and 'sub_action' not in bot.temp_data[chat_id]:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['keyword'] = keyword
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('trigger_updated', chat_id, keyword=keyword).replace("updated", "Send new response for"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    
    if action == 'triggers_edit' and bot.temp_data[chat_id].get('sub_action') == 'edit_response':
        new_response = sanitize_input(message.text)
        keyword = bot.temp_data[chat_id]['keyword']
        if len(new_response) > 1000:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_too_long', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("UPDATE triggers SET response=? WHERE chat_id=? AND keyword=?", 
                           (new_response, chat_id, keyword)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_updated', chat_id, keyword=keyword))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_not_found', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    
    elif action == 'triggers_delete':
        if safe_db_operation("DELETE FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, keyword)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_deleted', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_not_found', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_flood_enable(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    status = 'on' if message.text.lower() == 'on' else 'off'
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, 'flood', 'status', ?)", 
                       (chat_id, json.dumps({'status': status}))):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('flood_enabled', chat_id, status='enabled' if status == 'on' else 'disabled'))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('flood_enabled', chat_id, status='error'))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_broadcast_groups(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    groups = [g.strip() for g in message.text.split(',')]
    try:
        valid_groups = []
        for gid in groups:
            try:
                bot.get_chat(gid)
                valid_groups.append(gid)
            except:
                continue
        if not valid_groups:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, "❌ No valid group IDs provided!")
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        bot.temp_data[chat_id]['groups'] = valid_groups
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, f"👥 Selected {len(valid_groups)} groups. Send the broadcast message:")
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('broadcast_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_blacklist_remove(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    word = sanitize_input(message.text)
    if safe_db_operation("DELETE FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_removed', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_removed', chat_id).replace("removed", "error removing"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_customcmd_edit(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    if 'sub_action' in bot.temp_data[chat_id]:
        trigger = bot.temp_data[chat_id]['trigger']
        new_response = sanitize_input(message.text)
        if len(new_response) > 1000:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('command_too_long', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("UPDATE custom_commands SET response=? WHERE chat_id=? AND trigger=?", 
                           (new_response, chat_id, trigger)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('command_updated', chat_id, trigger=trigger))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('command_updated', chat_id, trigger='error'))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['trigger'] = sanitize_input(message.text.strip('/ '))
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, f"✏️ Send new response for /{message.text}:")
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_lang_set(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    lang = message.text.lower()
    if lang not in ['english', 'hindi']:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('lang_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    lang_code = 'en' if lang == 'english' else 'hi'
    if safe_db_operation("INSERT OR REPLACE INTO language_settings VALUES (?, ?)", (chat_id, lang_code)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('lang_set', chat_id, lang=lang))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('lang_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_triggers_add(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    data = bot.temp_data[chat_id]
    try:
        kw, resp = message.text.split('|', 1)
        kw = sanitize_input(kw.strip())
        resp = sanitize_input(resp.strip())
        if data['regex'] and not validate_regex(kw):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('invalid_regex', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if len(kw) > 100 or len(resp) > 1000:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_too_long', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("SELECT 1 FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, kw), "fetch"):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_exists', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT INTO triggers VALUES (?, ?, ?, ?)", (chat_id, kw, resp, data['regex'])):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_added', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('trigger_not_found', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError as e:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, f"❌ {str(e)}")
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_welcome_set(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    action = bot.temp_data[chat_id]['action']
    msg = sanitize_input(message.text)
    if len(msg) < 1:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('welcome_empty', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if safe_db_operation("INSERT OR REPLACE INTO welcome VALUES (?, ?, ?)", 
                       (chat_id, msg if 'welcome' in action else None, msg if 'leave' in action else None)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('welcome_set', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('welcome_set', chat_id).replace("set", "error setting"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_flood_set_limit(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        limit = parse_number(message.text)
        if limit < 1 or limit > 50:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('flood_invalid_limit', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT OR REPLACE INTO flood_settings VALUES (?, ?, ?)", (chat_id, limit, 'delete')):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('flood_limit_set', chat_id, limit=limit))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('flood_limit_set', chat_id).replace("set", "error setting"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('flood_invalid_number', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_broadcast_send(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    msg = sanitize_input(message.text)
    groups = bot.temp_data[chat_id].get('groups', [chat_id])
    if safe_db_operation("INSERT INTO broadcasts VALUES (?, ?, ?, ?)", (chat_id, msg, 0, json.dumps(groups))):
        for gid in groups:
            try:
                bot.send_message(gid, msg)
            except:
                continue
        safe_db_operation("UPDATE broadcasts SET sent=1 WHERE chat_id=? AND message=?", (chat_id, msg))
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('broadcast_sent', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('broadcast_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_blacklist_add(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    word = sanitize_input(message.text)
    regex = bot.temp_data[chat_id]['regex']
    
    if regex and not validate_regex(word):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('invalid_regex', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if len(word) > 100:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_too_long', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if safe_db_operation("SELECT 1 FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word), "fetch"):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_exists', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if safe_db_operation("INSERT INTO blacklists VALUES (?, ?, ?)", (chat_id, word, regex)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_added', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('blacklist_added', chat_id).replace("added", "error adding"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_grant_input(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        user_id, role = message.text.split()
        user_id = user_id.strip('@')
        role = role.upper()
        if role not in ['ADMIN', 'MOD']:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('role_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, user_id, role, json.dumps([]), '0')):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('role_granted', chat_id, role=role, user_name=user_id, user_id=user_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('role_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('role_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_customcmd_create(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        trigger, response = message.text.split('|', 1)
        trigger = sanitize_input(trigger.strip('/ '))
        response = sanitize_input(response.strip())
        if len(trigger) > 50 or len(response) > 1000:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('command_too_long', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
    if safe_db_operation("SELECT 1 FROM custom_commands WHERE chat_id=? AND trigger=?", (chat_id, trigger), "fetch"):
    delete_previous_reply(chat_id)
    sent_message = bot.reply_to(message, translate('command_exists', chat_id))
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
    if safe_db_operation("INSERT INTO custom_commands VALUES (?, ?, ?, ?, ?)", 
                    (chat_id, trigger, response, 'all', json.dumps([]))):
    del bot.temp_data[chat_id]
    delete_previous_reply(chat_id)
    sent_message = bot.reply_to(message, translate('command_added', chat_id))
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
    delete_previous_reply(chat_id)
    sent_message = bot.reply_to(message, translate('command_added', chat_id).replace("added", "error adding"))
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_poll_new(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        parts = message.text.split('|')
        question = sanitize_input(parts[0].strip())
        options = [sanitize_input(opt.strip()) for opt in parts[1].split(',')]
        anonymous = 1 if parts[2].strip().lower() == 'true' else 0
        timer = parse_time(parts[3].strip()) if len(parts) > 3 else 0
        if len(options) < 2 or len(question) > 255:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('poll_invalid', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        poll_id = str(random.randint(1000, 9999))
        if safe_db_operation("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (chat_id, poll_id, question, json.dumps(options), anonymous, timer, json.dumps({}))):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('poll_created', chat_id, poll_id=poll_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('poll_invalid', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('poll_invalid', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_note_save(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        tag, content = message.text.split('|', 1)
        tag = sanitize_input(tag.strip())
        content = sanitize_input(content.strip())
        expire = bot.temp_data[chat_id].get('expire', '0')
        if expire != '0' and not validate_time_format(expire):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('note_invalid_expire', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT INTO notes VALUES (?, ?, ?, ?)", 
                           (chat_id, tag, content, expire)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('note_saved', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('note_saved', chat_id).replace("saved", "error saving"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('note_saved', chat_id).replace("saved", "error saving"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_note_share(message):
    chat_id = str(message.chat.id)
    tag = sanitize_input(message.text)
    rows = safe_db_operation("SELECT content, expire FROM notes WHERE chat_id=? AND tag=?", 
                            (chat_id, tag), "fetch")
    if rows:
        content, expire = rows[0]
        if expire != '0':
            expire_time = datetime.strptime(expire, "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expire_time:
                safe_db_operation("DELETE FROM notes WHERE chat_id=? AND tag=?", (chat_id, tag))
                delete_previous_reply(chat_id)
                sent_message = bot.reply_to(message, "❌ Note expired!")
                bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
                return
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('note_shared', chat_id) + f"\n{content}")
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('note_shared', chat_id).replace("shared", "not found"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_rss_add(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        url, keywords, interval, fmt = message.text.split('|')
        url = url.strip()
        keywords = sanitize_input(keywords.strip())
        interval = interval.strip()
        fmt = sanitize_input(fmt.strip())
        if not validate_url(url):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_invalid_url', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if not validate_time_format(interval):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_invalid_interval', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT INTO rss_feeds VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, url, keywords, interval, fmt)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_added', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_added', chat_id).replace("added", "error adding"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('rss_added', chat_id).replace("added", "error adding"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_rss_edit(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        url, keywords, interval, fmt = message.text.split('|')
        url = url.strip()
        keywords = sanitize_input(keywords.strip())
        interval = interval.strip()
        fmt = sanitize_input(fmt.strip())
        if not validate_url(url):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_invalid_url', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if not validate_time_format(interval):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_invalid_interval', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("UPDATE rss_feeds SET keywords=?, interval=?, format=? WHERE chat_id=? AND url=?", 
                           (keywords, interval, fmt, chat_id, url)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_updated', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('rss_updated', chat_id).replace("updated", "error updating"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('rss_updated', chat_id).replace("updated", "error updating"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_sub_grant(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        user_id, plan, duration = message.text.split()
        user_id = user_id.strip('@')
        plan = sanitize_input(plan.strip())
        duration = duration.strip()
        if not validate_time_format(duration):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_invalid_duration', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT OR REPLACE INTO subscriptions VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, user_id, plan, duration, 1)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_granted', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_granted', chat_id).replace("granted", "error granting"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('sub_granted', chat_id).replace("granted", "error granting"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_sub_edit(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        user_id, plan, duration = message.text.split()
        user_id = user_id.strip('@')
        plan = sanitize_input(plan.strip())
        duration = duration.strip()
        if not validate_time_format(duration):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_invalid_duration', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("UPDATE subscriptions SET plan=?, duration=?, active=? WHERE chat_id=? AND user_id=?", 
                           (plan, duration, 1, chat_id, user_id)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_updated', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('sub_updated', chat_id).replace("updated", "error updating"))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('sub_updated', chat_id).replace("updated", "error updating"))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_fed_link(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    linked_group = message.text.strip()
    try:
        bot.get_chat(linked_group)
        if safe_db_operation("INSERT OR REPLACE INTO federations VALUES (?, ?, ?, ?)", 
                           (chat_id, linked_group, json.dumps([]), 0)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('fed_linked', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('fed_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('fed_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_fed_sync(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    actions = [act.strip() for act in message.text.split(',')]
    if safe_db_operation("UPDATE federations SET sync_actions=? WHERE chat_id=?", 
                       (json.dumps(actions), chat_id)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('fed_sync_set', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('fed_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_captcha_set(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        captcha_type, difficulty, time_limit, fail_action = message.text.split()
        captcha_type = sanitize_input(captcha_type.strip())
        difficulty = difficulty.strip().lower()
        time_limit = parse_time(time_limit.strip())
        fail_action = fail_action.strip().lower()
        if captcha_type not in ['math', 'text', 'image']:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if difficulty not in ['easy', 'medium', 'hard']:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_invalid_difficulty', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if not validate_time_format(time_limit):
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_invalid_time', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if fail_action not in ['kick', 'mute']:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_invalid_action', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
            return
        if safe_db_operation("INSERT OR REPLACE INTO captchas VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, captcha_type, difficulty, time_limit, fail_action)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_saved', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('captcha_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('captcha_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_dump_set(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    channel_id = message.text.strip()
    try:
        bot.get_chat(channel_id)
        if safe_db_operation("INSERT OR REPLACE INTO message_dump VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, "", "", "", channel_id)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('dump_channel_set', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('dump_invalid_channel', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('dump_invalid_channel', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_plugin_install(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    plugin_name = sanitize_input(message.text)
    if safe_db_operation("INSERT OR REPLACE INTO plugins VALUES (?, ?, ?, ?)", 
                       (chat_id, plugin_name, json.dumps({}), 1)):
        del bot.temp_data[chat_id]
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('plugin_installed', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('plugin_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def handle_plugin_config(message):
    chat_id = str(message.chat.id)
    if not is_creator_or_admin(bot, chat_id, message.from_user.id):
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('admin_only', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        return
    if chat_id not in bot.temp_data:
        return
    try:
        plugin_name, config = message.text.split('|', 1)
        plugin_name = sanitize_input(plugin_name.strip())
        config = json.dumps(json.loads(config.strip()))
        if safe_db_operation("UPDATE plugins SET config=? WHERE chat_id=? AND plugin_name=?", 
                           (config, chat_id, plugin_name)):
            del bot.temp_data[chat_id]
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('plugin_configured', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
        else:
            delete_previous_reply(chat_id)
            sent_message = bot.reply_to(message, translate('plugin_error', chat_id))
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    except ValueError:
        delete_previous_reply(chat_id)
        sent_message = bot.reply_to(message, translate('plugin_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# CALLBACK QUERY HANDLER
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = str(call.message.chat.id)
    data = call.data
    user_id = str(call.from_user.id)
    
    if not is_creator_or_admin(bot, chat_id, user_id) and data not in ['main', 'show_commands', 'help']:
        bot.answer_callback_query(call.id, translate('admin_only', chat_id))
        return
    
    delete_previous_reply(chat_id)
    
    handlers = {
        'main': lambda: show_main_menu(chat_id, call.message),
        'group_menu': lambda: show_group_menu(chat_id, call.message),
        'show_commands': lambda: show_commands(chat_id, call.message),
        'help': lambda: show_help(chat_id, call.message),
        'analytics_menu': lambda: show_analytics_menu(chat_id, call.message),
        'triggers_menu': lambda: show_triggers_menu(chat_id, call.message),
        'welcome_menu': lambda: show_welcome_menu(chat_id, call.message),
        'flood_menu': lambda: show_flood_menu(chat_id, call.message),
        'broadcast_menu': lambda: show_broadcast_menu(chat_id, call.message),
        'blacklist_menu': lambda: show_blacklist_menu(chat_id, call.message),
        'advanced_menu': lambda: show_advanced_menu(chat_id, call.message),
        'permissions_menu': lambda: show_permissions_menu(chat_id, call.message),
        'customcmd_menu': lambda: show_customcmd_menu(chat_id, call.message),
        'polls_menu': lambda: show_polls_menu(chat_id, call.message),
        'notes_menu': lambda: show_notes_menu(chat_id, call.message),
        'rss_menu': lambda: show_rss_menu(chat_id, call.message),
        'subs_menu': lambda: show_subs_menu(chat_id, call.message),
        'fed_menu': lambda: show_fed_menu(chat_id, call.message),
        'captcha_menu': lambda: show_captcha_menu(chat_id, call.message),
        'dump_menu': lambda: show_dump_menu(chat_id, call.message),
        'plugins_menu': lambda: show_plugins_menu(chat_id, call.message),
        'moderation_lock_menu': lambda: show_moderation_lock_menu(chat_id, call.message),
        'lang_menu': lambda: show_lang_menu(chat_id, call.message),
        'triggers_add': lambda: triggers_add(chat_id, call.message, False),
        'triggers_add_regex': lambda: triggers_add(chat_id, call.message, True),
        'triggers_list': lambda: triggers_list(chat_id, call.message),
        'triggers_edit': lambda: triggers_edit(chat_id, call.message),
        'triggers_delete': lambda: triggers_delete(chat_id, call.message),
        'welcome_set': lambda: welcome_set(chat_id, call.message, True),
        'welcome_set_leave': lambda: welcome_set(chat_id, call.message, False),
        'welcome_preview': lambda: welcome_preview(chat_id, call.message),
        'flood_enable': lambda: flood_enable(chat_id, call.message),
        'flood_set_limit': lambda: flood_set_limit(chat_id, call.message),
        'flood_stats': lambda: flood_stats(chat_id, call.message),
        'broadcast_send': lambda: broadcast_send(chat_id, call.message),
        'broadcast_groups': lambda: broadcast_groups(chat_id, call.message),
        'broadcast_preview': lambda: broadcast_preview(chat_id, call.message),
        'blacklist_add': lambda: blacklist_add(chat_id, call.message, False),
        'blacklist_add_regex': lambda: blacklist_add(chat_id, call.message, True),
        'blacklist_list': lambda: blacklist_list(chat_id, call.message),
        'blacklist_remove': lambda: blacklist_remove(chat_id, call.message),
        'grant_role': lambda: grant_role(chat_id, call.message),
        'list_roles': lambda: list_roles(chat_id, call.message),
        'set_commands': lambda: set_commands(chat_id, call.message),
        'set_duration': lambda: set_duration(chat_id, call.message),
        'customcmd_create': lambda: customcmd_create(chat_id, call.message),
        'customcmd_list': lambda: customcmd_list(chat_id, call.message),
        'customcmd_edit': lambda: customcmd_edit(chat_id, call.message),
        'poll_new': lambda: poll_new(chat_id, call.message),
        'poll_settings': lambda: poll_settings(chat_id, call.message),
        'poll_active': lambda: poll_active(chat_id, call.message),
        'note_save': lambda: note_save(chat_id, call.message),
        'note_search': lambda: note_search(chat_id, call.message),
        'note_share': lambda: note_share(chat_id, call.message),
        'rss_add': lambda: rss_add(chat_id, call.message),
        'rss_list': lambda: rss_list(chat_id, call.message),
        'rss_edit': lambda: rss_edit(chat_id, call.message),
        'sub_grant': lambda: sub_grant(chat_id, call.message),
        'sub_list': lambda: sub_list(chat_id, call.message),
        'sub_edit': lambda: sub_edit(chat_id, call.message),
        'fed_link': lambda: fed_link(chat_id, call.message),
        'fed_list': lambda: fed_list(chat_id, call.message),
        'fed_sync': lambda: fed_sync(chat_id, call.message),
        'captcha_set_type': lambda: captcha_set_type(chat_id, call.message),
        'captcha_difficulty': lambda: captcha_difficulty(chat_id, call.message),
        'captcha_time_limit': lambda: captcha_time_limit(chat_id, call.message),
        'captcha_fail_action': lambda: captcha_fail_action(chat_id, call.message),
        'dump_enable': lambda: dump_enable(chat_id, call.message),
        'dump_channel': lambda: dump_channel(chat_id, call.message),
        'dump_view': lambda: dump_view(chat_id, call.message),
        'plugin_install': lambda: plugin_install(chat_id, call.message),
        'plugin_list': lambda: plugin_list(chat_id, call.message),
        'plugin_config': lambda: plugin_config(chat_id, call.message),
        'lock_links': lambda: toggle_lock(chat_id, call.message, 'links'),
        'lock_media': lambda: toggle_lock(chat_id, call.message, 'media'),
        'lock_stickers': lambda: toggle_lock(chat_id, call.message, 'stickers'),
        'lock_forwards': lambda: toggle_lock(chat_id, call.message, 'forwards'),
        'lang_english': lambda: set_language(chat_id, call.message, 'english'),
        'lang_hindi': lambda: set_language(chat_id, call.message, 'hindi')
    }
    
    handler = handlers.get(data)
    if handler:
        handler()
    else:
        bot.answer_callback_query(call.id, "Invalid action!")

def show_main_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu'),
        types.InlineKeyboardButton(translate('lang_menu', chat_id).split('\n')[0], callback_data='lang_menu'),
        types.InlineKeyboardButton(translate('commands_list', chat_id).split('\n')[0], callback_data='show_commands')
    )
    sent_message = bot.send_message(chat_id, translate('main_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_group_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('moderation_lock_menu', chat_id).split('\n')[0], callback_data='moderation_lock_menu'),
        types.InlineKeyboardButton(translate('analytics_menu', chat_id).split('\n')[0], callback_data='analytics_menu'),
        types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[0], callback_data='triggers_menu'),
        types.InlineKeyboardButton(translate('welcome_menu', chat_id).split('\n')[0], callback_data='welcome_menu'),
        types.InlineKeyboardButton(translate('flood_menu', chat_id).split('\n')[0], callback_data='flood_menu'),
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[0], callback_data='broadcast_menu'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[0], callback_data='blacklist_menu'),
        types.InlineKeyboardButton(translate('advanced_menu', chat_id).split('\n')[0], callback_data='advanced_menu'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='main')
    )
    sent_message = bot.send_message(chat_id, translate('group_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_commands(chat_id, message):
    sent_message = bot.send_message(chat_id, translate('commands_list', chat_id))
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_help(chat_id, message):
    sent_message = bot.send_message(chat_id, "ℹ️ Help: Contact support or check documentation!")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_analytics_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Weekly", callback_data='analytics_week'),
        types.InlineKeyboardButton("📉 Monthly", callback_data='analytics_month'),
        types.InlineKeyboardButton("📤 Report", callback_data='analytics_report'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, get_analytics(chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_triggers_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[2], callback_data='triggers_add'),
        types.InlineKeyboardButton("➕ Regex", callback_data='triggers_add_regex'),
        types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[3], callback_data='triggers_list'),
        types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[4], callback_data='triggers_edit'),
        types.InlineKeyboardButton(translate('triggers_menu', chat_id).split('\n')[5], callback_data='triggers_delete'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('triggers_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_welcome_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('welcome_menu', chat_id).split('\n')[2], callback_data='welcome_set'),
        types.InlineKeyboardButton(translate('welcome_menu', chat_id).split('\n')[3], callback_data='welcome_preview'),
        types.InlineKeyboardButton(translate('welcome_menu', chat_id).split('\n')[4], callback_data='welcome_set_leave'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('welcome_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_flood_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('flood_menu', chat_id).split('\n')[2], callback_data='flood_enable'),
        types.InlineKeyboardButton(translate('flood_menu', chat_id).split('\n')[3], callback_data='flood_set_limit'),
        types.InlineKeyboardButton(translate('flood_menu', chat_id).split('\n')[4], callback_data='flood_stats'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('flood_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_broadcast_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[2], callback_data='broadcast_send'),
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[3], callback_data='broadcast_groups'),
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[4], callback_data='broadcast_preview'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('broadcast_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_blacklist_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[2], callback_data='blacklist_add'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[3], callback_data='blacklist_add_regex'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[4], callback_data='blacklist_list'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[5], callback_data='blacklist_remove'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('blacklist_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_advanced_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[0], callback_data='permissions_menu'),
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[0], callback_data='customcmd_menu'),
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[0], callback_data='polls_menu'),
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[0], callback_data='notes_menu'),
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[0], callback_data='rss_menu'),
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[0], callback_data='subs_menu'),
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[0], callback_data='fed_menu'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[0], callback_data='captcha_menu'),
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[0], callback_data='dump_menu'),
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[0], callback_data='plugins_menu'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('advanced_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_permissions_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[2], callback_data='grant_role'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[3], callback_data='list_roles'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[4], callback_data='set_commands'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[5], callback_data='set_duration'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('permissions_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_customcmd_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[2], callback_data='customcmd_create'),
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[3], callback_data='customcmd_list'),
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[4], callback_data='customcmd_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('customcmd_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_polls_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[2], callback_data='poll_new'),
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[3], callback_data='poll_settings'),
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[4], callback_data='poll_active'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('polls_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_notes_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[2], callback_data='note_save'),
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[3], callback_data='note_search'),
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[4], callback_data='note_share'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('notes_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_rss_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[2], callback_data='rss_add'),
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[3], callback_data='rss_list'),
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[4], callback_data='rss_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('rss_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_subs_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[2], callback_data='sub_grant'),
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[3], callback_data='sub_list'),
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[4], callback_data='sub_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('subs_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_fed_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[2], callback_data='fed_link'),
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[3], callback_data='fed_list'),
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[4], callback_data='fed_sync'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('fed_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_captcha_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[2], callback_data='captcha_set_type'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[3], callback_data='captcha_difficulty'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[4], callback_data='captcha_time_limit'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[5], callback_data='captcha_fail_action'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('captcha_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_dump_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[2], callback_data='dump_enable'),
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[3], callback_data='dump_channel'),
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[4], callback_data='dump_view'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('dump_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_plugins_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[2], callback_data='plugin_install'),
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[3], callback_data='plugin_list'),
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[4], callback_data='plugin_config'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='advanced_menu')
    )
    sent_message = bot.send_message(chat_id, translate('plugins_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_moderation_lock_menu(chat_id, message):
    settings = get_all_settings(chat_id)
    links_status = safe_json(settings.get('moderation_lock_links', '{}')).get('status', 'off')
    media_status = safe_json(settings.get('moderation_lock_media', '{}')).get('status', 'off')
    stickers_status = safe_json(settings.get('moderation_lock_stickers', '{}')).get('status', 'off')
    forwards_status = safe_json(settings.get('moderation_lock_forwards', '{}')).get('status', 'off')
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"🔗 Links: {'✅' if links_status == 'on' else '❌'}", callback_data='lock_links'),
        types.InlineKeyboardButton(f"📸 Media: {'✅' if media_status == 'on' else '❌'}", callback_data='lock_media'),
        types.InlineKeyboardButton(f"😀 Stickers: {'✅' if stickers_status == 'on' else '❌'}", callback_data='lock_stickers'),
        types.InlineKeyboardButton(f"📤 Forwards: {'✅' if forwards_status == 'on' else '❌'}", callback_data='lock_forwards'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    sent_message = bot.send_message(chat_id, translate('moderation_lock_menu', chat_id, 
                                                    links_status=links_status, 
                                                    media_status=media_status, 
                                                    stickers_status=stickers_status, 
                                                    forwards_status=forwards_status), 
                                  reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def show_lang_menu(chat_id, message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data='lang_english'),
        types.InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hindi'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='main')
    )
    sent_message = bot.send_message(chat_id, translate('lang_menu', chat_id), reply_markup=markup)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def triggers_add(chat_id, message, regex):
    bot.temp_data[chat_id] = {'action': 'triggers_add', 'regex': int(regex), 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, f"Send {'regex pattern' if regex else 'keyword'} and response (format: keyword|response)")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def triggers_list(chat_id, message):
    rows = safe_db_operation("SELECT keyword, response, regex FROM triggers WHERE chat_id=?", (chat_id,), "fetch")
    text = "🎯 Triggers:\n" + ("\n".join(f"{'[regex] ' if r[2] else ''}{r[0]}: {r[1]}" for r in rows) if rows else "No triggers!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def triggers_edit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'triggers_edit', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send keyword to edit:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def triggers_delete(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'triggers_delete', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send keyword to delete:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def welcome_set(chat_id, message, is_welcome):
    bot.temp_data[chat_id] = {'action': 'welcome_set_welcome' if is_welcome else 'welcome_set_leave', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, f"Send {'welcome' if is_welcome else 'leave'} message:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def welcome_preview(chat_id, message):
    welcome_msg = get_welcome(chat_id, True)
    leave_msg = get_welcome(chat_id, False)
    text = f"👋 Welcome: {welcome_msg}\n🚪 Leave: {leave_msg}"
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def flood_enable(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'flood_enable', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send 'on' or 'off':")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def flood_set_limit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'flood_set_limit', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send message limit per minute (1-50):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def flood_stats(chat_id, message):
    rows = safe_db_operation("SELECT user_id, COUNT(*) FROM analytics WHERE chat_id=? AND action LIKE 'flood_%' GROUP BY user_id", 
                            (chat_id,), "fetch")
    text = "🛡️ Flood Stats:\n" + ("\n".join(f"User {r[0]}: {r[1]} incidents" for r in rows) if rows else "No flood incidents!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def broadcast_send(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'broadcast_send', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send broadcast message:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def broadcast_groups(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'broadcast_groups', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send group IDs (comma-separated):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def broadcast_preview(chat_id, message):
    rows = safe_db_operation("SELECT message FROM broadcasts WHERE chat_id=? AND sent=0", (chat_id,), "fetch")
    text = "📢 Pending Broadcasts:\n" + ("\n".join(f"{r[0]}" for r in rows) if rows else "No pending broadcasts!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def blacklist_add(chat_id, message, regex):
    bot.temp_data[chat_id] = {'action': 'blacklist_add', 'regex': int(regex), 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, f"Send {'regex pattern' if regex else 'word'} to blacklist:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def blacklist_list(chat_id, message):
    rows = safe_db_operation("SELECT word, regex FROM blacklists WHERE chat_id=?", (chat_id,), "fetch")
    text = "🚫 Blacklist:\n" + ("\n".join(f"{'[regex] ' if r[1] else ''}{r[0]}" for r in rows) if rows else "No blacklist!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def blacklist_remove(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'blacklist_remove', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send word to remove from blacklist:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def grant_role(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'grant_role', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send user ID and role (format: @user role):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def list_roles(chat_id, message):
    rows = safe_db_operation("SELECT user_id, role, duration FROM permissions WHERE chat_id=?", (chat_id,), "fetch")
    text = "👑 Roles:\n" + ("\n".join(f"User {r[0]}: {r[1]} ({r[2]})" for r in rows) if rows else "No roles assigned!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def set_commands(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'set_commands', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send user ID and commands (format: @user cmd1,cmd2):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def set_duration(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'set_duration', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send user ID and duration (format: @user 1d):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def customcmd_create(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'customcmd_create', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send command and response (format: /cmd|response):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def customcmd_list(chat_id, message):
    rows = safe_db_operation("SELECT trigger, response FROM custom_commands WHERE chat_id=?", (chat_id,), "fetch")
    text = "⚙️ Custom Commands:\n" + ("\n".join(f"/{r[0]}: {r[1]}" for r in rows) if rows else "No custom commands!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def customcmd_edit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'customcmd_edit', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send command to edit (format: /cmd):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def poll_new(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'poll_new', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send poll details (format: question|option1,option2|anonymous|timer):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def poll_settings(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'poll_settings', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send poll ID and settings (format: poll_id|anonymous|timer):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def poll_active(chat_id, message):
    rows = safe_db_operation("SELECT poll_id, question FROM polls WHERE chat_id=?", (chat_id,), "fetch")
    text = "📊 Active Polls:\n" + ("\n".join(f"ID {r[0]}: {r[1]}" for r in rows) if rows else "No active polls!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def note_save(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'note_save', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send note tag and content (format: tag|content):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def note_search(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'note_search', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send tag to search:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def note_share(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'note_share', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send tag to share:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def rss_add(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'rss_add', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send RSS details (format: url|keywords|interval|format):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def rss_list(chat_id, message):
    rows = safe_db_operation("SELECT url, keywords, interval FROM rss_feeds WHERE chat_id=?", (chat_id,), "fetch")
    text = "📰 RSS Feeds:\n" + ("\n".join(f"URL: {r[0]}, Keywords: {r[1]}, Interval: {r[2]}" for r in rows) if rows else "No RSS feeds!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def rss_edit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'rss_edit', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send RSS details to edit (format: url|keywords|interval|format):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def sub_grant(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'sub_grant', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send user ID, plan, and duration (format: @user plan duration):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def sub_list(chat_id, message):
    rows = safe_db_operation("SELECT user_id, plan, duration FROM subscriptions WHERE chat_id=?", (chat_id,), "fetch")
    text = "💰 Subscriptions:\n" + ("\n".join(f"User {r[0]}: {r[1]} ({r[2]})" for r in rows) if rows else "No subscriptions!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def sub_edit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'sub_edit', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send user ID, plan, and duration (format: @user plan duration):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def fed_link(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'fed_link', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send group ID to link:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def fed_list(chat_id, message):
    rows = safe_db_operation("SELECT linked_group, sync_actions FROM federations WHERE chat_id=?", (chat_id,), "fetch")
    text = "🔗 Federated Groups:\n" + ("\n".join(f"Group {r[0]}: {r[1]}" for r in rows) if rows else "No federated groups!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def fed_sync(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'fed_sync', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send actions to sync (comma-separated):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def captcha_set_type(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'captcha_set', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send captcha type, difficulty, time limit, and fail action (format: type difficulty time action):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def captcha_difficulty(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'captcha_set', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send captcha type, difficulty, time limit, and fail action (format: type difficulty time action):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def captcha_time_limit(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'captcha_set', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send captcha type, difficulty, time limit, and fail action (format: type difficulty time action):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def captcha_fail_action(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'captcha_set', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send captcha type, difficulty, time limit, and fail action (format: type difficulty time action):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def dump_enable(chat_id, message):
    settings = get_all_settings(chat_id)
    current_status = safe_json(settings.get('message_dump', '{}')).get('status', 'off')
    new_status = 'off' if current_status == 'on' else 'on'
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, ?, ?, ?)", 
                       (chat_id, 'message_dump', 'status', json.dumps({'status': new_status}))):
        sent_message = bot.send_message(chat_id, translate('dump_enabled', chat_id, status=new_status))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        sent_message = bot.send_message(chat_id, translate('dump_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def dump_channel(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'dump_set', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send channel ID for message dump:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def dump_view(chat_id, message):
    rows = safe_db_operation("SELECT deleted_msg, user_id, timestamp FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
    text = "💾 Deleted Messages:\n" + ("\n".join(f"User {r[1]} at {r[2]}: {r[0]}" for r in rows) if rows else "No deleted messages!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def plugin_install(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'plugin_install', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send plugin name to install:")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def plugin_list(chat_id, message):
    rows = safe_db_operation("SELECT plugin_name, config, active FROM plugins WHERE chat_id=?", (chat_id,), "fetch")
    text = "🔌 Plugins:\n" + ("\n".join(f"{r[0]}: {'Active' if r[2] else 'Inactive'} ({r[1]})" for r in rows) if rows else "No plugins!")
    sent_message = bot.send_message(chat_id, text)
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def plugin_config(chat_id, message):
    bot.temp_data[chat_id] = {'action': 'plugin_config', 'timeout': time.time() + 300}
    sent_message = bot.send_message(chat_id, "Send plugin name and config (format: name|config):")
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def toggle_lock(chat_id, message, action):
    settings = get_all_settings(chat_id)
    key = f"moderation_lock_{action}"
    current_status = safe_json(settings.get(key, '{}')).get('status', 'off')
    new_status = 'off' if current_status == 'on' else 'on'
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, ?, ?, ?)", 
                       (chat_id, 'moderation', f"lock_{action}", json.dumps({'status': new_status}))):
        sent_message = bot.send_message(chat_id, translate('lock_set', chat_id, action=action.capitalize(), status=new_status))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        sent_message = bot.send_message(chat_id, translate('lock_error', chat_id, action=action.capitalize()))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

def set_language(chat_id, message, lang):
    lang_code = 'en' if lang == 'english' else 'hi'
    if safe_db_operation("INSERT OR REPLACE INTO language_settings VALUES (?, ?)", (chat_id, lang_code)):
        sent_message = bot.send_message(chat_id, translate('lang_set', chat_id, lang=lang))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        sent_message = bot.send_message(chat_id, translate('lang_error', chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# NEW CHAT MEMBERS
@bot.message_handler(content_types=['new_chat_members'])
def new_member(message):
    chat_id = str(message.chat.id)
    settings = get_all_settings(chat_id)
    captcha_settings = safe_json(settings.get('moderation_captcha', '{}'))
    
    if captcha_settings.get('status', 'off') == 'on':
        for user in message.new_chat_members:
            captcha = generate_captcha()
            markup = types.InlineKeyboardMarkup(row_width=2)
            for opt in captcha['options']:
                markup.add(types.InlineKeyboardButton(opt, callback_data=f"captcha_{user.id}_{opt}"))
            bot.temp_data[f"captcha_{chat_id}_{user.id}"] = {
                'answer': captcha['answer'],
                'timeout': time.time() + captcha_settings.get('time_limit', 300),
                'fail_action': captcha_settings.get('fail_action', 'kick')
            }
            sent_message = bot.send_message(chat_id, f"Welcome {user.first_name}! Solve this captcha: {captcha['question']}", reply_markup=markup)
            bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id
    else:
        sent_message = bot.send_message(chat_id, get_welcome(chat_id))
        bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# LEFT CHAT MEMBER
@bot.message_handler(content_types=['left_chat_member'])
def left_member(message):
    chat_id = str(message.chat.id)
    sent_message = bot.send_message(chat_id, get_welcome(chat_id, False))
    bot.temp_data[f"last_reply_{chat_id}"] = sent_message.message_id

# CAPTCHA CALLBACK
@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_callback(call):
    chat_id = str(call.message.chat.id)
    user_id, answer = call.data.split('_')[1:]
    captcha_key = f"captcha_{chat_id}_{user_id}"
    
    if captcha_key not in bot.temp_data:
        bot.answer_callback_query(call.id, "Captcha expired!")
        return
    
    captcha = bot.temp_data[captcha_key]
    if time.time() > captcha['timeout']:
        bot.answer_callback_query(call.id, translate('captcha_timeout', chat_id))
        if captcha['fail_action'] == 'kick':
            bot.kick_chat_member(chat_id, user_id)
        else:
            bot.restrict_chat_member(chat_id, user_id, permissions={'can_send_messages': False})
        del bot.temp_data[captcha_key]
        return
    
    if answer == captcha['answer']:
        bot.answer_callback_query(call.id, translate('captcha_verified', chat_id))
        bot.delete_message(chat_id, call.message.message_id)
        del bot.temp_data[captcha_key]
    else:
        bot.answer_callback_query(call.id, translate('captcha_wrong', chat_id))

# RUN BOT
if __name__ == '__main__':
    try:
        logging.info("Bot starting...")
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logging.error(f"Infinity polling exception: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=10, long_polling_timeout=5)