import os
import re
import logging
import asyncio
from threading import Thread

import aiohttp
from flask import Flask
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant

# ---------------- CONFIG ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

API_ID              = int(os.environ["API_ID"])
API_HASH            = os.environ["API_HASH"]
BOT_TOKEN           = os.environ["BOT_TOKEN"]
LINKSTERR_API_KEY   = os.environ["LINKSTERR_API_KEY"]
CHANNEL_USERNAME    = os.environ.get("CHANNEL_USERNAME", "nr_hackz").lstrip("@")
CHANNEL_LINK        = f"https://t.me/{CHANNEL_USERNAME}"

URL_REGEX = r"https?://[^\s]+"

# ---------------- BOT ----------------
app = Client(
    "earning_link_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=8,
)

# ---------------- FORCE JOIN CHECK ----------------
async def is_user_joined(user_id: int) -> bool:
    try:
        member = await app.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in (
            ChatMemberStatus.OWNER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.RESTRICTED,
        ):
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        log.error(f"Force-join check error: {e}")
        return False


def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 @nr_hackz Join Karo", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ I Joined - Check Karo", callback_data="check_join")],
    ])


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton("❓ Help", callback_data="help")],
    ])


# ---------------- LINKSTERR SHORTENER ----------------
async def shorten_link(long_url: str):
    """Linksterr.com API se short link banata hai."""
    api_url = "https://linksterr.com/api"
    params = {"api": LINKSTERR_API_KEY, "url": long_url}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, timeout=30) as resp:
                text = await resp.text()
                log.info(f"Linksterr response [{resp.status}]: {text[:200]}")
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    return None, f"API error: {text[:120]}"

                # Different response formats handle kar raha hai
                if isinstance(data, dict):
                    short = (
                        data.get("shortenedUrl")
                        or data.get("short")
                        or data.get("short_url")
                        or data.get("result", {}).get("url")
                    )
                    if short:
                        return short, None
                    if data.get("status") == "error":
                        return None, data.get("message", "Unknown error")
                return None, "Short link nahi mila"
    except asyncio.TimeoutError:
        return None, "API timeout"
    except Exception as e:
        log.exception("Shorten error")
        return None, str(e)


# ---------------- HANDLERS ----------------
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user = message.from_user
    joined = await is_user_joined(user.id)

    if not joined:
        await message.reply_text(
            f"👋 **Namaste {user.first_name}!**\n\n"
            "Bot use karne ke liye pehle hamara channel join karna zaroori hai.\n"
            "Join karne ke baad **✅ I Joined - Check Karo** pe click karo.",
            reply_markup=join_keyboard(),
            disable_web_page_preview=True,
        )
        return

    await message.reply_text(
        f"✅ **Welcome {user.first_name}!**\n\n"
        "Ab apna **long link** bhejo (YouTube, Drive, kuch bhi).\n"
        "Main usko **earning short link** me convert kar dunga 💰\n\n"
        "**Example:**\n`https://youtube.com/watch?v=xxxxx`",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


@app.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    await message.reply_text(
        "**📖 Kaise use kare:**\n\n"
        "1. Channel join karo\n"
        "2. Bot ko koi bhi link bhejo\n"
        "3. Bot short earning link dega\n"
        "4. Woh link share karo — har click se paisa milega\n\n"
        "**Commands:**\n"
        "/start - Bot start karo\n"
        "/help - Ye message\n",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True,
    )


@app.on_callback_query(filters.regex("^check_join$"))
async def check_join_cb(client, callback):
    joined = await is_user_joined(callback.from_user.id)
    if joined:
        await callback.message.edit_text(
            f"✅ **Verified {callback.from_user.first_name}!**\n\n"
            "Ab apna **long link** bhejo — main earning link bana dunga 💰",
            reply_markup=main_keyboard(),
            disable_web_page_preview=True,
        )
    else:
        await callback.answer("❌ Pehle channel join karo!", show_alert=True)


@app.on_callback_query(filters.regex("^help$"))
async def help_cb(client, callback):
    await callback.answer(
        "Link bhejo → short link milega → share karo → paisa kamao 💰",
        show_alert=True,
    )


@app.on_message(filters.private & filters.regex(URL_REGEX))
async def shorten_handler(client, message):
    user_id = message.from_user.id

    # Force-join check
    if not await is_user_joined(user_id):
        await message.reply_text(
            "⚠️ Pehle channel join karo!",
            reply_markup=join_keyboard(),
        )
        return

    # Extract first URL
    urls = re.findall(URL_REGEX, message.text)
    if not urls:
        await message.reply_text("❌ Valid link bhejo.")
        return
    long_url = urls[0]

    # Linksterr domain ko dobara short na karein
    if "linksterr.com" in long_url:
        await message.reply_text("⚠️ Ye already ek short link hai. Original link bhejo.")
        return

    status_msg = await message.reply_text("⏳ Link short kar raha hu...")

    short_url, error = await shorten_link(long_url)
    if not short_url:
        await status_msg.edit_text(f"❌ **Fail ho gaya!**\n`{error}`")
        return

    await status_msg.edit_text(
        "✅ **Earning Link Ready!** 💰\n\n"
        f"`{short_url}`\n\n"
        "👆 Isko copy karke share karo. Har click se paisa milega!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Open Link", url=short_url)],
            [InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK)],
        ]),
        disable_web_page_preview=True,
    )


@app.on_message(filters.private & filters.text & ~filters.regex(URL_REGEX) & ~filters.command(["start", "help"]))
async def fallback(client, message):
    if not await is_user_joined(message.from_user.id):
        await message.reply_text("⚠️ Pehle channel join karo!", reply_markup=join_keyboard())
        return
    await message.reply_text(
        "❌ Ye link nahi lag raha. **https://** se start hone wala link bhejo.",
        disable_web_page_preview=True,
    )


# ---------------- HEALTH CHECK (Render ke liye) ----------------
web_app = Flask(__name__)

@web_app.route("/")
def _health():
    return "🤖 Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

Thread(target=run_web, daemon=True).start()


# ---------------- RUN ----------------
if __name__ == "__main__":
    log.info("🚀 Earning Link Bot starting...")
    app.run()
