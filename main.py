# main.py
import os
import json
import asyncio
from datetime import datetime, time as dt_time
from flask import Flask, request
from bs4 import BeautifulSoup
import aiohttp
import html as pyhtml
import logging
from telegram import Update, MessageEntity
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)

# ===== CONFIG =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
BASE_URL = os.getenv("BASE_URL","https://girlhonghot.onrender.com")
CONFIG_FILE = "config.json"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN chưa được thiết lập!")

# ===== LOGGING =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== CONFIG HELPERS =====
def load_config():
    try:
        with open(CONFIG_FILE,"r",encoding="utf-8") as f:
            cfg = json.load(f)
    except:
        cfg = {}
    cfg.setdefault("users",{})
    cfg.setdefault("news_sources",["https://coin68.com/feed/"])
    cfg.setdefault("report_time","08:00")
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE,"w",encoding="utf-8") as f:
        json.dump(cfg,f,indent=2,ensure_ascii=False)

def is_admin(uid):
    return str(uid) == str(ADMIN_ID)

def is_registered(uid):
    return str(uid) in load_config().get("users",{})

# ===== FLASK APP =====
app = Flask(__name__)

# ===== TELEGRAM APP =====
application = ApplicationBuilder().token(BOT_TOKEN).build()

# ===== UTILS =====
COIN_CACHE = {"last_update":0,"data":[]}

async def fetch_json(url, timeout=10):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                return await resp.json()
    except:
        return {}

async def fetch_items_from_feed(src):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(src, headers=headers, timeout=8) as r:
                content = await r.read()
        soup = BeautifulSoup(content,"xml")
        items = soup.find_all("item")
        if not items:
            soup = BeautifulSoup(content,"html.parser")
            items = soup.find_all("item")
        return items
    except Exception as e:
        logger.warning(f"⚠️ Lỗi RSS {src}: {e}")
        return []

# ===== HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not (is_registered(user.id) or is_admin(user.id)):
        await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
        return
    await update.message.reply_text(f"👋 Chào {user.first_name}! Tôi là @girlhonghot – trợ lý crypto của bạn 💖")

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

# ===== USER REGISTRATION =====
async def dangky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cfg = load_config()
    if str(user.id) in cfg["users"]:
        await update.message.reply_text("✅ Bạn đã được kích hoạt!")
        return
    msg = f"📩 *YÊU CẦU ĐĂNG KÝ*\n👤 @{user.username or 'Không có'}\n🆔 `{user.id}`"
    if ADMIN_ID:
        try:
            await context.bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Lỗi gửi tin admin: {e}")
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin, vui lòng chờ duyệt 💬")

async def them(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
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
        try: await context.bot.send_message(uid,"🎉 Bạn đã được kích hoạt! 💖")
        except: pass
    except Exception as e:
        await update.message.reply_text(f"❌ Lỗi: {e}")

async def xoa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
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
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("🚫 Không có quyền.")
        return
    cfg = load_config()
    if not cfg["users"]:
        await update.message.reply_text("📭 Chưa có người dùng nào.")
        return
    msg = "👥 *Danh sách người dùng:*\n\n"
    for k,v in cfg["users"].items():
        msg += f"• {v} – `{k}`\n"
    await update.message.reply_text(msg,parse_mode="Markdown")

# ===== NEWS HANDLERS =====
async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    msg = "📰 <b>TIN TỨC CRYPTO MỚI NHẤT</b>\n\n"
    for src in cfg.get("news_sources", []):
        items = await fetch_items_from_feed(src)
        for i in items[:5]:
            title = pyhtml.escape(getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề")
            link = getattr(i.find("link"), "text", src) if i.find("link") else src
            msg += f"• <a href=\"{link}\">{title}</a>\n"
        msg += "\n"
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=False)

async def addnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
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
    if not is_admin(update.message.from_user.id):
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

# ===== PRICE/TOP HANDLERS =====
async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_registered(user_id):
        await update.message.reply_text("🔒 Cần /dangky trước.")
        return
    if not context.args:
        await update.message.reply_text("⚙️ Dùng: /price btc hoặc /price bitcoin")
        return
    query = context.args[0].lower()
    import time
    if time.time() - COIN_CACHE["last_update"] > 3600 or not COIN_CACHE["data"]:
        data = await fetch_json("https://api.coingecko.com/api/v3/coins/list")
        if isinstance(data, list):
            COIN_CACHE["data"] = [c for c in data if isinstance(c, dict)]
        COIN_CACHE["last_update"] = time.time()
    coins = COIN_CACHE["data"]
    match = next((c for c in coins if c.get("id","").lower()==query), None)
    if not match:
        match = next((c for c in coins if c.get("symbol","").lower()==query), None)
    if not match:
        await update.message.reply_text("❌ Không tìm thấy coin.")
        return
    cid = match["id"]
    res = await fetch_json(f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd")
    price_val = res.get(cid, {}).get("usd")
    if price_val is not None:
        await update.message.reply_text(f"💰 Giá {match.get('name',cid).title()} ({match.get('symbol','').upper()}): ${price_val:,}")
    else:
        await update.message.reply_text("⚠️ Không lấy được giá coin này.")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_registered(user_id):
        await update.message.reply_text("🔒 Cần /dangky trước.")
        return
    data = await fetch_json("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=10")
    if not isinstance(data, list):
        await update.message.reply_text("⚠️ Lỗi dữ liệu từ API.")
        return
    msg = "🏆 *Top 10 Coin theo vốn hóa:*\n\n"
    for i, c in enumerate(data[:10],1):
        name = c.get('name','Unknown')
        symbol = c.get('symbol','').upper()
        price = c.get('current_price')
        price_str = f"${price:,.2f}" if isinstance(price,(int,float)) else "N/A"
        msg += f"{i}. {name} ({symbol}): {price_str}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# ===== AI CHAT =====
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    if msg.chat.type in ["group","supergroup"]:
        if not msg.entities or not any(e.type==MessageEntity.MENTION and "@girlhonghot" in msg.text for e in msg.entities):
            return
    prompt = msg.text.replace("@girlhonghot","").strip()
    if not prompt: return
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.chatanywhere.tech/v1/chat/completions",
                headers={"Authorization": f"Bearer {CHATANYWHERE_API_KEY}","Content-Type":"application/json"},
                json={"model":"gpt-4o-mini",
                      "messages":[{"role":"system","content":"Bạn là trợ lý crypto dễ thương, trả lời ngắn gọn và bằng tiếng Việt."},
                                  {"role":"user","content":prompt}],
                      "max_tokens":500},
                timeout=30
            ) as resp:
                if resp.status != 200:
                    await msg.reply_text(f"⚠️ Lỗi AI ({resp.status})")
                    return
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi khi gọi AI: {e}")


# ===== DAILY REPORT =====
async def generate_report_msg():
    cfg = load_config()
    msg = "📊 <b>BÁO CÁO TỔNG HỢP CRYPTO</b>\n\n"
    # Market overview
    global_data = await fetch_json("https://api.coingecko.com/api/v3/global")
    data = global_data.get("data", {})
    total_mcap = data.get("total_market_cap", {}).get("usd", 0)
    total_volume = data.get("total_volume", {}).get("usd", 0)
    btc_dom = data.get("market_cap_percentage", {}).get("btc", 0)
    msg += f"🌍 Tổng vốn hóa: ${total_mcap:,.0f}\n"
    msg += f"• Khối lượng 24h: ${total_volume:,.0f}\n"
    msg += f"• BTC Dominance: {btc_dom:.2f}%\n\n"
    # News highlights
    msg += "📰 <b>TIN TỨC NỔI BẬT</b>\n"
    for src in cfg.get("news_sources", []):
        items = await fetch_items_from_feed(src)
        for i in items[:3]:
            title = pyhtml.escape(getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề")
            link = getattr(i.find("link"), "text", src) if i.find("link") else src
            msg += f"• <a href=\"{link}\">{title}</a>\n"
        msg += "\n"
    return msg

async def send_daily_report():
    await application.bot.wait_until_ready()
    while True:
        cfg = load_config()
        report_time_str = cfg.get("report_time", "08:00")
        h, m = map(int, report_time_str.split(":"))
        now = datetime.now()
        report_dt = datetime.combine(now.date(), dt_time(hour=h, minute=m))
        if now > report_dt:
            report_dt += timedelta(days=1)
        wait_seconds = (report_dt - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        msg = await generate_report_msg()

        # Gửi vào nhóm (GROUP_ID) nếu có
        if GROUP_ID:
            try:
                await application.bot.send_message(
                    int(GROUP_ID),
                    msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"⚠️ Lỗi gửi báo cáo vào nhóm: {e}")

        # Gửi cho tất cả user đã đăng ký
        for uid in cfg.get("users", {}):
            try:
                await application.bot.send_message(
                    int(uid),
                    msg,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception as e:
                print(f"⚠️ Lỗi gửi báo cáo cho user {uid}: {e}")


# ===== FLASK WEBHOOK =====
@app.route(WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)

    # ✅ Cách đúng cho python-telegram-bot v21.x
    asyncio.run(application.process_update(update))

    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running 🌟", 200

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
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))

# ===== START WEBHOOK + DAILY TASK =====
async def set_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook đã được set tại {WEBHOOK_URL}")

async def start_bot():
    await set_webhook()
    asyncio.create_task(send_daily_report())
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    asyncio.run(set_webhook())
app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

