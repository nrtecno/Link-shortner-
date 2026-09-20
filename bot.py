import os
import re
import time
import logging
import threading

import requests
import telebot
from telebot import types
from flask import Flask

# ---------------- CONFIG ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

BOT_TOKEN         = os.environ["BOT_TOKEN"]
LINKSTERR_API_KEY = os.environ["LINKSTERR_API_KEY"]
CHANNEL_USERNAME  = os.environ.get("CHANNEL_USERNAME", "nr_hackz").lstrip("@")
CHANNEL_LINK      = f"https://t.me/{CHANNEL_USERNAME}"

URL_REGEX = re.compile(r"https?://[^\s]+")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown", threaded=True)


# ---------------- FORCE JOIN CHECK ----------------
def is_user_joined(user_id: int) -> bool:
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception as e:
        log.warning(f"Force-join check error for {user_id}: {e}")
        return False


def join_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 @nr_hackz Join Karo", url=CHANNEL_LINK))
    kb.add(types.InlineKeyboardButton("✅ I Joined - Check Karo", callback_data="check_join"))
    return kb


def main_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
    kb.add(types.InlineKeyboardButton("❓ Help", callback_data="help"))
    return kb


# ---------------- LINKSTERR SHORTENER ----------------
def shorten_link(long_url: str):
    """Linksterr.com API se short link banata hai. (short_url, error) return karta hai."""
    api_url = "https://linksterr.com/api"
    params = {"api": LINKSTERR_API_KEY, "url": long_url}

    try:
        resp = requests.get(api_url, params=params, timeout=30)
        log.info(f"Linksterr [{resp.status_code}]: {resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError:
            return None, f"API error: {resp.text[:120]}"

        if isinstance(data, dict):
            short = (
                data.get("shortenedUrl")
                or data.get("short")
                or data.get("short_url")
                or (data.get("result") or {}).get("url")
            )
            if short:
                return short, None
            if data.get("status") == "error":
                return None, data.get("message", "Unknown error")
        return None, "Short link nahi mila"
    except requests.Timeout:
        return None, "API timeout"
    except Exception as e:
        log.exception("Shorten error")
        return None, str(e)


# ---------------- HANDLERS ----------------
@bot.message_handler(commands=["start"])
def start_handler(message):
    user = message.from_user
    if not is_user_joined(user.id):
        bot.send_message(
            message.chat.id,
            f"👋 *Namaste {user.first_name}!*\n\n"
            "Bot use karne ke liye pehle hamara channel join karna zaroori hai.\n"
            "Join karne ke baad *✅ I Joined - Check Karo* pe click karo.",
            reply_markup=join_keyboard(),
            disable_web_page_preview=True,
        )
        return

    bot.send_message(
        message.chat.id,
        f"✅ *Welcome {user.first_name}!*\n\n"
        "Ab apna *long link* bhejo (YouTube, Drive, kuch bhi).\n"
        "Main usko *earning short link* me convert kar dunga 💰\n\n"
        "*Example:*\n`https://youtube.com/watch?v=xxxxx`",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


@bot.message_handler(commands=["help"])
def help_handler(message):
    bot.send_message(
        message.chat.id,
        "*📖 Kaise use kare:*\n\n"
        "1. Channel join karo\n"
        "2. Bot ko koi bhi link bhejo\n"
        "3. Bot short earning link dega\n"
        "4. Woh link share karo — har click se paisa milega\n\n"
        "*Commands:*\n"
        "/start - Bot start karo\n"
        "/help - Ye message\n",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_cb(callback):
    if is_user_joined(callback.from_user.id):
        bot.edit_message_text(
            f"✅ *Verified {callback.from_user.first_name}!*\n\n"
            "Ab apna *long link* bhejo — main earning link bana dunga 💰",
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    else:
        bot.answer_callback_query(callback.id, "❌ Pehle channel join karo!", show_alert=True)


@bot.callback_query_handler(func=lambda c: c.data == "help")
def help_cb(callback):
    bot.answer_callback_query(
        callback.id,
        "Link bhejo → short link milega → share karo → paisa kamao 💰",
        show_alert=True,
    )


@bot.message_handler(func=lambda m: m.text and URL_REGEX.search(m.text))
def shorten_handler(message):
    user_id = message.from_user.id

    if not is_user_joined(user_id):
        bot.reply_to(message, "⚠️ Pehle channel join karo!", reply_markup=join_keyboard())
        return

    urls = URL_REGEX.findall(message.text)
    if not urls:
        bot.reply_to(message, "❌ Valid link bhejo.")
        return
    long_url = urls[0]

    if "linksterr.com" in long_url:
        bot.reply_to(message, "⚠️ Ye already ek short link hai. Original link bhejo.")
        return

    status_msg = bot.reply_to(message, "⏳ Link short kar raha hu...")

    short_url, error = shorten_link(long_url)
    if not short_url:
        bot.edit_message_text(
            f"❌ *Fail ho gaya!*\n`{error}`",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
        )
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔗 Open Link", url=short_url))
    kb.add(types.InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))

    bot.edit_message_text(
        "✅ *Earning Link Ready!* 💰\n\n"
        f"`{short_url}`\n\n"
        "👆 Isko copy karke share karo. Har click se paisa milega!",
        chat_id=status_msg.chat.id,
        message_id=status_msg.message_id,
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@bot.message_handler(
    func=lambda m: m.text and not m.text.startswith("/") and not URL_REGEX.search(m.text)
)
def fallback(message):
    if not is_user_joined(message.from_user.id):
        bot.reply_to(message, "⚠️ Pehle channel join karo!", reply_markup=join_keyboard())
        return
    bot.reply_to(
        message,
        "❌ Ye link nahi lag raha. *https://* se start hone wala link bhejo.",
        disable_web_page_preview=True,
    )


# ---------------- HEALTH CHECK (Render ke liye) ----------------
web_app = Flask(__name__)


@web_app.route("/")
def _health():
    return "🤖 Bot is alive!"


# Telegram jab tak purana webhook hit kare, use 200 return karo (chup-chaap ignore)
@web_app.route("/webhook/<path:token>", methods=["POST"])
def _webhook_sink(token):
    return "ok", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web, daemon=True).start()


# ---------------- POLLING WRAPPER ----------------
def clear_webhook():
    """Telegram se webhook hatata hai taaki polling kaam kare."""
    try:
        bot.delete_webhook(drop_pending_updates=True)
        log.info("🧹 Webhook cleared (drop_pending_updates=True)")
    except Exception as e:
        log.warning(f"delete_webhook failed: {e}")


def run_bot():
    """Webhook clear karke polling start karta hai — auto-restart on crash."""
    # Start hote hi webhook clear karo
    clear_webhook()

    # Thoda wait — Telegram ko delete process karne ka time do
    time.sleep(2)
    clear_webhook()  # double-tap safety

    while True:
        try:
            log.info("🚀 Bot polling start...")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=20,
                skip_pending=False,
            )
        except Exception as e:
            log.exception(f"Polling crash: {e}")
            time.sleep(5)
            clear_webhook()
            time.sleep(2)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    log.info("🚀 Earning Link Bot starting (pyTelegramBotAPI)...")
    run_bot()
