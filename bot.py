
import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")
CHANNEL_USERNAME = "nr_hackz"  # bina @ ke
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

bot = telebot.TeleBot(BOT_TOKEN)

def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Join check error: {e}")
        # Agar bot channel ka admin nahi hai to ye error ayega
        return True

def short_link(long_url):
    try:
        # Tere API key lnk_... ke liye try
        # Agar tera provider Short.io / Dub type ka hai to isko change karna padega
        # Abhi ShrinkEarn + Generic support rakha hai
        url = f"https://shrinkearn.com/api?api={API_KEY}&url={long_url}"
        res = requests.get(url, timeout=15).json()
        if 'shortenedUrl' in res:
            return res['shortenedUrl']
        return res.get('short_url') or res.get('link')
    except Exception as e:
        print(f"Shorten error: {e}")
        return None

def join_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Channel Join Karo", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("✅ I Joined - Check Karo", callback_data="check_joined"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not is_user_joined(user_id):
        bot.send_message(
            message.chat.id,
            f"⚠️ Bot use karne ke liye pehle hamara channel join karna padega.\n\n"
            f"👉 @{CHANNEL_USERNAME} ko join karo, fir neeche 'I Joined' dabao.",
            reply_markup=join_keyboard()
        )
        return
    
    bot.send_message(
        message.chat.id,
        "💰 *Welcome to NR Hackz Earning Bot!*\n\n"
        "Bas koi bhi link bhejo, main usko paise kamane wala link bana dunga.\n\n"
        "🔗 YouTube, Drive, Insta sab chalega\n"
        "💵 1000 Clicks = ₹400 tak\n\n"
        "Abhi link bhejo 👇",
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "check_joined")
def check_joined(call):
    user_id = call.from_user.id
    if is_user_joined(user_id):
        bot.answer_callback_query(call.id, "✅ Thanks! Ab link bhejo.")
        bot.send_message(
            call.message.chat.id,
            "✅ Verification ho gaya!\nAb koi bhi link bhejo earning ke liye."
        )
    else:
        bot.answer_callback_query(call.id, "❌ Abhi tak join nahi kiya!", show_alert=True)

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    user_id = message.from_user.id
    if not is_user_joined(user_id):
        bot.send_message(message.chat.id, f"⛔ Pehle @{CHANNEL_USERNAME} join karo!", reply_markup=join_keyboard())
        return

    long_url = message.text.strip()
    if not long_url.startswith("http"):
        bot.reply_to(message, "❌ Sahi link bhejo, jaise https://google.com")
        return

    loading = bot.reply_to(message, "⏳ Earning link bana raha hu...")
    s_link = short_link(long_url)

    if s_link:
        bot.edit_message_text(
            f"✅ *Link Ready!*\n\n"
            f"💰 Earning Link:\n{s_link}\n\n"
            f"Share karo, har click ka paisa dashboard me ayega.",
            chat_id=message.chat.id,
            message_id=loading.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            "❌ Link short nahi hua. API Key ya Provider check karo.",
            chat_id=message.chat.id,
            message_id=loading.message_id
        )

print("Bot Started...")
bot.infinity_polling()
                         
