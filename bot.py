import os
from telebot import TeleBot, types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not found! Please set it in .env file.")

bot = TeleBot(BOT_TOKEN)

# --- Commands ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Hello! I'm your Group Manager Bot. Add me to a group and make me admin!")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "📋 *Available Commands:*\n"
        "/rules - Show group rules\n"
        "/warn - Warn a user\n"
        "/ban - Ban a user\n"
        "/mute - Mute a user\n"
        "/unmute - Unmute a user"
    )
    bot.send_message(message.chat.id, help_text, parse_mode='Markdown')

print("🤖 Bot is running...")
bot.infinity_polling()