import os
import re
import time
import json
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
LINKSTERR_API_KEY = os.environ["LINKSTERR_API_KEY"]           # lnk_xxxxx
CHANNEL_USERNAME  = os.environ.get("CHANNEL_USERNAME", "nr_hackz").lstrip("@")
CHANNEL_LINK      = f"https://t.me/{CHANNEL_USERNAME}"

# Linksterr official API (dashboard se confirmed)
LINKSTERR_BASE    = "https://linksterr.com/user-api/v1"
LINKSTERR_CREATE  = f"{LINKSTERR_BASE}/links/"

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


# ---------------- LINKSTERR API ----------------
def _extract_short(data):
    """Har possible response format se short URL nikaalo."""
    if not isinstance(data, dict):
        return None
    candidates = [
        data.get("shortenedUrl"),
        data.get("short_url"),
        data.get("short"),
        data.get("url"),
        data.get("link"),
        data.get("shortened_url"),
        (data.get("data") or {}).get("url") if isinstance(data.get("data"), dict) else None,
        (data.get("data") or {}).get("short_url") if isinstance(data.get("data"), dict) else None,
        (data.get("result") or {}).get("url") if isinstance(data.get("result"), dict) else None,
    ]
    for c in candidates:
        if c and isinstance(c, str) and c.startswith("http"):
            return c
    return None


def shorten_link(long_url: str):
    """Linksterr user-api/v1 se short link banata hai."""
    if not LINKSTERR_API_KEY or not LINKSTERR_API_KEY.startswith("lnk_"):
        return None, "LINKSTERR_API_KEY galat hai (lnk_ se start honi chahiye)."

    headers = {
        "Authorization": f"Bearer {LINKSTERR_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Body field name ke multiple possibilities try karo
    body_variants = [
        {"url": long_url},
        {"destination": long_url},
        {"long_url": long_url},
        {"target": long_url},
        {"original_url": long_url},
    ]

    last_error = "Unknown error"

    for i, body in enumerate(body_variants, 1):
        try:
            resp = requests.post(
                LINKSTERR_CREATE,
                headers=headers,
                json=body,
                timeout=30,
            )
            log.info(f"Linksterr POST [{resp.status_code}] body={list(body.keys())}: {resp.text[:300]}")

            # HTML check
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                return None, "Linksterr ne HTML return kiya — endpoint galat hai."

            # Success?
            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except ValueError:
                    return None, f"Invalid JSON: {resp.text[:200]}"

                short = _extract_short(data)
                if short:
                    return short, None

                # Agar slug alag field me hai
                slug = data.get("slug") or data.get("code") or (data.get("data") or {}).get("slug")
                if slug:
                    return f"https://linksterr.com/{slug}", None

                return None, f"Short link nahi mila. Response: {json.dumps(data)[:250]}"

            # Error — agar 400/422 hai toh shayad body field galat hai, agli try karo
            if resp.status_code in (400, 422):
                try:
                    err_json = resp.json()
                    last_error = err_json.get("message") or err_json.get("error") or json.dumps(err_json)[:200]
                except ValueError:
                    last_error = resp.text[:200]
                continue

            # 401/403 — auth problem, agli try bekaar
            if resp.status_code in (401, 403):
                return None, (
                    f"❌ Auth fail ({resp.status_code}). "
                    "API key ya Bearer token format check karo."
                )

            # 429 rate limit
            if resp.status_code == 429:
                return None, "⏳ Rate limit hit (30/min). Thodi der baad try karo."

            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"

        except requests.Timeout:
            return None, "API timeout"
        except requests.exceptions.ConnectionError:
            return None, "Connection error — internet/DNS check karo"
        except Exception as e:
            log.exception(f"Attempt #{i} crashed")
            last_error = str(e)
            continue

    return None, f"Sab attempts fail. Last error: {last_error}"


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
            f"❌ *Fail ho gaya!*\n\n{error}",
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


# ---------------- HEALTH CHECK (Render) ----------------
web_app = Flask(__name__)


@web_app.route("/")
def _health():
    return "🤖 Bot is alive!"


@web_app.route("/webhook/<path:token>", methods=["POST"])
def _webhook_sink(token):
    return "ok", 200


def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)


threading.Thread(target=run_web, daemon=True).start()


# ---------------- POLLING ----------------
def clear_webhook():
    try:
        bot.delete_webhook(drop_pending_updates=True)
        log.info("🧹 Webhook cleared")
    except Exception as e:
        log.warning(f"delete_webhook failed: {e}")


def run_bot():
    clear_webhook()
    time.sleep(2)
    clear_webhook()

    while True:
        try:
            log.info("🚀 Bot polling start...")
            bot.infinity_polling(timeout=30, long_polling_timeout=20, skip_pending=False)
        except Exception as e:
            log.exception(f"Polling crash: {e}")
            time.sleep(5)
            clear_webhook()
            time.sleep(2)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    log.info("🚀 Earning Link Bot starting...")
    log.info(f"📡 Linksterr endpoint: {LINKSTERR_CREATE}")
    run_bot()
