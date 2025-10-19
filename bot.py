from flask import Flask, request
import telebot, os, sqlite3, json
from telebot import types
from dotenv import load_dotenv

load_dotenv()
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
app = Flask(__name__)

# Simple Database
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
def start(m): bot.send_message(m.chat.id, "🤖 **BOT LIVE!**", reply_markup=Buttons.main())

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    chat_id = c.message.chat.id
    if c.data == 'main': bot.edit_message_text("🤖 MENU", chat_id, c.message.id, reply_markup=Buttons.main())
    elif c.data == 'spam': bot.answer_callback_query(c.id, "🚫 AntiSpam ON!")
    elif c.data == 'welcome': bot.answer_callback_query(c.id, "👋 Welcome ON!")
    elif c.data == 'ban': bot.answer_callback_query(c.id, "🔒 Ban Ready!")
    elif c.data == 'rules': bot.answer_callback_query(c.id, "📜 Rules Set!")

@app.route('/')
def home(): return "🤖 Bot Live!"

@app.route('/webhook', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return ''

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=os.getenv('WEBHOOK_URL'))
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)