# main.py
import os
import json
import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, Any, List, Optional

import aiohttp
from bs4 import BeautifulSoup
import html as pyhtml

from telegram import Update, MessageEntity
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")        # keep as string for comparison
GROUP_ID = os.getenv("GROUP_ID")        # optional
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
CONFIG_FILE = "config.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN chưa được thiết lập!")

# ===== LOGGING =====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("girlhonghot")

# ===== CONFIG HELPERS =====
def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("users", {})  # map id -> display name
    cfg.setdefault("news_sources", ["https://coin68.com/feed/"])
    cfg.setdefault("report_time", "08:00")
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_admin(uid: int) -> bool:
    return str(uid) == str(ADMIN_ID)


def is_registered(uid: int) -> bool:
    return str(uid) in load_config().get("users", {})


# ===== TELEGRAM APP =====
application = ApplicationBuilder().token(BOT_TOKEN).build()

# ===== UTILS & CACHES =====
COIN_CACHE: Dict[str, Any] = {"last_update": 0, "data": []}


async def fetch_json(url: str, timeout: int = 10) -> Any:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.json()
    except Exception as e:
        logger.warning("fetch_json lỗi %s: %s", url, e)
        return {}


async def fetch_text(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                resp.raise_for_status()
                return await resp.read()
    except Exception as e:
        logger.warning("fetch_text lỗi %s: %s", url, e)
        return None


async def fetch_items_from_feed(src: str) -> List[Any]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; girlhonghotBot/1.0)"}
        async with aiohttp.ClientSession() as session:
            async with session.get(src, headers=headers, timeout=8) as r:
                content = await r.read()
        soup = BeautifulSoup(content, "xml")
        items = soup.find_all("item")
        if not items:
            soup = BeautifulSoup(content, "html.parser")
            items = soup.find_all("item")
        return items
    except Exception as e:
        logger.warning("Lỗi RSS %s: %s", src, e)
        return []


# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not (is_registered(user.id) or is_admin(user.id)):
        await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
        return
    await update.message.reply_text(
        f"👋 Chào {user.first_name}! Tôi là @girlhonghot – trợ lý crypto của bạn 💖"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💡 *Hướng dẫn sử dụng:*\n"
        "• /start – Bắt đầu trò chuyện\n"
        "• /dangky – Gửi yêu cầu đăng ký\n"
        "• /price <coin> – Xem giá coin\n"
        "• /top – Top 10 coin theo vốn hóa\n"
        "• /news – Tin tức RSS\n"
        "• /report – Báo cáo thủ công\n"
        "• /help – Hướng dẫn\n"
        "👑 *Admin:* /them, /xoa, /listuser, /addnews, /delnews, /settime"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ===== USER MANAGEMENT =====
async def dangky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cfg = load_config()
    if str(user.id) in cfg["users"]:
        await update.message.reply_text("✅ Bạn đã được kích hoạt!")
        return
    msg = f"📩 *YÊU CẦU ĐĂNG KÝ*\n👤 @{user.username or 'Không có'}\n🆔 `{user.id}`"
    if ADMIN_ID:
        try:
            await context.bot.send_message(int(ADMIN_ID), msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning("Lỗi gửi tin admin: %s", e)
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin, vui lòng chờ duyệt 💬")


async def them(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp: /them <id>")
        return
    uid = context.args[0]
    cfg = load_config()
    try:
        user_info = await context.bot.get_chat(uid)
        cfg["users"][uid] = user_info.username or user_info.first_name or "User"
        save_config(cfg)
        await update.message.reply_text(f"✅ Đã kích hoạt {cfg['users'][uid]} ({uid})")
        try:
            await context.bot.send_message(int(uid), "🎉 Bạn đã được kích hoạt! 💖")
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")


async def xoa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    if not context.args:
        await update.message.reply_text("❌ Sai cú pháp: /xoa <id>")
        return
    uid = context.args[0]
    cfg = load_config()
    if uid not in cfg["users"]:
        await update.message.reply_text("❌ Không tìm thấy user này.")
        return
    del cfg["users"][uid]
    save_config(cfg)
    await update.message.reply_text(f"🗑️ Đã xóa {uid}")


async def listuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    cfg = load_config()
    if not cfg["users"]:
        await update.message.reply_text("📭 Chưa có người dùng nào.")
        return
    msg = "👥 *Danh sách người dùng:*\n\n"
    for k, v in cfg["users"].items():
        msg += f"• {v} – `{k}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ===== NEWS HANDLERS =====
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    msg = "📰 <b>TIN TỨC CRYPTO MỚI NHẤT</b>\n\n"
    for src in cfg.get("news_sources", []):
        items = await fetch_items_from_feed(src)
        if not items:
            msg += f"⚠️ Không tìm thấy tin nào từ {src}\n\n"
            continue
        for i in items[:5]:
            title = pyhtml.escape(
                getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề"
            )
            link = None
            if i.find("link") and getattr(i.find("link"), "text", "").strip().startswith("http"):
                link = i.find("link").text.strip()
            elif i.find("guid") and "http" in getattr(i.find("guid"), "text", ""):
                link = i.find("guid").text.strip()
            else:
                link = src
            msg += f"• <a href=\"{link}\">{title}</a>\n"
        msg += "\n"
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=False)


async def addnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    if not context.args:
        await update.message.reply_text("⚙️ Dùng: /addnews <url>")
        return
    url = context.args[0]
    cfg = load_config()
    if url in cfg["news_sources"]:
        await update.message.reply_text("⚠️ Nguồn đã tồn tại.")
        return
    cfg["news_sources"].append(url)
    save_config(cfg)
    await update.message.reply_text("✅ Đã thêm nguồn tin.")


async def delnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    if not context.args:
        await update.message.reply_text("⚙️ Dùng: /delnews <url>")
        return
    url = context.args[0]
    cfg = load_config()
    if url not in cfg["news_sources"]:
        await update.message.reply_text("❌ Không có nguồn này.")
        return
    cfg["news_sources"].remove(url)
    save_config(cfg)
    await update.message.reply_text("🗑️ Đã xóa nguồn tin.")


async def listnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    msg = "🗞️ *Danh sách nguồn tin:*\n\n"
    for s in cfg["news_sources"]:
        msg += f"• {s}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ===== PRICE / TOP =====
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_registered(update.effective_user.id):
        await update.message.reply_text("🔒 Cần /dangky trước.")
        return
    if not context.args:
        await update.message.reply_text("⚙️ Dùng: /price btc hoặc /price bitcoin")
        return
    query = context.args[0].lower()

    # update coin cache once per hour
    now_ts = int(datetime.utcnow().timestamp())
    if now_ts - COIN_CACHE["last_update"] > 3600 or not COIN_CACHE["data"]:
        data = await fetch_json("https://api.coingecko.com/api/v3/coins/list")
        if isinstance(data, list):
            COIN_CACHE["data"] = [c for c in data if isinstance(c, dict)]
        else:
            COIN_CACHE["data"] = []
        COIN_CACHE["last_update"] = now_ts

    coins = COIN_CACHE["data"]
    match = None
    try:
        match = next((c for c in coins if c.get("id", "").lower() == query), None)
    except Exception:
        match = None

    if not match:
        symbol_matches = [c for c in coins if c.get("symbol", "").lower() == query]
        if len(symbol_matches) == 1:
            match = symbol_matches[0]
        elif len(symbol_matches) > 1:
            # try search endpoint to pick best candidate
            s = await fetch_json(f"https://api.coingecko.com/api/v3/search?query={query}")
            candidates = [c for c in s.get("coins", []) if isinstance(c, dict) and c.get("symbol", "").lower() == query]
            if candidates:
                candidates_sorted = sorted(candidates, key=lambda x: x.get("market_cap_rank") or 10**9)
                chosen_id = candidates_sorted[0]["id"]
                match = next((c for c in coins if c.get("id") == chosen_id), None)
        else:
            match = next((c for c in coins if c.get("name", "").lower() == query), None)

    if not match:
        await update.message.reply_text("❌ Không tìm thấy coin.")
        return

    cid = match["id"]
    res = await fetch_json(f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd")
    price_val = None
    if isinstance(res, dict):
        price_val = res.get(cid, {}).get("usd")
    if price_val is not None:
        await update.message.reply_text(
            f"💰 Giá {match.get('name', cid).title()} ({match.get('symbol','').upper()}): ${price_val:,}"
        )
    else:
        await update.message.reply_text("⚠️ Không lấy được giá coin này.")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_registered(update.effective_user.id):
        await update.message.reply_text("🔒 Cần /dangky trước.")
        return
    data = await fetch_json("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=10")
    if not isinstance(data, list):
        await update.message.reply_text("⚠️ Lỗi dữ liệu từ API.")
        return
    msg = "🏆 *Top 10 Coin theo vốn hóa:*\n\n"
    for i, c in enumerate(data[:10], 1):
        name = c.get("name", "Unknown")
        symbol = c.get("symbol", "").upper()
        price = c.get("current_price")
        price_str = f"${price:,.2f}" if isinstance(price, (int, float)) else "N/A"
        msg += f"{i}. {name} ({symbol}): {price_str}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ===== AI CHAT =====
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return

    # In groups require mention
    if msg.chat.type in ["group", "supergroup"]:
        if not msg.entities or not any(e.type == MessageEntity.MENTION and "@girlhonghot" in msg.text for e in msg.entities):
            return

    prompt = msg.text.replace("@girlhonghot", "").strip()
    if not prompt:
        return
    if not CHATANYWHERE_API_KEY:
        await msg.reply_text("⚠️ AI chat chưa được cấu hình API key.")
        return

    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.chatanywhere.tech/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {CHATANYWHERE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "Bạn là trợ lý crypto dễ thương, trả lời ngắn gọn và bằng tiếng Việt."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500,
                },
                timeout=30,
            ) as resp:
                if resp.status != 200:
                    await msg.reply_text(f"⚠️ Lỗi AI ({resp.status})")
                    return
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi khi gọi AI: {e}")


# ===== REPORTS =====
async def generate_report() -> str:
    cfg = load_config()
    # Market overview
    global_data = await fetch_json("https://api.coingecko.com/api/v3/global")
    data = global_data.get("data", {})
    total_mcap = data.get("total_market_cap", {}).get("usd", 0)
    total_volume = data.get("total_volume", {}).get("usd", 0)
    btc_dom = data.get("market_cap_percentage", {}).get("btc", 0)

    msg = "📊 <b>BÁO CÁO TỔNG HỢP CRYPTO</b>\n\n"
    msg += "🌍 <b>TỔNG QUAN THỊ TRƯỜNG</b>\n"
    msg += f"• Tổng vốn hóa: ${total_mcap:,.0f}\n"
    msg += f"• Khối lượng 24h: ${total_volume:,.0f}\n"
    msg += f"• BTC Dominance: {btc_dom:.2f}%\n\n"

    # News highlights
    msg += "📰 <b>TIN TỨC NỔI BẬT</b>\n"
    for src in cfg.get("news_sources", []):
        items = await fetch_items_from_feed(src)
        if not items:
            msg += f"⚠️ Không có bài viết từ {src}\n\n"
            continue
        for i in items[:3]:
            title = pyhtml.escape(
                getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề"
            )
            link = None
            if i.find("link") and getattr(i.find("link"), "text", "").strip().startswith("http"):
                link = i.find("link").text.strip()
            elif i.find("guid") and "http" in getattr(i.find("guid"), "text", ""):
                link = i.find("guid").text.strip()
            else:
                link = src
            msg += f"• <a href=\"{link}\">{title}</a>\n"
        msg += "\n"

    # Snapshot (few coins)
    try:
        coins = ["bitcoin", "ethereum", "bnb", "solana", "xrp"]
        coin_icons = {"bitcoin": "🟠", "ethereum": "💎", "bnb": "🟡", "solana": "🟣", "xrp": "💠"}
        data_coins = await fetch_json(
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + ",".join(coins)
        )
        for c in data_coins:
            icon = coin_icons.get(c.get("id", ""), "💰")
            msg += f"{icon} <b>{c.get('name')}</b>: ${c.get('current_price'):,} ({c.get('price_change_percentage_24h', 0):+.2f}%)\n"
    except Exception:
        msg += "⚠️ Không thể lấy snapshot coin.\n"

    return msg


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (is_admin(update.effective_user.id) or is_registered(update.effective_user.id)):
        await update.message.reply_text("🔒 Cần /dangky trước.")
        return
    msg = await generate_report()
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


# ===== SCHEDULED DAILY REPORT TASK =====
async def send_daily_report_task(app):
    # Wait until bot is started
    await app.wait_until_ready()  # ensures application.bot exists and ready (PTB helper)
    logger.info("Daily report task started.")
    while True:
        cfg = load_config()
        try:
            h, m = map(int, cfg.get("report_time", "08:00").split(":"))
        except Exception:
            h, m = 8, 0
        now = datetime.now()
        report_dt = datetime.combine(now.date(), dt_time(hour=h, minute=m))
        if now >= report_dt:
            report_dt += timedelta(days=1)
        wait_seconds = (report_dt - now).total_seconds()
        logger.info("Next report in %.0f seconds (at %s)", wait_seconds, report_dt.isoformat())
        await asyncio.sleep(wait_seconds)

        msg = await generate_report()

        # send to group if configured
        if GROUP_ID:
            try:
                await app.bot.send_message(int(GROUP_ID), msg, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                logger.warning("Lỗi gửi báo cáo vào nhóm: %s", e)

        # send to users
        for uid in list(load_config().get("users", {}).keys()):
            try:
                await app.bot.send_message(int(uid), msg, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                logger.warning("Lỗi gửi báo cáo cho %s: %s", uid, e)


# ===== SETTIME =====
async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Chỉ admin có thể thay đổi giờ báo cáo.")
        return
    if not context.args:
        await update.message.reply_text("⚙️ Dùng: /settime HH:MM (vd: /settime 09:30)")
        return
    new_time = context.args[0]
    try:
        hh, mm = new_time.split(":")
        hh_i = int(hh)
        mm_i = int(mm)
        if not (0 <= hh_i < 24 and 0 <= mm_i < 60):
            raise ValueError
    except Exception:
        await update.message.reply_text("❌ Định dạng không hợp lệ. Dùng HH:MM (24h).")
        return
    cfg = load_config()
    cfg["report_time"] = new_time
    save_config(cfg)
    await update.message.reply_text(f"⏰ Đã cập nhật giờ báo cáo thành {new_time}")


# ===== REGISTER HANDLERS =====
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("dangky", dangky))
application.add_handler(CommandHandler("them", them))
application.add_handler(CommandHandler("xoa", xoa))
application.add_handler(CommandHandler("listuser", listuser))
application.add_handler(CommandHandler("news", news))
application.add_handler(CommandHandler("addnews", addnews))
application.add_handler(CommandHandler("delnews", delnews))
application.add_handler(CommandHandler("listnews", listnews))
application.add_handler(CommandHandler("price", price))
application.add_handler(CommandHandler("top", top))
application.add_handler(CommandHandler("report", report_cmd))
application.add_handler(CommandHandler("settime", settime))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))


# ===== ERROR HANDLER (logging) =====
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Exception while handling an update: %s", context.error)
    # optional: notify admin
    try:
        if ADMIN_ID:
            await application.bot.send_message(int(ADMIN_ID), f"⚠️ Lỗi bot: {context.error}")
    except Exception:
        pass


application.add_error_handler(error_handler)


# ===== STARTUP / MAIN =====
# ===== CHẠY BOT BẰNG POLLING =====
async def send_daily_report_task():
    """Tác vụ chạy nền gửi báo cáo hàng ngày"""
    await asyncio.sleep(5)  # chờ bot khởi động ổn định
    while True:
        cfg = load_config()
        h, m = map(int, cfg.get("report_time", "08:00").split(":"))
        now = datetime.now()
        report_dt = datetime.combine(now.date(), dt_time(hour=h, minute=m))
        if now > report_dt:
            report_dt += timedelta(days=1)
        await asyncio.sleep((report_dt - now).total_seconds())
        try:
            msg = await generate_report_msg()
            if GROUP_ID:
                await application.bot.send_message(
                    int(GROUP_ID), msg, parse_mode="HTML", disable_web_page_preview=True
                )
            for uid in load_config().get("users", {}):
                await application.bot.send_message(
                    int(uid), msg, parse_mode="HTML", disable_web_page_preview=True
                )
        except Exception as e:
            logger.error(f"⚠️ Lỗi gửi báo cáo: {e}")


async def main():
    logger.info("Khởi tạo application...")
    asyncio.create_task(send_daily_report_task())

    # Xóa webhook cũ (nếu có)
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Lỗi xóa webhook: {e}")

    logger.info("🤖 Bot đang chạy bằng polling...")
    await application.run_polling(stop_signals=None)


if __name__ == "__main__":
    asyncio.run(main())

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
