from flask import Flask, request
import telebot, os, sqlite3, json
from telebot import types
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Database
conn = sqlite3.connect('data.db', check_same_thread=False)
conn.execute('CREATE TABLE IF NOT EXISTS settings (chat_id INT PRIMARY KEY, data TEXT)')
conn.commit()

class Buttons:
    @staticmethod
    def main():
        markup = types.InlineKeyboardMarkup(row_width=2)
        btns = [('🚫 AntiSpam', 'spam'), ('👋 Welcome', 'welcome'), 
                ('🔒 Ban User', 'ban'), ('📜 Rules', 'rules'), ('❌ OFF', 'off')]
        for t, d in btns: markup.add(types.InlineKeyboardButton(t, callback_data=d))
        return markup

@bot.message_handler(commands=['start', 'settings'])
def start(m): 
    bot.send_message(m.chat.id, "🤖 **RENDER BOT LIVE!** 🎉", reply_markup=Buttons.main())

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.data == 'spam': bot.answer_callback_query(c.id, "🚫 AntiSpam ON!")
    elif c.data == 'welcome': bot.answer_callback_query(c.id, "👋 Welcome ON!")
    elif c.data == 'ban': bot.answer_callback_query(c.id, "🔒 Ban Ready!")
    elif c.data == 'rules': bot.answer_callback_query(c.id, "📜 Rules Set!")

# ✅ FIXED WEBHOOK ROUTE!
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return '', 200
    return 'OK', 200

@app.route('/')
def home(): return "🤖 Bot Live on Render!"

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=f"https://helliobot.onrender.com/{TOKEN}")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
