
import os
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("API_KEY")  # lnk_8bRfhHM32fzyHQn74sOmJIAnP8D3PEdyNbvjeyyW
CHANNEL_USERNAME = "nr_hackz"
CHANNEL_LINK = f"https://t.me/{CHANNEL_USERNAME}"

bot = telebot.TeleBot(BOT_TOKEN)

def is_user_joined(user_id):
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Join check error (bot admin banao): {e}")
        return True  # Agar admin nahi hai to allow kar dega taki bot na ruke

def short_with_linksterr(long_url):
    """
    Linksterr API - Correct format
    Docs ke mutabik API key header me Bearer token ke roop me jata hai
    """
    try:
        # Linksterr ka official API endpoint
        api_url = "https://linksterr.com/api/links"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "url": long_url
            # "alias": "custom" # chahe to custom alias bhi de sakta hai
        }
        
        res = requests.post(api_url, json=payload, headers=headers, timeout=15)
        print(f"Linksterr Response: {res.status_code} - {res.text}")
        
        if res.status_code in [200, 201]:
            data = res.json()
            # Response format: { "short_url": "https://linksterr.com/r/xxxx", "link": ... }
            return data.get("short_url") or data.get("link") or data.get("data", {}).get("short_url")
        else:
            # Fallback: Kuch APIs query param se bhi kaam karti hai
            fallback_url = f"https://linksterr.com/api?api={API_KEY}&url={long_url}"
            res2 = requests.get(fallback_url, timeout=10)
            if res2.status_code == 200:
                j = res2.json()
                return j.get("shortenedUrl") or j.get("short_url")
            return None
            
    except Exception as e:
        print(f"Shorten error: {e}")
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
            f"⚠️ Bot use karne se pehle channel join karna zaruri hai.\n\n"
            f"👉 @{CHANNEL_USERNAME} ko join karo, fir 'I Joined' dabao.",
            reply_markup=join_keyboard()
        )
        return
    
    bot.send_message(
        message.chat.id,
        "💰 *NR Hackz Earning Bot Ready!*\n\n"
        "Koi bhi link bhejo, main Linksterr se earning link bana dunga.\n\n"
        "🌍 US - $3.25 / 1000 clicks\n"
        "🇩🇪 Germany - $10.50 / 1000 clicks\n\n"
        "Link bhejo 👇",
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

    loading = bot.reply_to(message, "⏳ Linksterr par link bana raha hu...")
    s_link = short_with_linksterr(long_url)

    if s_link:
        bot.edit_message_text(
            f"✅ *Link Ready!*\n\n"
            f"💰 Earning Link:\n{s_link}\n\n"
            f"Har click ka paisa tere Linksterr dashboard me ayega:\n"
            f"https://linksterr.com/dashboard",
            chat_id=message.chat.id,
            message_id=loading.message_id,
            parse_mode="Markdown"
        )
    else:
        bot.edit_message_text(
            "❌ API Error. Render ke logs check karo.\n"
            "Ho sakta hai API endpoint galat ho. Linksterr dashboard -> API Docs se endpoint confirm karo.",
            chat_id=message.chat.id,
            message_id=loading.message_id
        )

print("Bot Started...")
bot.infinity_polling()
            
