
import os
import requests
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "NR Hackz Bot is Running! Bot is alive."

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
CHANNEL_USERNAME = "nr_hackz"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

bot = telebot.TeleBot(BOT_TOKEN)

# --- Fix 409 Conflict ---
try:
    bot.delete_webhook(drop_pending_updates=True)
    print("Webhook deleted, polling clean")
except Exception as e:
    print(f"Webhook delete error: {e}")

def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Join check error: {e}")
        return True

def short_with_linksterr(long_url):
    print(f"Trying to shorten: {long_url}")
    # List of all possible formats Linksterr might use
    attempts = []

    # 1. Official Bearer format
    try:
        print("Attempt 1: Bearer Token")
        res = requests.post(
            "https://linksterr.com/api/links",
            json={"url": long_url},
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json", "Accept": "application/json"},
            timeout=15
        )
        print(f"Attempt 1 Response: {res.status_code} - {res.text[:500]}")
        if res.status_code in [200, 201]:
            data = res.json()
            link = data.get("short_url") or data.get("link") or data.get("data", {}).get("short_url") or data.get("url")
            if link:
                return link
    except Exception as e:
        print(f"Attempt 1 Error: {e}")

    # 2. API Key header format
    try:
        print("Attempt 2: X-API-KEY header")
        res = requests.post(
            "https://linksterr.com/api/links",
            json={"url": long_url},
            headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
            timeout=15
        )
        print(f"Attempt 2 Response: {res.status_code} - {res.text[:500]}")
        if res.status_code in [200, 201]:
            data = res.json()
            link = data.get("short_url") or data.get("link") or data.get("data", {}).get("short_url")
            if link:
                return link
    except Exception as e:
        print(f"Attempt 2 Error: {e}")

    # 3. Old style GET API
    try:
        print("Attempt 3: GET ?api=KEY&url=")
        res = requests.get(
            f"https://linksterr.com/api?api={API_KEY}&url={long_url}",
            timeout=15
        )
        print(f"Attempt 3 Response: {res.status_code} - {res.text[:500]}")
        if res.status_code == 200:
            data = res.json()
            link = data.get("shortenedUrl") or data.get("short_url") or data.get("link")
            if link:
                return link
    except Exception as e:
        print(f"Attempt 3 Error: {e}")

    # 4. /api/v1/shorten
    try:
        print("Attempt 4: /api/v1/links")
        res = requests.post(
            "https://linksterr.com/api/v1/links",
            json={"url": long_url},
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=15
        )
        print(f"Attempt 4 Response: {res.status_code} - {res.text[:500]}")
        if res.status_code in [200, 201]:
            data = res.json()
            link = data.get("short_url") or data.get("link")
            if link:
                return link
    except Exception as e:
        print(f"Attempt 4 Error: {e}")

    print("All attempts failed")
    return None

def join_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 @nr_hackz Join Karo", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("✅ I Joined - Check Karo", callback_data="check_joined"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not is_user_joined(user_id):
        bot.send_message(
            message.chat.id,
            f"⚠️ Bot use karne se pehle channel join karna zaruri hai.\n\n👉 @{CHANNEL_USERNAME} ko join karo, fir 'I Joined' dabao.",
            reply_markup=join_keyboard()
        )
        return
    bot.send_message(
        message.chat.id,
        "💰 *NR Hackz Earning Bot Ready!*\n\nKoi bhi link bhejo, main Linksterr se earning link bana dunga.\n\n🌍 US - $3.25 / 1000 clicks\n🇩🇪 Germany - $10.50 / 1000 clicks\n\nLink bhejo 👇",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_joined")
def check_joined(call):
    user_id = call.from_user.id
    if is_user_joined(user_id):
        bot.answer_callback_query(call.id, "Verified!")
        bot.send_message(call.message.chat.id, "✅ Verification ho gaya! Ab koi bhi link bhejo.")
    else:
        bot.answer_callback_query(call.id, "❌ Abhi tak join nahi kiya!", show_alert=True)

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    if not is_user_joined(message.from_user.id):
        bot.send_message(message.chat.id, f"⛔ Pehle @{CHANNEL_USERNAME} join karo!", reply_markup=join_keyboard())
        return
    long_url = message.text.strip()
    if not long_url.startswith("http"):
        bot.reply_to(message, "❌ Sahi link bhejo, jaise https://youtube.com/...")
        return
    loading = bot.reply_to(message, "⏳ Linksterr par link bana raha hu... (thoda time lagega)")
    s_link = short_with_linksterr(long_url)
    if s_link:
        bot.edit_message_text(
            f"✅ *Link Ready!*\n\n💰 Earning Link:\n{s_link}\n\nDashboard: https://linksterr.com/dashboard",
            chat_id=message.chat.id,
            message_id=loading.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            "❌ API Error. Render logs me dekho kaunsa Attempt fail hua.\n\nAgar 401/403 aaya to API Key galat hai. Agar 404 aaya to endpoint galat hai. Screenshot bhejo.",
            chat_id=message.chat.id,
            message_id=loading.message_id
        )

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Bot Started...")
    bot.infinity_polling()
    
