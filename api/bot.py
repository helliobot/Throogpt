from flask import Flask, request
from libsql import connect  # Turso SQLite के लिए
import telebot, os, json, time, random, re
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
    filename='/tmp/bot.log',  # Vercel में राइटेबल /tmp डायरेक्टरी
    format='%(asctime)s %(levelname)s: %(message)s'
)

# Load environment variables
load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

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
        'rss_added': "✅ RSS added!",
        'rss_invalid_url': "❌ Invalid URL!",
        'rss_invalid_interval': "❌ Invalid interval format (e.g., 1h)!",
        'sub_granted': "✅ Subscription granted!",
        'sub_invalid_duration': "❌ Invalid duration format (e.g., 1m)!",
        'fed_linked': "✅ Group linked!",
        'fed_error': "❌ Error linking group!",
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
        'lock_set': "✅ {action} lock {status}!",
        'lock_error': "❌ Error setting {action} lock!",
        'invalid_input': "❌ Invalid input! Use 'on' or 'off'.",
        'lang_set': "✅ Language set to {lang}!",
        'lang_error': "❌ Invalid language! Use 'english' or 'hindi'.",
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
        'rss_added': "✅ RSS जोड़ा गया!",
        'rss_invalid_url': "❌ अमान्य URL!",
        'rss_invalid_interval': "❌ अमान्य अंतराल प्रारूप (उदा., 1h)!",
        'sub_granted': "✅ सदस्यता प्रदान की गई!",
        'sub_invalid_duration': "❌ अमान्य अवधि प्रारूप (उदा., 1m)!",
        'fed_linked': "✅ समूह लिंक किया गया!",
        'fed_error': "❌ समूह लिंक करने में त्रुटि!",
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
        'lock_set': "✅ {action} लॉक {status}!",
        'lock_error': "❌ {action} लॉक सेट करने में त्रुटि!",
        'invalid_input': "❌ अमान्य इनपुट! 'on' या 'off' का उपयोग करें।",
        'lang_set': "✅ भाषा {lang} पर सेट की गई!",
        'lang_error': "❌ अमान्य भाषा! 'english' या 'hindi' का उपयोग करें।",
    }
}

# DATABASE SETUP (ALL TABLES WITH INDEXES)
def init_db():
    try:
        conn = connect(os.getenv('TURSO_DATABASE_URL'), auth_token=os.getenv('TURSO_AUTH_TOKEN'))
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
                     (chat_id TEXT, message TEXT, sent INTEGER)''')
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
                     (chat_id TEXT, language TEXT)''')  # New table for language settings
        
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
def get_language(chat_id):
    """Get the language for a chat, default to English."""
    try:
        conn = connect(os.getenv('TURSO_DATABASE_URL'), auth_token=os.getenv('TURSO_AUTH_TOKEN'))
        c = conn.cursor()
        c.execute("SELECT language FROM language_settings WHERE chat_id=?", (chat_id,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 'en'
    except Exception as e:
        logging.error(f"Error getting language: {e}")
        return 'en'

def translate(key, chat_id, **kwargs):
    """Translate a message based on chat language."""
    lang = get_language(chat_id)
    text = translations.get(lang, translations['en']).get(key, translations['en'][key])
    return text.format(**kwargs)

def sanitize_input(text):
    """Sanitize input to prevent SQL injection and Telegram formatting issues."""
    if not text:
        raise ValueError("Input cannot be empty")
    text = html.escape(text.strip())  # Escape HTML characters
    if len(text) > 4096:  # Telegram message limit
        raise ValueError("Input too long (max 4096 characters)")
    return text

def validate_url(url):
    """Validate URL format."""
    url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
    return bool(url_pattern.match(url))

def validate_time_format(time_str):
    """Validate time format (e.g., 1d, 2h, 30m)."""
    time_pattern = re.compile(r'^\d+[smhd]$')
    return bool(time_pattern.match(time_str))

def validate_regex(regex_str):
    """Validate regex pattern."""
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
    """Check if user is creator or has admin/mod role."""
    if str(chat_id).startswith('-'):
        try:
            status = bot.get_chat_member(chat_id, user_id).status
            if status == 'creator':
                return True
            conn = connect(os.getenv('TURSO_DATABASE_URL'), auth_token=os.getenv('TURSO_AUTH_TOKEN'))
            c = conn.cursor()
            c.execute("SELECT role FROM permissions WHERE chat_id=? AND user_id=?", (chat_id, str(user_id)))
            role = c.fetchone()
            conn.close()
            return role and role[0] in ['ADMIN', 'MOD']
        except:
            return False
    return True

def safe_db_operation(query, params, operation="execute"):
    """Safely execute database operations with error handling."""
    try:
        conn = connect(os.getenv('TURSO_DATABASE_URL'), auth_token=os.getenv('TURSO_AUTH_TOKEN'))
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
    rows = safe_db_operation("SELECT feature, subfeature, data FROM settings WHERE chat_id=?", (chat_id,), "fetch")
    if rows:
        settings = {f"{r[0]}_{r[1]}": json.loads(r[2]) for r in rows}
    MENU_CACHE[chat_id] = settings
    return settings

def safe_json(data): 
    return json.loads(data) if data else {'status': 'off'}

def cleanup_temp_data():
    """Remove expired temp_data entries."""
    now = time.time()
    for key in list(bot.temp_data.keys()):
        if 'timeout' in bot.temp_data[key] and now > bot.temp_data[key]['timeout']:
            del bot.temp_data[key]

# Run cleanup periodically
Thread(target=lambda: [cleanup_temp_data() or time.sleep(60) for _ in iter(int, 1)], daemon=True).start()

# FLOOD PROTECTION
def check_flood(chat_id, user_id):
    """Check and handle flood control based on flood_settings."""
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
    """Generate a simple math captcha."""
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
    
    # Auto-delete after 2s
    time.sleep(2)
    try:
        bot.delete_message(chat_id, sent_message.message_id)
    except:
        pass

# STATUS COMMAND
@bot.message_handler(commands=['status'])
def status_command(message):
    chat_id = str(message.chat.id)
    if message.chat.type == 'private' or not is_creator_or_admin(bot, chat_id, message.from_user.id):
        return bot.reply_to(message, translate('admin_only', chat_id))
    
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
        status = safe_json(settings.get(key, '{}'))['status']
        status_text += f"{name}: {'✅' if status == 'on' else '❌'}\n"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu'),
        types.InlineKeyboardButton(translate('commands_list', chat_id).split('\n')[0], callback_data='show_commands')
    )
    bot.reply_to(message, status_text, reply_markup=markup)

# LANGUAGE COMMAND
@bot.message_handler(commands=['lang'])
def lang_command(message):
    chat_id = str(message.chat.id)
    bot.temp_data[chat_id] = {'action': 'lang_set', 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data='lang_english'),
        types.InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hindi'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='main')
    )
    bot.reply_to(message, translate('lang_menu', chat_id), reply_markup=markup)

# CONTENT HANDLER
@bot.message_handler(content_types=['text'])
def content_handler(message):
    chat_id = str(message.chat.id)
    text = sanitize_input(message.text)
    user_id = str(message.from_user.id)
    log_activity(chat_id, user_id, 'message', {'text': text})
    
    # Save message to dump if enabled
    settings = get_all_settings(chat_id)
    if safe_json(settings.get('message_dump', '{}'))['status'] == 'on':
        rows = safe_db_operation("SELECT dump_channel FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
        if rows:
            safe_db_operation("INSERT INTO message_dump VALUES (?, ?, ?, ?, ?)", 
                            (chat_id, text, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rows[0][0]))
    
    # ANTI-FLOOD
    flood_action = check_flood(chat_id, user_id)
    if flood_action:
        bot.delete_message(chat_id, message.message_id)
        if flood_action == 'mute':
            bot.restrict_chat_member(chat_id, user_id, permissions={'can_send_messages': False})
            bot.reply_to(message, translate('flood_mute', chat_id))
        elif flood_action == 'ban':
            bot.kick_chat_member(chat_id, user_id)
            bot.reply_to(message, translate('flood_ban', chat_id))
        else:
            bot.reply_to(message, translate('flood_violation', chat_id))
        return
    
    # BLACKLIST
    if check_blacklist(chat_id, text):
        bot.delete_message(chat_id, message.message_id)
        log_activity(chat_id, user_id, 'blacklist_hit')
        return bot.reply_to(message, translate('blacklist_blocked', chat_id))
    
    # TRIGGERS
    trigger = check_triggers(chat_id, text)
    if trigger:
        return bot.reply_to(message, trigger)
    
    # ORIGINAL LOCKS
    if message.entities and any(e.type == 'url' for e in message.entities) and safe_json(settings.get('moderation_lock_links', '{}'))['status'] == 'on':
        bot.delete_message(chat_id, message.message_id)
        return bot.reply_to(message, translate('lock_set', chat_id, action='Links', status='enabled'))
    
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
                'customcmd_create': handle_customcmd_create,
                'customcmd_edit': handle_customcmd_edit,
                'poll_new': handle_poll_new,
                'note_save': handle_note_save,
                'rss_add': handle_rss_add,
                'sub_grant': handle_sub_grant,
                'fed_link': handle_fed_link,
                'captcha_set': handle_captcha_set,
                'dump_set': handle_dump_set,
                'plugin_install': handle_plugin_install,
                'lang_set': handle_lang_set
            }
            if action in handlers:
                handlers[action](message)
                return

# HANDLERS
def handle_triggers_edit_delete(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    action = bot.temp_data[chat_id]['action']
    keyword = sanitize_input(message.text)
    
    if action == 'triggers_edit' and 'sub_action' not in bot.temp_data[chat_id]:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['keyword'] = keyword
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        bot.reply_to(message, translate('trigger_updated', chat_id, keyword=keyword).replace("updated", "Send new response for"))
        return
    
    if action == 'triggers_edit' and bot.temp_data[chat_id].get('sub_action') == 'edit_response':
        new_response = sanitize_input(message.text)
        keyword = bot.temp_data[chat_id]['keyword']
        if len(new_response) > 1000:
            return bot.reply_to(message, translate('trigger_too_long', chat_id))
        if safe_db_operation("UPDATE triggers SET response=? WHERE chat_id=? AND keyword=?", 
                           (new_response, chat_id, keyword)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('trigger_updated', chat_id, keyword=keyword))
        else:
            bot.reply_to(message, translate('trigger_not_found', chat_id))
    
    elif action == 'triggers_delete':
        if safe_db_operation("DELETE FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, keyword)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('trigger_deleted', chat_id))
        else:
            bot.reply_to(message, translate('trigger_not_found', chat_id))

def handle_flood_enable(message):
    chat_id = str(message.chat.id)
    status = 'on' if message.text.lower() == 'on' else 'off'
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, 'flood', 'status', ?)", 
                       (chat_id, json.dumps({'status': status}))):
        bot.reply_to(message, translate('flood_enabled', chat_id, status='enabled' if status == 'on' else 'disabled'))
    else:
        bot.reply_to(message, translate('flood_enabled', chat_id, status='error'))

def handle_broadcast_groups(message):
    chat_id = str(message.chat.id)
    bot.reply_to(message, "👥 All groups selected!")  # Placeholder

def handle_customcmd_edit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    if 'sub_action' in bot.temp_data[chat_id]:
        trigger = bot.temp_data[chat_id]['trigger']
        new_response = sanitize_input(message.text)
        if len(new_response) > 1000:
            return bot.reply_to(message, translate('command_too_long', chat_id))
        if safe_db_operation("UPDATE custom_commands SET response=? WHERE chat_id=? AND trigger=?", 
                           (new_response, chat_id, trigger)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('command_updated', chat_id, trigger=trigger))
        else:
            bot.reply_to(message, translate('command_updated', chat_id, trigger='error'))
    else:
        bot.temp_data[chat_id]['sub_action'] = 'edit_response'
        bot.temp_data[chat_id]['trigger'] = sanitize_input(message.text.strip('/ '))
        bot.temp_data[chat_id]['timeout'] = time.time() + 300
        bot.reply_to(message, f"✏️ Send new response for /{message.text}:")

def handle_lang_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    lang = message.text.lower()
    if lang not in ['english', 'hindi']:
        return bot.reply_to(message, translate('lang_error', chat_id))
    lang_code = 'en' if lang == 'english' else 'hi'
    if safe_db_operation("INSERT OR REPLACE INTO language_settings VALUES (?, ?)", (chat_id, lang_code)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('lang_set', chat_id, lang=lang))
    else:
        bot.reply_to(message, translate('lang_error', chat_id))

# NEW MEMBER
@bot.message_handler(content_types=['new_chat_members'])
def new_member_welcome(message):
    chat_id = str(message.chat.id)
    for user in message.new_chat_members:
        welcome = get_welcome(chat_id)
        bot.send_message(chat_id, f"{welcome} @{user.username or user.first_name}!")
        log_activity(chat_id, user.id, 'join')
        
        # CAPTCHA
        settings = get_all_settings(chat_id)
        if safe_json(settings.get('moderation_captcha', '{}'))['status'] == 'on':
            captcha = generate_captcha()
            bot.temp_data[f"{chat_id}_{user.id}"] = {'action': 'captcha_verify', 'answer': captcha['answer'], 'timeout': time.time() + 300}
            markup = types.InlineKeyboardMarkup(row_width=2)
            for i in range(0, len(captcha['options']), 2):
                markup.add(
                    types.InlineKeyboardButton(captcha['options'][i], callback_data=f"captcha_{captcha['options'][i]}_{user.id}"),
                    types.InlineKeyboardButton(captcha['options'][i+1], callback_data=f"captcha_{captcha['options'][i+1]}_{user.id}") if i+1 < len(captcha['options']) else types.InlineKeyboardButton(" ", callback_data="noop")
                )
            bot.send_message(chat_id, f"🛡️ @{user.username or user.first_name}, solve: {captcha['question']} (5 min)", reply_markup=markup)

# CAPTCHA VERIFICATION
@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_verify(call):
    chat_id = str(call.message.chat.id)
    _, answer, user_id = call.data.split('_')
    key = f"{chat_id}_{user_id}"
    if key not in bot.temp_data:
        bot.answer_callback_query(call.id, translate('captcha_expired', chat_id))
        return
    data = bot.temp_data[key]
    if time.time() > data['timeout']:
        bot.answer_callback_query(call.id, translate('captcha_timeout', chat_id))
        bot.kick_chat_member(chat_id, user_id)
        del bot.temp_data[key]
        return
    if answer == data['answer']:
        bot.answer_callback_query(call.id, translate('captcha_verified', chat_id))
        bot.delete_message(chat_id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, translate('captcha_wrong', chat_id))
        bot.kick_chat_member(chat_id, user_id)
    del bot.temp_data[key]

# LEFT MEMBER
@bot.message_handler(content_types=['left_chat_member'])
def left_member(message):
    chat_id = str(message.chat.id)
    user = message.left_chat_member
    leave = get_welcome(chat_id, False)
    bot.send_message(chat_id, f"{leave} @{user.username or user.first_name}")
    log_activity(chat_id, user.id, 'leave')

# SETTINGS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'main')
def settings_menu(call):
    bot.answer_callback_query(call.id, "⚙️ Loading...", show_alert=False)
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("🛡️ Verify", 'verify'), (translate('welcome_menu', chat_id).split('\n')[0], 'welcome_menu'),
        (translate('triggers_menu', chat_id).split('\n')[0], 'triggers_menu'), ("⏰ Schedule", 'scheduled'),
        (translate('group_menu', chat_id).split('\n')[0], 'group_menu'), ("🧹 Clean", 'autoclean'),
        ("🚫 Block", 'block'), (translate('lang_menu', chat_id).split('\n')[0], 'lang_menu'),
        (translate('advanced_menu', chat_id).split('\n')[0], 'advanced_menu'), (translate('commands_list', chat_id).split('\n')[0], 'show_commands')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(translate('main_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

# LANGUAGE MENU
@bot.callback_query_handler(func=lambda call: call.data == 'lang_menu')
def lang_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇬🇧 English", callback_data='lang_english'),
        types.InlineKeyboardButton("🇮🇳 Hindi", callback_data='lang_hindi'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='main')
    )
    
    bot.edit_message_text(translate('lang_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def lang_action(call):
    chat_id = str(call.message.chat.id)
    lang = call.data.split('_')[1]
    lang_code = 'en' if lang == 'english' else 'hi'
    
    if safe_db_operation("INSERT OR REPLACE INTO language_settings VALUES (?, ?)", (chat_id, lang_code)):
        bot.edit_message_text(translate('lang_set', chat_id, lang=lang), chat_id, call.message.message_id)
    else:
        bot.edit_message_text(translate('lang_error', chat_id), chat_id, call.message.message_id)

# GROUP MENU
@bot.callback_query_handler(func=lambda call: call.data == 'group_menu')
def group_menu(call):
    if not is_creator_or_admin(bot, str(call.message.chat.id), call.from_user.id):
        return bot.edit_message_text(translate('admin_only', call.message.chat.id), call.message.chat.id, call.message.message_id)
    
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        (translate('moderation_lock_menu', chat_id).split('\n')[0], 'moderation_lock'), (translate('captcha_menu', chat_id).split('\n')[0], 'moderation_captcha'),
        (translate('analytics_menu', chat_id).split('\n')[0], 'analytics_menu'), (translate('triggers_menu', chat_id).split('\n')[0], 'triggers_menu'),
        (translate('welcome_menu', chat_id).split('\n')[0], 'welcome_menu'), (translate('flood_menu', chat_id).split('\n')[0], 'flood_menu'),
        (translate('broadcast_menu', chat_id).split('\n')[0], 'broadcast_menu'), (translate('blacklist_menu', chat_id).split('\n')[0], 'blacklist_menu'),
        (translate('permissions_menu', chat_id).split('\n')[0], 'permissions_menu'), (translate('customcmd_menu', chat_id).split('\n')[0], 'customcmd_menu'),
        (translate('polls_menu', chat_id).split('\n')[0], 'polls_menu'), (translate('notes_menu', chat_id).split('\n')[0], 'notes_menu'),
        (translate('rss_menu', chat_id).split('\n')[0], 'rss_menu'), (translate('subs_menu', chat_id).split('\n')[0], 'subs_menu'),
        (translate('fed_menu', chat_id).split('\n')[0], 'fed_menu'), (translate('captcha_menu', chat_id).split('\n')[0], 'captcha_menu'),
        (translate('dump_menu', chat_id).split('\n')[0], 'dump_menu'), (translate('plugins_menu', chat_id).split('\n')[0], 'plugins_menu')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(translate('group_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

# ANALYTICS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'analytics_menu')
def analytics_menu(call):
    bot.answer_callback_query(call.id, "📊 Loading...")
    chat_id = str(call.message.chat.id)
    stats = get_analytics(chat_id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Weekly", callback_data='analytics_week'),
        types.InlineKeyboardButton("📉 Monthly", callback_data='analytics_month'),
        types.InlineKeyboardButton("📤 Report", callback_data='analytics_report'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(stats, chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('analytics_'))
def analytics_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'week':
        stats = get_analytics(chat_id, 'week')
    elif action == 'month':
        stats = get_analytics(chat_id, 'month')
    elif action == 'report':
        stats = "📤 Report sent to logs (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📈 Weekly", callback_data='analytics_week'),
        types.InlineKeyboardButton("📉 Monthly", callback_data='analytics_month'),
        types.InlineKeyboardButton("📤 Report", callback_data='analytics_report'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='analytics_menu')
    )
    bot.edit_message_text(stats, chat_id, call.message.message_id, reply_markup=markup)

# TRIGGERS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'triggers_menu')
def triggers_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add", callback_data='triggers_add'),
        types.InlineKeyboardButton("📝 List", callback_data='triggers_list'),
        types.InlineKeyboardButton("✏️ Edit", callback_data='triggers_edit'),
        types.InlineKeyboardButton("🗑️ Delete", callback_data='triggers_delete'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu'),
        types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
    )
    
    bot.edit_message_text(translate('triggers_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('triggers_'))
def triggers_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'add':
        text = translate('triggers_menu', chat_id).split('\n')[0] + "\n\n" \
               "📝 Keyword: Simple word match\n" \
               "⚡ Regex: Advanced pattern"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📝 Keyword", callback_data='triggers_add_keyword'),
            types.InlineKeyboardButton("⚡ Regex", callback_data='triggers_add_regex'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu'),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action in ['add_keyword', 'add_regex']:
        bot.temp_data[chat_id] = {'action': 'triggers_add', 'regex': 1 if 'regex' in action else 0, 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='triggers_menu'),
            types.InlineKeyboardButton("ℹ️ Help", callback_data='triggers_help')
        )
        bot.edit_message_text("Send: keyword|response\nE.g., hello|Hi there!", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        triggers = safe_db_operation("SELECT keyword, response FROM triggers WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('triggers_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {kw}: {resp}" for kw, resp in triggers) or "No triggers."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➕ Add", callback_data='triggers_add'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'edit' or action == 'delete':
        bot.temp_data[chat_id] = {'action': f'triggers_{action}', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='triggers_menu'),
            types.InlineKeyboardButton("📝 List", callback_data='triggers_list')
        )
        bot.edit_message_text(f"Send keyword to {action}:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'help':
        text = translate('triggers_menu', chat_id).split('\n')[0] + " Help:\n\n- Add: Create keyword or regex triggers\n- Edit/Delete: Modify or remove\n- Format: keyword|response"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='triggers_menu'),
            types.InlineKeyboardButton("➕ Add", callback_data='triggers_add')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_triggers_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    data = bot.temp_data[chat_id]
    try:
        kw, resp = message.text.split('|', 1)
        kw = sanitize_input(kw.strip())
        resp = sanitize_input(resp.strip())
        if data['regex'] and not validate_regex(kw):
            return bot.reply_to(message, translate('invalid_regex', chat_id))
        if len(kw) > 100 or len(resp) > 1000:
            return bot.reply_to(message, translate('trigger_too_long', chat_id))
        if safe_db_operation("SELECT 1 FROM triggers WHERE chat_id=? AND keyword=?", (chat_id, kw), "fetch"):
            return bot.reply_to(message, translate('trigger_exists', chat_id))
        if safe_db_operation("INSERT INTO triggers VALUES (?, ?, ?, ?)", (chat_id, kw, resp, data['regex'])):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('trigger_added', chat_id))
        else:
            bot.reply_to(message, translate('trigger_not_found', chat_id))
    except ValueError as e:
        bot.reply_to(message, f"❌ {str(e)}")

# WELCOME MENU
@bot.callback_query_handler(func=lambda call: call.data == 'welcome_menu')
def welcome_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👋 Set Welcome", callback_data='welcome_set'),
        types.InlineKeyboardButton("👋 Preview", callback_data='welcome_preview'),
        types.InlineKeyboardButton("🚪 Set Leave", callback_data='leave_set'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('welcome_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['welcome_set', 'leave_set'])
def welcome_action(call):
    action = call.data
    chat_id = str(call.message.chat.id)
    bot.temp_data[chat_id] = {'action': action, 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Cancel", callback_data='welcome_menu'),
        types.InlineKeyboardButton("👋 Preview", callback_data='welcome_preview')
    )
    bot.edit_message_text(f"Send new {'welcome' if 'welcome' in action else 'leave'} message:", chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'welcome_preview')
def welcome_preview(call):
    chat_id = str(call.message.chat.id)
    welcome, leave = get_welcome(chat_id), get_welcome(chat_id, False)
    text = f"👋 Welcome: {welcome}\n🚪 Leave: {leave}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("👋 Set Welcome", callback_data='welcome_set'),
        types.InlineKeyboardButton("🚪 Set Leave", callback_data='leave_set')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_welcome_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    action = bot.temp_data[chat_id]['action']
    msg = sanitize_input(message.text)
    if len(msg) < 1:
        return bot.reply_to(message, translate('welcome_empty', chat_id))
    if safe_db_operation("INSERT OR REPLACE INTO welcome VALUES (?, ?, ?)", 
                       (chat_id, msg if 'welcome' in action else None, msg if 'leave' in action else None)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('welcome_set', chat_id))
    else:
        bot.reply_to(message, translate('welcome_set', chat_id).replace("set", "error setting"))

# ANTI-FLOOD MENU
@bot.callback_query_handler(func=lambda call: call.data == 'flood_menu')
def flood_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛡️ Enable", callback_data='flood_enable'),
        types.InlineKeyboardButton("⚙️ Set Limit", callback_data='flood_limit'),
        types.InlineKeyboardButton("📊 Stats", callback_data='flood_stats'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('flood_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('flood_'))
def flood_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'enable':
        bot.temp_data[chat_id] = {'action': 'flood_enable', 'timeout': time.time() + 300}
        text = translate('flood_menu', chat_id).split('\n')[0] + ": Send 'on' or 'off' to enable/disable flood protection:"
    elif action == 'limit':
        bot.temp_data[chat_id] = {'action': 'flood_set_limit', 'timeout': time.time() + 300}
        text = "⚙️ Send new limit (e.g., 5):"
    elif action == 'stats':
        text = "📊 Flood stats: 0 incidents (placeholder)."
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='flood_menu'),
        types.InlineKeyboardButton("📊 Stats", callback_data='flood_stats')
    )
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_flood_set_limit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        limit = parse_number(message.text)
        if limit < 1 or limit > 50:
            return bot.reply_to(message, translate('flood_invalid_limit', chat_id))
        if safe_db_operation("INSERT OR REPLACE INTO flood_settings VALUES (?, ?, ?)", (chat_id, limit, 'delete')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('flood_limit_set', chat_id, limit=limit))
        else:
            bot.reply_to(message, translate('flood_limit_set', chat_id, limit='error'))
    except ValueError:
        bot.reply_to(message, translate('flood_invalid_number', chat_id))

# BROADCAST MENU (जारी)
@bot.callback_query_handler(func=lambda call: call.data == 'broadcast_menu')
def broadcast_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[1], callback_data='broadcast_send'),
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[2], callback_data='broadcast_groups'),
        types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[3], callback_data='broadcast_preview'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('broadcast_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_'))
def broadcast_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'send':
        bot.temp_data[chat_id] = {'action': 'broadcast_send', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='broadcast_menu'),
            types.InlineKeyboardButton(translate('broadcast_menu', chat_id).split('\n')[3], callback_data='broadcast_preview')
        )
        bot.edit_message_text("📢 Send broadcast message:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'groups':
        bot.temp_data[chat_id] = {'action': 'broadcast_groups', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='broadcast_menu'),
            types.InlineKeyboardButton("📢 Send Now", callback_data='broadcast_send')
        )
        bot.edit_message_text("👥 Send group IDs (comma-separated):", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'preview':
        rows = safe_db_operation("SELECT message FROM broadcasts WHERE chat_id=? AND sent=0", (chat_id,), "fetch")
        text = rows[0][0] if rows else "No broadcast message set."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📢 Send Now", callback_data='broadcast_send'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='broadcast_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_broadcast_send(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    msg = sanitize_input(message.text)
    if safe_db_operation("INSERT INTO broadcasts VALUES (?, ?, 0)", (chat_id, msg)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('broadcast_menu', chat_id).split('\n')[0] + ": Message saved for broadcast!")
    else:
        bot.reply_to(message, translate('broadcast_menu', chat_id).split('\n')[0] + ": Error saving message.")

def handle_broadcast_groups(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    group_ids = [g.strip() for g in message.text.split(',')]
    rows = safe_db_operation("SELECT message FROM broadcasts WHERE chat_id=? AND sent=0", (chat_id,), "fetch")
    if not rows:
        return bot.reply_to(message, "No broadcast message set.")
    msg = rows[0][0]
    for gid in group_ids:
        try:
            bot.send_message(gid, msg)
            log_activity(gid, message.from_user.id, 'broadcast_sent')
        except Exception as e:
            logging.error(f"Broadcast error for {gid}: {e}")
    if safe_db_operation("UPDATE broadcasts SET sent=1 WHERE chat_id=?", (chat_id,)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('broadcast_menu', chat_id).split('\n')[0] + ": Broadcast sent!")
    else:
        bot.reply_to(message, translate('broadcast_menu', chat_id).split('\n')[0] + ": Error sending broadcast.")

# BLACKLIST MENU
@bot.callback_query_handler(func=lambda call: call.data == 'blacklist_menu')
def blacklist_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[1], callback_data='blacklist_add_word'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[2], callback_data='blacklist_add_regex'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[3], callback_data='blacklist_list'),
        types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[4], callback_data='blacklist_remove'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('blacklist_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('blacklist_'))
def blacklist_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action in ['add_word', 'add_regex']:
        bot.temp_data[chat_id] = {'action': 'blacklist_add', 'regex': 1 if 'regex' in action else 0, 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='blacklist_menu'),
            types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[3], callback_data='blacklist_list')
        )
        bot.edit_message_text(f"Send {'regex pattern' if 'regex' in action else 'word'} to blacklist:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        blacklists = safe_db_operation("SELECT word FROM blacklists WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('blacklist_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {w[0]}" for w in blacklists) or "No blacklisted words."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[1], callback_data='blacklist_add_word'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='blacklist_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'remove':
        bot.temp_data[chat_id] = {'action': 'blacklist_remove', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='blacklist_menu'),
            types.InlineKeyboardButton(translate('blacklist_menu', chat_id).split('\n')[3], callback_data='blacklist_list')
        )
        bot.edit_message_text("Send word to remove from blacklist:", chat_id, call.message.message_id, reply_markup=markup)

def handle_blacklist_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    word = sanitize_input(message.text)
    if bot.temp_data[chat_id]['regex'] and not validate_regex(word):
        return bot.reply_to(message, translate('invalid_regex', chat_id))
    if len(word) > 100:
        return bot.reply_to(message, translate('blacklist_too_long', chat_id))
    if safe_db_operation("SELECT 1 FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word), "fetch"):
        return bot.reply_to(message, translate('blacklist_exists', chat_id))
    if safe_db_operation("INSERT INTO blacklists VALUES (?, ?, ?)", (chat_id, word, bot.temp_data[chat_id]['regex'])):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('blacklist_added', chat_id))
    else:
        bot.reply_to(message, translate('blacklist_added', chat_id).replace("added", "error adding"))

def handle_blacklist_remove(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    word = sanitize_input(message.text)
    if safe_db_operation("DELETE FROM blacklists WHERE chat_id=? AND word=?", (chat_id, word)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('blacklist_menu', chat_id).split('\n')[0] + ": Word removed!")
    else:
        bot.reply_to(message, translate('blacklist_menu', chat_id).split('\n')[0] + ": Word not found!")

# PERMISSIONS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'permissions_menu')
def permissions_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[1], callback_data='permissions_grant'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[2], callback_data='permissions_list'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[3], callback_data='permissions_commands'),
        types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[4], callback_data='permissions_duration'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('permissions_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('permissions_'))
def permissions_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'grant':
        bot.temp_data[chat_id] = {'action': 'grant_role', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='permissions_menu'),
            types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[2], callback_data='permissions_list')
        )
        bot.edit_message_text("Send: @username role (e.g., @user ADMIN)", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        roles = safe_db_operation("SELECT user_id, role FROM permissions WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('permissions_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {r[0]}: {r[1]}" for r in roles) or "No roles assigned."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[1], callback_data='permissions_grant'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='permissions_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'commands':
        bot.temp_data[chat_id] = {'action': 'permissions_commands', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='permissions_menu'),
            types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[2], callback_data='permissions_list')
        )
        bot.edit_message_text("Send role and commands (e.g., ADMIN:/warn,/ban)", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'duration':
        bot.temp_data[chat_id] = {'action': 'permissions_duration', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='permissions_menu'),
            types.InlineKeyboardButton(translate('permissions_menu', chat_id).split('\n')[2], callback_data='permissions_list')
        )
        bot.edit_message_text("Send: @username duration (e.g., @user 1d)", chat_id, call.message.message_id, reply_markup=markup)

def handle_grant_input(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        username, role = message.text.split()
        username = sanitize_input(username)
        role = role.upper()
        if role not in ['ADMIN', 'MOD']:
            return bot.reply_to(message, translate('role_error', chat_id))
        user_id = username.strip('@')
        if safe_db_operation("INSERT OR REPLACE INTO permissions VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, user_id, role, '', '')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('role_granted', chat_id, role=role, user_name=username, user_id=user_id))
        else:
            bot.reply_to(message, translate('role_error', chat_id))
    except ValueError:
        bot.reply_to(message, translate('role_error', chat_id))

def handle_permissions_commands(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        role, commands = message.text.split(':', 1)
        role = role.upper()
        if role not in ['ADMIN', 'MOD']:
            return bot.reply_to(message, translate('role_error', chat_id))
        if safe_db_operation("UPDATE permissions SET commands=? WHERE chat_id=? AND role=?", 
                           (commands, chat_id, role)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('permissions_menu', chat_id).split('\n')[0] + ": Commands updated!")
        else:
            bot.reply_to(message, translate('role_error', chat_id))
    except ValueError:
        bot.reply_to(message, translate('role_error', chat_id))

def handle_permissions_duration(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        username, duration = message.text.split()
        if not validate_time_format(duration):
            return bot.reply_to(message, translate('note_invalid_expire', chat_id))
        user_id = username.strip('@')
        if safe_db_operation("UPDATE permissions SET duration=? WHERE chat_id=? AND user_id=?", 
                           (duration, chat_id, user_id)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('permissions_menu', chat_id).split('\n')[0] + ": Duration updated!")
        else:
            bot.reply_to(message, translate('role_error', chat_id))
    except ValueError:
        bot.reply_to(message, translate('role_error', chat_id))

# CUSTOM COMMANDS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'customcmd_menu')
def customcmd_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[1], callback_data='customcmd_create'),
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[2], callback_data='customcmd_list'),
        types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[3], callback_data='customcmd_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('customcmd_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('customcmd_'))
def customcmd_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'create':
        bot.temp_data[chat_id] = {'action': 'customcmd_create', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='customcmd_menu'),
            types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[2], callback_data='customcmd_list')
        )
        bot.edit_message_text("Send: /command response (e.g., /hello Hi there!)", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        commands = safe_db_operation("SELECT trigger, response FROM custom_commands WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('customcmd_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• /{t}: {r}" for t, r in commands) or "No custom commands."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[1], callback_data='customcmd_create'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='customcmd_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'edit':
        bot.temp_data[chat_id] = {'action': 'customcmd_edit', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='customcmd_menu'),
            types.InlineKeyboardButton(translate('customcmd_menu', chat_id).split('\n')[2], callback_data='customcmd_list')
        )
        bot.edit_message_text("Send command to edit (e.g., /hello):", chat_id, call.message.message_id, reply_markup=markup)

def handle_customcmd_create(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        cmd, resp = message.text.split(' ', 1)
        cmd = sanitize_input(cmd.strip('/'))
        resp = sanitize_input(resp)
        if len(cmd) > 50 or len(resp) > 1000:
            return bot.reply_to(message, translate('command_too_long', chat_id))
        if safe_db_operation("SELECT 1 FROM custom_commands WHERE chat_id=? AND trigger=?", (chat_id, cmd), "fetch"):
            return bot.reply_to(message, translate('command_exists', chat_id))
        if safe_db_operation("INSERT INTO custom_commands VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, cmd, resp, 'all', '')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('command_added', chat_id))
        else:
            bot.reply_to(message, translate('command_added', chat_id).replace("added", "error adding"))
    except ValueError:
        bot.reply_to(message, translate('command_too_long', chat_id))

# POLLS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'polls_menu')
def polls_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[1], callback_data='poll_new'),
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[2], callback_data='poll_settings'),
        types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[3], callback_data='poll_active'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('polls_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('poll_'))
def poll_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'new':
        bot.temp_data[chat_id] = {'action': 'poll_new', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='polls_menu'),
            types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[3], callback_data='poll_active')
        )
        bot.edit_message_text("Send: question|option1,option2|anonymous|timer (e.g., Favorite color?|Red,Blue|yes|1h)", 
                             chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'settings':
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Back", callback_data='polls_menu'),
            types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[3], callback_data='poll_active')
        )
        bot.edit_message_text("Poll settings: Under development.", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'active':
        polls = safe_db_operation("SELECT poll_id, question FROM polls WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('polls_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {p[0]}: {p[1]}" for p in polls) or "No active polls."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('polls_menu', chat_id).split('\n')[1], callback_data='poll_new'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='polls_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_poll_new(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        question, options, anon, timer = message.text.split('|')
        question = sanitize_input(question)
        options = [sanitize_input(o.strip()) for o in options.split(',')]
        anon = 1 if anon.lower() == 'yes' else 0
        if not validate_time_format(timer):
            return bot.reply_to(message, translate('poll_invalid', chat_id))
        if safe_db_operation("INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?)", 
                           (chat_id, str(message.message_id), question, json.dumps(options), anon, timer, '')):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('poll_created', chat_id, poll_id=message.message_id))
        else:
            bot.reply_to(message, translate('poll_invalid', chat_id))
    except ValueError:
        bot.reply_to(message, translate('poll_invalid', chat_id))

# NOTES MENU
@bot.callback_query_handler(func=lambda call: call.data == 'notes_menu')
def notes_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[1], callback_data='note_save'),
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[2], callback_data='note_search'),
        types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[3], callback_data='note_share'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('notes_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('note_'))
def note_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'save':
        bot.temp_data[chat_id] = {'action': 'note_save', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='notes_menu'),
            types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[2], callback_data='note_search')
        )
        bot.edit_message_text("Send: #tag content|expire (e.g., #info Rules here|1d)", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'search':
        notes = safe_db_operation("SELECT tag, content FROM notes WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('notes_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {t}: {c}" for t, c in notes) or "No notes."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[1], callback_data='note_save'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='notes_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'share':
        bot.temp_data[chat_id] = {'action': 'note_share', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='notes_menu'),
            types.InlineKeyboardButton(translate('notes_menu', chat_id).split('\n')[2], callback_data='note_search')
        )
        bot.edit_message_text("Send #tag to share:", chat_id, call.message.message_id, reply_markup=markup)

def handle_note_save(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        tag_content, expire = message.text.split('|')
        tag = sanitize_input(tag_content.split(' ', 1)[0])
        content = sanitize_input(tag_content.split(' ', 1)[1] if ' ' in tag_content else '')
        if not validate_time_format(expire):
            return bot.reply_to(message, translate('note_invalid_expire', chat_id))
        if safe_db_operation("INSERT INTO notes VALUES (?, ?, ?, ?)", 
                           (chat_id, tag, content, expire)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('note_saved', chat_id))
        else:
            bot.reply_to(message, translate('note_saved', chat_id).replace("saved", "error saving"))
    except ValueError:
        bot.reply_to(message, translate('note_invalid_expire', chat_id))

def handle_note_share(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    tag = sanitize_input(message.text)
    rows = safe_db_operation("SELECT content FROM notes WHERE chat_id=? AND tag=?", (chat_id, tag), "fetch")
    if rows:
        bot.reply_to(message, f"{tag}: {rows[0][0]}")
        del bot.temp_data[chat_id]
    else:
        bot.reply_to(message, translate('notes_menu', chat_id).split('\n')[0] + ": Note not found!")

# RSS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'rss_menu')
def rss_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[1], callback_data='rss_add'),
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[2], callback_data='rss_list'),
        types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[3], callback_data='rss_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('rss_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('rss_'))
def rss_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'add':
        bot.temp_data[chat_id] = {'action': 'rss_add', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='rss_menu'),
            types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[2], callback_data='rss_list')
        )
        bot.edit_message_text("Send: url|keywords|interval|format (e.g., https://example.com/feed|news|1h|text)", 
                             chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        feeds = safe_db_operation("SELECT url, keywords FROM rss_feeds WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('rss_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {u}: {k}" for u, k in feeds) or "No RSS feeds."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[1], callback_data='rss_add'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='rss_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'edit':
        bot.temp_data[chat_id] = {'action': 'rss_edit', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='rss_menu'),
            types.InlineKeyboardButton(translate('rss_menu', chat_id).split('\n')[2], callback_data='rss_list')
        )
        bot.edit_message_text("Send URL to edit:", chat_id, call.message.message_id, reply_markup=markup)

def handle_rss_add(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        url, keywords, interval, fmt = message.text.split('|')
        if not validate_url(url):
            return bot.reply_to(message, translate('rss_invalid_url', chat_id))
        if not validate_time_format(interval):
            return bot.reply_to(message, translate('rss_invalid_interval', chat_id))
        if safe_db_operation("INSERT INTO rss_feeds VALUES (?, ?, ?, ?, ?)", 
                           (chat_id, url, keywords, interval, fmt)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('rss_added', chat_id))
        else:
            bot.reply_to(message, translate('rss_added', chat_id).replace("added", "error adding"))
    except ValueError:
        bot.reply_to(message, translate('rss_invalid_url', chat_id))

def handle_rss_edit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        url, keywords, interval, fmt = message.text.split('|')
        if not validate_url(url):
            return bot.reply_to(message, translate('rss_invalid_url', chat_id))
        if not validate_time_format(interval):
            return bot.reply_to(message, translate('rss_invalid_interval', chat_id))
        if safe_db_operation("UPDATE rss_feeds SET keywords=?, interval=?, format=? WHERE chat_id=? AND url=?", 
                           (keywords, interval, fmt, chat_id, url)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('rss_menu', chat_id).split('\n')[0] + ": Feed updated!")
        else:
            bot.reply_to(message, translate('rss_menu', chat_id).split('\n')[0] + ": Feed not found!")
    except ValueError:
        bot.reply_to(message, translate('rss_invalid_url', chat_id))

# SUBSCRIPTIONS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'subs_menu')
def subs_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[1], callback_data='sub_grant'),
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[2], callback_data='sub_list'),
        types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[3], callback_data='sub_edit'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('subs_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sub_'))
def sub_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'grant':
        bot.temp_data[chat_id] = {'action': 'sub_grant', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='subs_menu'),
            types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[2], callback_data='sub_list')
        )
        bot.edit_message_text("Send: @username plan duration (e.g., @user premium 1m)", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        subs = safe_db_operation("SELECT user_id, plan, duration FROM subscriptions WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('subs_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {s[0]}: {s[1]} ({s[2]})" for s in subs) or "No subscriptions."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[1], callback_data='sub_grant'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='subs_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'edit':
        bot.temp_data[chat_id] = {'action': 'sub_edit', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='subs_menu'),
            types.InlineKeyboardButton(translate('subs_menu', chat_id).split('\n')[2], callback_data='sub_list')
        )
        bot.edit_message_text("Send: @username new_plan new_duration", chat_id, call.message.message_id, reply_markup=markup)

def handle_sub_grant(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        username, plan, duration = message.text.split()
        if not validate_time_format(duration):
            return bot.reply_to(message, translate('sub_invalid_duration', chat_id))
        user_id = username.strip('@')
        if safe_db_operation("INSERT INTO subscriptions VALUES (?, ?, ?, ?, 1)", 
                           (chat_id, user_id, plan, duration)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('sub_granted', chat_id))
        else:
            bot.reply_to(message, translate('sub_granted', chat_id).replace("granted", "error granting"))
    except ValueError:
        bot.reply_to(message, translate('sub_invalid_duration', chat_id))

def handle_sub_edit(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        username, plan, duration = message.text.split()
        if not validate_time_format(duration):
            return bot.reply_to(message, translate('sub_invalid_duration', chat_id))
        user_id = username.strip('@')
        if safe_db_operation("UPDATE subscriptions SET plan=?, duration=? WHERE chat_id=? AND user_id=?", 
                           (plan, duration, chat_id, user_id)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('subs_menu', chat_id).split('\n')[0] + ": Subscription updated!")
        else:
            bot.reply_to(message, translate('subs_menu', chat_id).split('\n')[0] + ": Subscription not found!")
    except ValueError:
        bot.reply_to(message, translate('sub_invalid_duration', chat_id))

# FEDERATION MENU
@bot.callback_query_handler(func=lambda call: call.data == 'fed_menu')
def fed_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[1], callback_data='fed_link'),
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[2], callback_data='fed_list'),
        types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[3], callback_data='fed_sync'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('fed_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fed_'))
def fed_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'link':
        bot.temp_data[chat_id] = {'action': 'fed_link', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='fed_menu'),
            types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[2], callback_data='fed_list')
        )
        bot.edit_message_text("Send group ID to link:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        groups = safe_db_operation("SELECT linked_group FROM federations WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('fed_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {g[0]}" for g in groups) or "No linked groups."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[1], callback_data='fed_link'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='fed_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'sync':
        bot.temp_data[chat_id] = {'action': 'fed_sync', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='fed_menu'),
            types.InlineKeyboardButton(translate('fed_menu', chat_id).split('\n')[2], callback_data='fed_list')
        )
        bot.edit_message_text("Send sync actions (e.g., bans,warns)", chat_id, call.message.message_id, reply_markup=markup)

def handle_fed_link(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    linked_group = sanitize_input(message.text)
    if safe_db_operation("INSERT INTO federations VALUES (?, ?, ?, 0)", 
                       (chat_id, linked_group, '',)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('fed_linked', chat_id))
    else:
        bot.reply_to(message, translate('fed_error', chat_id))

def handle_fed_sync(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    actions = sanitize_input(message.text)
    if safe_db_operation("UPDATE federations SET sync_actions=? WHERE chat_id=?", 
                       (actions, chat_id)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('fed_menu', chat_id).split('\n')[0] + ": Sync actions updated!")
    else:
        bot.reply_to(message, translate('fed_error', chat_id))

# CAPTCHA MENU
@bot.callback_query_handler(func=lambda call: call.data == 'captcha_menu')
def captcha_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[1], callback_data='captcha_type'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[2], callback_data='captcha_difficulty'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[3], callback_data='captcha_time'),
        types.InlineKeyboardButton(translate('captcha_menu', chat_id).split('\n')[4], callback_data='captcha_action'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('captcha_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def captcha_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    bot.temp_data[chat_id] = {'action': 'captcha_set', 'sub_action': action, 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Cancel", callback_data='captcha_menu'),
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu')
    )
    
    if action == 'type':
        text = "Send captcha type (math/text/image):"
    elif action == 'difficulty':
        text = "Send difficulty (easy/medium/hard):"
    elif action == 'time':
        text = "Send time limit (e.g., 5m):"
    elif action == 'action':
        text = "Send fail action (kick/mute):"
    
    bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_captcha_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    sub_action = bot.temp_data[chat_id]['sub_action']
    value = sanitize_input(message.text)
    
    if sub_action == 'type' and value not in ['math', 'text', 'image']:
        return bot.reply_to(message, translate('captcha_error', chat_id))
    elif sub_action == 'difficulty' and value not in ['easy', 'medium', 'hard']:
        return bot.reply_to(message, translate('captcha_invalid_difficulty', chat_id))
    elif sub_action == 'time' and not validate_time_format(value):
        return bot.reply_to(message, translate('captcha_invalid_time', chat_id))
    elif sub_action == 'action' and value not in ['kick', 'mute']:
        return bot.reply_to(message, translate('captcha_invalid_action', chat_id))
    
    column = {'type': 'type', 'difficulty': 'difficulty', 'time': 'time_limit', 'action': 'fail_action'}[sub_action]
    if safe_db_operation(f"INSERT OR REPLACE INTO captchas (chat_id, {column}) VALUES (?, ?)", 
                       (chat_id, value)):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('captcha_saved', chat_id))
    else:
        bot.reply_to(message, translate('captcha_error', chat_id))

# MESSAGE DUMP MENU
@bot.callback_query_handler(func=lambda call: call.data == 'dump_menu')
def dump_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[1], callback_data='dump_enable'),
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[2], callback_data='dump_channel'),
        types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[3], callback_data='dump_view'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('dump_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dump_'))
def dump_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'enable':
        bot.temp_data[chat_id] = {'action': 'dump_set', 'sub_action': 'enable', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='dump_menu'),
            types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[3], callback_data='dump_view')
        )
        bot.edit_message_text("Send 'on' or 'off' to enable/disable message dump:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'channel':
        bot.temp_data[chat_id] = {'action': 'dump_set', 'sub_action': 'channel', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='dump_menu'),
            types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[3], callback_data='dump_view')
        )
        bot.edit_message_text("Send channel ID for message dump:", chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'view':
        dumps = safe_db_operation("SELECT deleted_msg, timestamp FROM message_dump WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('dump_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {t}: {m}" for m, t in dumps) or "No dumped messages."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('dump_menu', chat_id).split('\n')[1], callback_data='dump_enable'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='dump_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)

def handle_dump_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    sub_action = bot.temp_data[chat_id]['sub_action']
    value = sanitize_input(message.text)
    
    if sub_action == 'enable':
        if value not in ['on', 'off']:
            return bot.reply_to(message, translate('invalid_input', chat_id))
        if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, 'message_dump', 'status', ?)", 
                           (chat_id, json.dumps({'status': value}))):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('dump_enabled', chat_id, status='enabled' if value == 'on' else 'disabled'))
        else:
            bot.reply_to(message, translate('dump_error', chat_id))
    
    elif sub_action == 'channel':
        try:
            bot.get_chat(value)
            if safe_db_operation("INSERT OR REPLACE INTO message_dump (chat_id, dump_channel) VALUES (?, ?)", 
                               (chat_id, value)):
                del bot.temp_data[chat_id]
                bot.reply_to(message, translate('dump_channel_set', chat_id))
            else:
                bot.reply_to(message, translate('dump_error', chat_id))
        except:
            bot.reply_to(message, translate('dump_invalid_channel', chat_id))

# PLUGINS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'plugins_menu')
def plugins_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[1], callback_data='plugin_install'),
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[2], callback_data='plugin_list'),
        types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[3], callback_data='plugin_config'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('plugins_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('plugin_'))
def plugin_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    if action == 'install':
        bot.temp_data[chat_id] = {'action': 'plugin_install', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='plugins_menu'),
            types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[2], callback_data='plugin_list')
        )
        bot.edit_message_text("Send plugin name and config (e.g., plugin_name|key:value)", 
                             chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'list':
        plugins = safe_db_operation("SELECT plugin_name, config FROM plugins WHERE chat_id=?", (chat_id,), "fetch")
        text = translate('plugins_menu', chat_id).split('\n')[0] + ":\n" + "\n".join(f"• {p}: {c}" for p, c in plugins) or "No plugins installed."
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[1], callback_data='plugin_install'),
            types.InlineKeyboardButton("⬅️ Back", callback_data='plugins_menu')
        )
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup)
    
    elif action == 'config':
        bot.temp_data[chat_id] = {'action': 'plugin_config', 'timeout': time.time() + 300}
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("⬅️ Cancel", callback_data='plugins_menu'),
            types.InlineKeyboardButton(translate('plugins_menu', chat_id).split('\n')[2], callback_data='plugin_list')
        )
        bot.edit_message_text("Send plugin name and new config (e.g., plugin_name|key:value)", 
                             chat_id, call.message.message_id, reply_markup=markup)

def handle_plugin_install(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        name, config = message.text.split('|')
        name = sanitize_input(name)
        config = sanitize_input(config)
        if safe_db_operation("INSERT INTO plugins VALUES (?, ?, ?, 1)", 
                           (chat_id, name, config)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('plugin_installed', chat_id))
        else:
            bot.reply_to(message, translate('plugin_error', chat_id))
    except ValueError:
        bot.reply_to(message, translate('plugin_error', chat_id))

def handle_plugin_config(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    try:
        name, config = message.text.split('|')
        name = sanitize_input(name)
        config = sanitize_input(config)
        if safe_db_operation("UPDATE plugins SET config=? WHERE chat_id=? AND plugin_name=?", 
                           (config, chat_id, name)):
            del bot.temp_data[chat_id]
            bot.reply_to(message, translate('plugins_menu', chat_id).split('\n')[0] + ": Config updated!")
        else:
            bot.reply_to(message, translate('plugin_error', chat_id))
    except ValueError:
        bot.reply_to(message, translate('plugin_error', chat_id))

# MODERATION LOCKS MENU
@bot.callback_query_handler(func=lambda call: call.data == 'moderation_lock')
def moderation_lock_menu(call):
    chat_id = str(call.message.chat.id)
    settings = get_all_settings(chat_id)
    
    links_status = '✅' if safe_json(settings.get('moderation_lock_links', '{}'))['status'] == 'on' else '❌'
    media_status = '✅' if safe_json(settings.get('moderation_lock_media', '{}'))['status'] == 'on' else '❌'
    stickers_status = '✅' if safe_json(settings.get('moderation_lock_stickers', '{}'))['status'] == 'on' else '❌'
    forwards_status = '✅' if safe_json(settings.get('moderation_lock_forwards', '{}'))['status'] == 'on' else '❌'
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(f"🔗 Links: {links_status}", callback_data='lock_links'),
        types.InlineKeyboardButton(f"📸 Media: {media_status}", callback_data='lock_media'),
        types.InlineKeyboardButton(f"😀 Stickers: {stickers_status}", callback_data='lock_stickers'),
        types.InlineKeyboardButton(f"📤 Forwards: {forwards_status}", callback_data='lock_forwards'),
        types.InlineKeyboardButton("⬅️ Back", callback_data='group_menu')
    )
    
    bot.edit_message_text(translate('moderation_lock_menu', chat_id, 
                                   links_status=links_status, 
                                   media_status=media_status, 
                                   stickers_status=stickers_status, 
                                   forwards_status=forwards_status), 
                         chat_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lock_'))
def lock_action(call):
    action = call.data.split('_')[1]
    chat_id = str(call.message.chat.id)
    
    bot.temp_data[chat_id] = {'action': 'lock_set', 'sub_action': action, 'timeout': time.time() + 300}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Cancel", callback_data='moderation_lock'),
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu')
    )
    bot.edit_message_text(f"Send 'on' or 'off' to set {action} lock:", chat_id, call.message.message_id, reply_markup=markup)

def handle_lock_set(message):
    chat_id = str(message.chat.id)
    if chat_id not in bot.temp_data: return
    sub_action = bot.temp_data[chat_id]['sub_action']
    value = message.text.lower()
    
    if value not in ['on', 'off']:
        return bot.reply_to(message, translate('invalid_input', chat_id))
    
    if safe_db_operation("INSERT OR REPLACE INTO settings VALUES (?, ?, ?, ?)", 
                       (chat_id, 'moderation', f'lock_{sub_action}', json.dumps({'status': value}))):
        del bot.temp_data[chat_id]
        bot.reply_to(message, translate('lock_set', chat_id, action=sub_action.capitalize(), status='enabled' if value == 'on' else 'disabled'))
    else:
        bot.reply_to(message, translate('lock_error', chat_id, action=sub_action.capitalize()))

# ADVANCED MENU
@bot.callback_query_handler(func=lambda call: call.data == 'advanced_menu')
def advanced_menu(call):
    chat_id = str(call.message.chat.id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        (translate('permissions_menu', chat_id).split('\n')[0], 'permissions_menu'),
        (translate('customcmd_menu', chat_id).split('\n')[0], 'customcmd_menu'),
        (translate('polls_menu', chat_id).split('\n')[0], 'polls_menu'),
        (translate('notes_menu', chat_id).split('\n')[0], 'notes_menu'),
        (translate('rss_menu', chat_id).split('\n')[0], 'rss_menu'),
        (translate('subs_menu', chat_id).split('\n')[0], 'subs_menu'),
        (translate('fed_menu', chat_id).split('\n')[0], 'fed_menu'),
        (translate('captcha_menu', chat_id).split('\n')[0], 'captcha_menu'),
        (translate('dump_menu', chat_id).split('\n')[0], 'dump_menu'),
        (translate('plugins_menu', chat_id).split('\n')[0], 'plugins_menu'),
        ("⬅️ Back", 'main')
    ]
    markup.add(*[types.InlineKeyboardButton(text, callback_data=data) for text, data in buttons])
    
    bot.edit_message_text(translate('advanced_menu', chat_id), chat_id, call.message.message_id, reply_markup=markup)

# SHOW COMMANDS
@bot.callback_query_handler(func=lambda call: call.data == 'show_commands')
def show_commands(call):
    chat_id = str(call.message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data='main'),
        types.InlineKeyboardButton(translate('group_menu', chat_id).split('\n')[0], callback_data='group_menu')
    )
    bot.edit_message_text(translate('commands_list', chat_id), chat_id, call.message.message_id, reply_markup=markup)

# FLASK WEBHOOK
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = telebot.types.Update.de_json(request.get_json())
        bot.process_new_updates([update])
        return '', 200
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return '', 500

# Vercel entry point
if __name__ == '__main__':
    try:
        bot.remove_webhook()
        webhook_url = os.getenv('WEBHOOK_URL', f'https://{os.getenv("VERCEL_URL")}/webhook')
        bot.set_webhook(url=webhook_url)
        app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
    except Exception as e:
        logging.error(f"Startup error: {e}")
