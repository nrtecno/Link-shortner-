
import os
import time
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, request, abort

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
CHANNEL_USERNAME = "nr_hackz"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

# Render tumhe ye URL dega, agar nahi hai to manual daal do
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL") or "https://link-shortner-hin5.onrender.com"
WEBHOOK_URL = f"{RENDER_URL}/webhook/{BOT_TOKEN}"

bot = telebot.TeleBot(BOT_TOKEN)

def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Join check error: {e}")
        return True

def short_with_linksterr(long_url):
    print(f"Trying to shorten: {long_url}")
    # Try 1: Bearer
    try:
        print("Attempt 1: Bearer")
        res = requests.post(
            "https://linksterr.com/api/links",
            json={"url": long_url},
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            timeout=15
        )
        print(f"A1: {res.status_code} - {res.text[:600]}")
        if res.status_code in [200, 201]:
            data = res.json()
            link = data.get("short_url") or data.get("link") or data.get("data", {}).get("short_url")
            if link: return link
    except Exception as e:
        print(f"A1 Error: {e}")

    # Try 2: x-api-key
    try:
        print("Attempt 2: X-API-KEY")
        res = requests.post(
            "https://linksterr.com/api/links",
            json={"url": long_url},
            headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
            timeout=15
        )
        print(f"A2: {res.status_code} - {res.text[:600]}")
        if res.status_code in [200, 201]:
            data = res.json()
            link = data.get("short_url") or data.get("link")
            if link: return link
    except Exception as e:
        print(f"A2 Error: {e}")

    # Try 3: GET api
    try:
        print("Attempt 3: GET")
        res = requests.get(f"https://linksterr.com/api?api={API_KEY}&url={long_url}", timeout=15)
        print(f"A3: {res.status_code} - {res.text[:600]}")
        if res.status_code == 200:
            data = res.json()
            link = data.get("shortenedUrl") or data.get("short_url")
            if link: return link
    except Exception as e:
        print(f"A3 Error: {e}")

    return None

def join_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 @nr_hackz Join Karo", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("✅ I Joined - Check Karo", callback_data="check_joined"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    if not is_user_joined(message.from_user.id):
        bot.send_message(message.chat.id, f"⚠️ Pehle @{CHANNEL_USERNAME} join karo, fir 'I Joined' dabao.", reply_markup=join_keyboard())
        return
    bot.send_message(message.chat.id, "💰 *NR Hackz Bot Ready!*\n\nLink bhejo earning ke liye 👇", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "check_joined")
def check_joined(call):
    if is_user_joined(call.from_user.id):
        bot.answer_callback_query(call.id, "Verified!")
        bot.send_message(call.message.chat.id, "✅ Ho gaya! Ab link bhejo.")
    else:
        bot.answer_callback_query(call.id, "❌ Join nahi kiya!", show_alert=True)

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    if not is_user_joined(message.from_user.id):
        bot.send_message(message.chat.id, f"⛔ Pehle @{CHANNEL_USERNAME} join karo!", reply_markup=join_keyboard())
        return
    long_url = message.text.strip()
    if not long_url.startswith("http"):
        bot.reply_to(message, "❌ Sahi link bhejo")
        return
    loading = bot.reply_to(message, "⏳ Linksterr par bana raha hu...")
    s_link = short_with_linksterr(long_url)
    if s_link:
        bot.edit_message_text(f"✅ *Link Ready!*\n\n💰 {s_link}\n\nDashboard: https://linksterr.com/dashboard", chat_id=message.chat.id, message_id=loading.message_id, parse_mode="Markdown")
    else:
        bot.edit_message_text("❌ API Error. Logs me Attempt dekho aur mujhe bhejo.", chat_id=message.chat.id, message_id=loading.message_id)

@app.route('/')
def home():
    return "NR Hackz Bot is Running!"

@app.route(f'/webhook/{BOT_TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

# Webhook setup
if __name__ == "__main__":
    print(f"Setting webhook to {WEBHOOK_URL}")
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook set: {WEBHOOK_URL}")
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
    
