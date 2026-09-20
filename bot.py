import os
import re
import time
import json
import logging
import sqlite3
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

# ⚠️ Apna Telegram user ID yahan daalo
# @userinfobot se pata karo
OWNER_ID          = int(os.environ.get("OWNER_ID", "0"))

LINKSTERR_BASE    = "https://linksterr.com/user-api/v1"
LINKSTERR_CREATE  = f"{LINKSTERR_BASE}/links/"

URL_REGEX = re.compile(r"https?://[^\s]+")
DB_PATH   = "users.db"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown", threaded=True)

# Admin states: {owner_id: "ON"/"OFF"}
CAST_STATE = {"enabled": False}


# ---------------- DATABASE ----------------
def db_init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            first_name  TEXT,
            username    TEXT,
            joined_at   INTEGER,
            last_seen   INTEGER,
            links_made  INTEGER DEFAULT 0,
            is_blocked  INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()
    log.info("📦 Database ready")


def db_save_user(user):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (user_id, first_name, username, joined_at, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = excluded.first_name,
                username   = excluded.username,
                last_seen  = excluded.last_seen,
                is_blocked = 0
        """, (user.id, user.first_name or "", user.username or "", int(time.time()), int(time.time())))
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"db_save_user error: {e}")


def db_count_users():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 0")
        total = c.fetchone()[0]
        conn.close()
        return total
    except Exception:
        return 0


def db_all_user_ids():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_blocked = 0")
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids


def db_mark_blocked(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def db_increment_links(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE users SET links_made = links_made + 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------- FORCE JOIN ----------------
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


def send_join_prompt(chat_id, first_name):
    bot.send_message(
        chat_id,
        f"👋 *Namaste {first_name}!*\n\n"
        "🔒 Bot use karne ke liye pehle hamara channel *join* karna zaroori hai.\n\n"
        "👇 Neeche ke button se join karo, phir *✅ I Joined* pe click karo.",
        reply_markup=join_keyboard(),
        disable_web_page_preview=True,
    )


# ---------------- LINKSTERR ----------------
def _extract_short(data):
    if not isinstance(data, dict):
        return None
    candidates = [
        data.get("shortenedUrl"), data.get("short_url"), data.get("short"),
        data.get("url"), data.get("link"), data.get("shortened_url"),
        (data.get("data") or {}).get("url") if isinstance(data.get("data"), dict) else None,
        (data.get("data") or {}).get("short_url") if isinstance(data.get("data"), dict) else None,
    ]
    for c in candidates:
        if c and isinstance(c, str) and c.startswith("http"):
            return c
    return None


def shorten_link(long_url: str):
    if not LINKSTERR_API_KEY or not LINKSTERR_API_KEY.startswith("lnk_"):
        return None, "LINKSTERR_API_KEY galat hai."

    headers = {
        "Authorization": f"Bearer {LINKSTERR_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body_variants = [
        {"url": long_url}, {"destination": long_url}, {"long_url": long_url},
        {"target": long_url}, {"original_url": long_url},
    ]
    last_error = "Unknown error"

    for i, body in enumerate(body_variants, 1):
        try:
            resp = requests.post(LINKSTERR_CREATE, headers=headers, json=body, timeout=30)
            log.info(f"Linksterr [{resp.status_code}] body={list(body.keys())}: {resp.text[:200]}")

            if "text/html" in resp.headers.get("Content-Type", ""):
                return None, "Linksterr HTML return kar raha hai — endpoint check karo."

            if resp.status_code in (200, 201):
                try:
                    data = resp.json()
                except ValueError:
                    return None, f"Invalid JSON: {resp.text[:200]}"
                short = _extract_short(data)
                if short:
                    return short, None
                slug = data.get("slug") or data.get("code")
                if slug:
                    return f"https://linksterr.com/{slug}", None
                return None, f"Short link nahi mila: {json.dumps(data)[:200]}"

            if resp.status_code in (400, 422):
                try:
                    err_json = resp.json()
                    last_error = err_json.get("message") or err_json.get("error") or json.dumps(err_json)[:200]
                except ValueError:
                    last_error = resp.text[:200]
                continue

            if resp.status_code in (401, 403):
                return None, f"Auth fail ({resp.status_code}) — API key check karo."
            if resp.status_code == 429:
                return None, "⏳ Rate limit hit. Thodi der baad try karo."

            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
        except requests.Timeout:
            return None, "API timeout"
        except Exception as e:
            last_error = str(e)
            continue

    return None, f"Fail. Last error: {last_error}"


# ---------------- BROADCAST ----------------
def broadcast_message(from_chat_id, message):
    """Admin ke message ko sab users ko forward karta hai."""
    user_ids = db_all_user_ids()
    total = len(user_ids)
    if total == 0:
        bot.send_message(from_chat_id, "❌ Abhi koi user nahi hai.")
        return

    sent, failed = 0, 0
    progress = bot.send_message(from_chat_id, f"📤 Broadcasting to {total} users...")

    for uid in user_ids:
        try:
            bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message.message_id)
            sent += 1
        except Exception as e:
            failed += 1
            err = str(e).lower()
            if "blocked" in err or "deactivated" in err or "chat not found" in err:
                db_mark_blocked(uid)
        time.sleep(0.05)  # rate limit safe

    try:
        bot.edit_message_text(
            f"✅ *Broadcast Complete*\n\n"
            f"📤 Sent: `{sent}`\n"
            f"❌ Failed: `{failed}`\n"
            f"👥 Total: `{total}`",
            chat_id=from_chat_id,
            message_id=progress.message_id,
        )
    except Exception:
        pass


# ---------------- HANDLERS ----------------
@bot.message_handler(commands=["start"])
def start_handler(message):
    user = message.from_user

    # Sabse pehle force-join check
    if not is_user_joined(user.id):
        send_join_prompt(message.chat.id, user.first_name)
        return

    # Joined hai — DB me save karo
    db_save_user(user)

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


# --------- /cast (Sirf Owner) ---------
@bot.message_handler(commands=["cast"])
def cast_handler(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Ye command sirf owner use kar sakta hai.")
        return

    total = db_count_users()
    state = "🟢 ON" if CAST_STATE["enabled"] else "🔴 OFF"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🟢 ON", callback_data="cast_on"),
        types.InlineKeyboardButton("🔴 OFF", callback_data="cast_off"),
    )

    bot.send_message(
        message.chat.id,
        f"📢 *Broadcast Panel*\n\n"
        f"👥 Total users: `{total}`\n"
        f"📡 Status: *{state}*\n\n"
        "ON karo → jo message bhejoge woh sab users ko jayega\n"
        "OFF karo → bot normal mode me",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data == "cast_on")
def cast_on_cb(callback):
    if callback.from_user.id != OWNER_ID:
        bot.answer_callback_query(callback.id, "❌ Sirf owner!", show_alert=True)
        return
    CAST_STATE["enabled"] = True
    bot.answer_callback_query(callback.id, "🟢 Broadcast ON — ab message bhejo", show_alert=True)
    bot.send_message(callback.message.chat.id, "🟢 *Broadcast ON*\nAb jo bhi message bhejoge woh sab users ko jayega.\nBand karne ke liye /cast → OFF.")


@bot.callback_query_handler(func=lambda c: c.data == "cast_off")
def cast_off_cb(callback):
    if callback.from_user.id != OWNER_ID:
        bot.answer_callback_query(callback.id, "❌ Sirf owner!", show_alert=True)
        return
    CAST_STATE["enabled"] = False
    bot.answer_callback_query(callback.id, "🔴 Broadcast OFF", show_alert=True)
    bot.send_message(callback.message.chat.id, "🔴 *Broadcast OFF*\nBot normal mode me aa gaya.")


# --------- Broadcast capture (sirf tab jab ON ho) ---------
@bot.message_handler(
    func=lambda m: m.from_user.id == OWNER_ID and CAST_STATE["enabled"]
                  and not (m.text or "").startswith("/"),
    content_types=["text", "photo", "video", "document", "audio", "voice", "sticker", "animation"]
)
def capture_broadcast(message):
    broadcast_message(message.chat.id, message)


# --------- Force-join check callback ---------
@bot.callback_query_handler(func=lambda c: c.data == "check_join")
def check_join_cb(callback):
    if is_user_joined(callback.from_user.id):
        db_save_user(callback.from_user)
        bot.edit_message_text(
            f"✅ *Verified {callback.from_user.first_name}!*\n\n"
            "Ab apna *long link* bhejo — main earning link bana dunga 💰",
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    else:
        bot.answer_callback_query(
            callback.id,
            "❌ Tumne abhi tak channel join nahi kiya. Pehle join karo!",
            show_alert=True,
        )


@bot.callback_query_handler(func=lambda c: c.data == "help")
def help_cb(callback):
    bot.answer_callback_query(
        callback.id,
        "Link bhejo → short link milega → share karo → paisa kamao 💰",
        show_alert=True,
    )


# --------- Link shortening ---------
@bot.message_handler(func=lambda m: m.text and URL_REGEX.search(m.text) and m.from_user.id != OWNER_ID)
def shorten_handler(message):
    user_id = message.from_user.id

    if not is_user_joined(user_id):
        send_join_prompt(message.chat.id, message.from_user.first_name)
        return

    db_save_user(message.from_user)
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

    db_increment_links(user_id)

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


# --------- Fallback ---------
@bot.message_handler(
    func=lambda m: m.text and not m.text.startswith("/")
                  and not URL_REGEX.search(m.text)
                  and m.from_user.id != OWNER_ID
)
def fallback(message):
    if not is_user_joined(message.from_user.id):
        send_join_prompt(message.chat.id, message.from_user.first_name)
        return
    bot.reply_to(
        message,
        "❌ Ye link nahi lag raha. *https://* se start hone wala link bhejo.",
        disable_web_page_preview=True,
    )


# ---------------- HEALTH CHECK ----------------
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
    db_init()
    log.info(f"🚀 Bot starting | Owner ID: {OWNER_ID}")
    run_bot()
