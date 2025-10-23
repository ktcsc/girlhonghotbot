import os
import json
import asyncio
import requests
import time
import nest_asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, MessageEntity
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from flask import Flask
import aiohttp
import html as pyhtml


# Apply nest_asyncio to avoid event loop issues on some hosts (Render)
nest_asyncio.apply()

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GROUP_ID = os.getenv("GROUP_ID")
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
CONFIG_FILE = "config.json"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN chưa được thiết lập trong biến môi trường!")

# === FLASK HEALTHCHECK (Render cần một endpoint) ===
web_app = Flask(__name__)

@web_app.route("/")
def health():
    return "🤖 Bot @girlhonghot is running (Render)."

# === HELPERS ===
def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    cfg.setdefault("users", {})
    cfg.setdefault("news_sources", ["https://coin68.com/feed/"])
    cfg.setdefault("report_time", "08:00")
    cfg.setdefault("last_news", [])
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def is_admin(uid):
    if ADMIN_ID is None:
        return False
    return str(uid) == str(ADMIN_ID)

def is_registered(uid):
    return str(uid) in load_config().get("users", {})

# === COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not (is_registered(user.id) or is_admin(user.id)):
        return await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
    await update.message.reply_text(f"👋 Chào {user.first_name}! Tôi là @girlhonghot – trợ lý crypto của bạn 💖")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💡 *Hướng dẫn sử dụng:*\n\n"
        "• /start – Bắt đầu trò chuyện\n"
        "• /dangky – Gửi yêu cầu đăng ký sử dụng bot\n"
        "• /price <coin> – Xem giá coin (vd: /price btc)\n"
        "• /top – Top 10 coin theo vốn hóa\n"
        "• /news – Lấy tin tức RSS từ nguồn\n"
        "• /addnews <url> – Thêm nguồn tin (admin)\n"
        "• /delnews <url> – Xóa nguồn tin (admin)\n"
        "• /listnews – Hiển thị nguồn tin\n"
        "• /settime <HH:MM> – Đặt giờ gửi báo cáo hàng ngày (admin)\n"
        "• /report – Gọi báo cáo thủ công\n"
        "• /help – Hiển thị hướng dẫn\n\n"
        "👑 *Dành cho Admin:*\n"
        "• /them <id> – Thêm người dùng\n"
        "• /xoa <id> – Xóa người dùng\n"
        "• /listuser – Danh sách người dùng"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def dangky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cfg = load_config()
    if str(user.id) in cfg["users"]:
        return await update.message.reply_text("✅ Bạn đã được kích hoạt rồi!")
    msg = (
        f"📩 *YÊU CẦU ĐĂNG KÝ MỚI*\n"
        f"👤 Username: @{user.username or 'Không có'}\n"
        f"🆔 ID: `{user.id}`\n\n"
        f"📌 Admin dùng /them {user.id} để kích hoạt."
    )
    try:
        if ADMIN_ID:
            await context.bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    except Exception:
        pass
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin, vui lòng chờ duyệt 💬")

async def them(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        uid = context.args[0]
        cfg = load_config()
        if uid in cfg["users"]:
            return await update.message.reply_text("⚠️ Người dùng đã tồn tại.")
        user_info = await context.bot.get_chat(uid)
        cfg["users"][uid] = user_info.username or user_info.first_name or "User"
        save_config(cfg)
        await update.message.reply_text(f"✅ Đã kích hoạt {cfg['users'][uid]} ({uid})")
        try:
            await context.bot.send_message(uid, "🎉 Bạn đã được kích hoạt! Bắt đầu dùng bot nhé 💖")
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("❌ Sai cú pháp: /them <id>")

async def xoa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        uid = context.args[0]
        cfg = load_config()
        if uid not in cfg["users"]:
            return await update.message.reply_text("❌ Không tìm thấy user này.")
        del cfg["users"][uid]
        save_config(cfg)
        await update.message.reply_text(f"🗑️ Đã xóa người dùng {uid}")
    except Exception:
        await update.message.reply_text("❌ Sai cú pháp: /xoa <id>")

async def listuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    cfg = load_config()
    if not cfg["users"]:
        return await update.message.reply_text("📭 Chưa có người dùng nào.")
    msg = "👥 *Danh sách người dùng:*\n\n"
    for k, v in cfg["users"].items():
        msg += f"• {v} – `{k}`\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === PRICE / TOP ===
COIN_CACHE = {"data": [], "last_update": 0}

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_registered(update.message.from_user.id):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /price btc hoặc /price bitcoin")
    query = context.args[0].lower()
    if time.time() - COIN_CACHE["last_update"] > 3600 or not COIN_CACHE["data"]:
        try:
            COIN_CACHE["data"] = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=10).json()
            COIN_CACHE["last_update"] = time.time()
        except Exception:
            COIN_CACHE["data"] = COIN_CACHE.get("data", [])
    coins = COIN_CACHE["data"]
    match = next((c for c in coins if c.get("id","").lower() == query), None)
    if not match:
        symbol_matches = [c for c in coins if c.get("symbol","").lower() == query]
        if len(symbol_matches) == 1:
            match = symbol_matches[0]
        elif len(symbol_matches) > 1:
            try:
                s = requests.get(f"https://api.coingecko.com/api/v3/search?query={query}", timeout=10).json()
                candidates = [c for c in s.get("coins", []) if c.get("symbol","").lower() == query]
                if candidates:
                    candidates_sorted = sorted(candidates, key=lambda x: x.get("market_cap_rank") or 10**9)
                    chosen_id = candidates_sorted[0]["id"]
                    match = next((c for c in coins if c.get("id") == chosen_id), None)
            except Exception:
                match = symbol_matches[0] if symbol_matches else None
        else:
            match = next((c for c in coins if c.get("name","").lower() == query), None)
    if not match:
        return await update.message.reply_text("❌ Không tìm thấy coin.")
    cid = match["id"]
    try:
        res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd", timeout=10).json()
        if cid in res:
            p = res[cid]["usd"]
            await update.message.reply_text(f"💰 Giá {match.get('name', cid).title()} ({match.get('symbol','').upper()}): ${p:,}")
        else:
            await update.message.reply_text("⚠️ Không lấy được giá coin này.")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Lỗi khi lấy giá: {e}")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_registered(update.message.from_user.id):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    try:
        data = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=10", timeout=10).json()
        msg = "🏆 *Top 10 Coin theo vốn hóa:*\n\n"
        for i, c in enumerate(data[:10], 1):
            msg += f"{i}. {c.get('name')} ({c.get('symbol','').upper()}): ${c.get('current_price'):,}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Lỗi: {e}")

# === NEWS helpers and commands ===
def fetch_items_from_feed(src):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; girlhonghotBot/1.0; +https://girlhonghot.onrender.com)"
        }
        r = requests.get(src, timeout=8, headers=headers)
        soup = BeautifulSoup(r.content, "xml")
        items = soup.find_all("item")
        if not items:
            # fallback sang HTML (nhiều trang WordPress giờ không còn RSS XML)
            soup = BeautifulSoup(r.content, "html.parser")
            items = soup.find_all("item")
        return items
    except Exception as e:
        print(f"⚠️ Lỗi khi đọc RSS từ {src}: {e}")
        return []

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    msg = "📰 <b>TIN TỨC CRYPTO MỚI NHẤT</b>\n\n"
    for src in cfg.get("news_sources", []):
        items = fetch_items_from_feed(src)[:5]
        if not items:
            msg += f"⚠️ Không tìm thấy tin nào từ {src}\n\n"
            continue
        for i in items:
            title = pyhtml.escape(getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề")
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
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /addnews <url>")
    cfg = load_config()
    url = context.args[0]
    if url in cfg["news_sources"]:
        return await update.message.reply_text("⚠️ Nguồn đã tồn tại.")
    cfg["news_sources"].append(url)
    save_config(cfg)
    await update.message.reply_text("✅ Đã thêm nguồn tin.")

async def delnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /delnews <url>")
    cfg = load_config()
    url = context.args[0]
    if url not in cfg["news_sources"]:
        return await update.message.reply_text("❌ Không có nguồn này.")
    cfg["news_sources"].remove(url)
    save_config(cfg)
    await update.message.reply_text("🗑️ Đã xóa nguồn tin.")

async def listnews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    msg = "🗞️ *Danh sách nguồn tin:*\n\n"
    for s in cfg["news_sources"]:
        msg += f"• {s}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

# === SETTIME / REPORT ===
async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Chỉ admin có thể thay đổi giờ báo cáo.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /settime HH:MM (vd: /settime 09:30)")
    new_time = context.args[0]
    # basic validation HH:MM
    try:
        datetime.strptime(new_time, "%H:%M")
    except Exception:
        return await update.message.reply_text("❌ Định dạng không hợp lệ. Dùng HH:MM (24h).")
    cfg = load_config()
    cfg["report_time"] = new_time
    save_config(cfg)
    await update.message.reply_text(f"⏰ Đã cập nhật giờ báo cáo thành {new_time}")

def generate_report():
    cfg = load_config()
    msg = "📊 <b>BÁO CÁO TỔNG HỢP CRYPTO</b>\n\n"
    # Market overview
    try:
        global_data = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()["data"]
        total_mcap = global_data["total_market_cap"]["usd"]
        total_volume = global_data["total_volume"]["usd"]
        btc_dom = global_data["market_cap_percentage"]["btc"]
        msg += "🌍 <b>TỔNG QUAN THỊ TRƯỜNG</b>\n"
        msg += f"• Tổng vốn hóa: ${total_mcap:,.0f}\n"
        msg += f"• Khối lượng 24h: ${total_volume:,.0f}\n"
        msg += f"• BTC Dominance: {btc_dom:.2f}%\n"
        try:
            fear = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()["data"][0]
            msg += f"• Fear & Greed: {fear['value']} ({fear['value_classification']})\n"
        except Exception:
            msg += "• Fear & Greed: N/A\n"
        msg += "\n"
    except Exception:
        msg += "⚠️ Không thể lấy dữ liệu tổng quan.\n\n"
    # News highlights
    msg += "📰 <b>TIN TỨC NỔI BẬT</b>\n"
    for src in cfg.get("news_sources", []):
        items = fetch_items_from_feed(src)[:5]
        if not items:
            msg += f"⚠️ Không có bài viết từ {src}\n\n"
            continue
        for i in items:
            title = pyhtml.escape(getattr(i, "title", "").text.strip() if getattr(i, "title", None) else "Không có tiêu đề")
            link = None
            if i.find("link") and getattr(i.find("link"), "text", "").strip().startswith("http"):
                link = i.find("link").text.strip()
            elif i.find("guid") and "http" in getattr(i.find("guid"), "text", ""):
                link = i.find("guid").text.strip()
            else:
                link = src
            msg += f"• <a href=\"{link}\">{title}</a>\n"
        msg += "\n"
    # Market snapshot
    msg += "💹 <b>THỊ TRƯỜNG HIỆN TẠI</b>\n"
    try:
        coins = ["bitcoin", "ethereum", "bnb", "solana", "xrp"]
        coin_icons = {"bitcoin":"🟠","ethereum":"💎","bnb":"🟡","solana":"🟣","xrp":"💠"}
        data = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + ",".join(coins), timeout=10).json()
        for c in data:
            icon = coin_icons.get(c["id"], "💰")
            msg += f"{icon} <b>{c['name']}</b>: ${c['current_price']:,.2f} ({c.get('price_change_percentage_24h',0):+.2f}%)\n"
        market_data = requests.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=50", timeout=10).json()
        top_up = sorted(market_data, key=lambda x: x.get("price_change_percentage_24h",0), reverse=True)[:3]
        top_down = sorted(market_data, key=lambda x: x.get("price_change_percentage_24h",0))[:3]
        msg += "\n📈 <b>Top tăng mạnh</b>\n"
        for coin in top_up:
            msg += f"🔹 {coin['symbol'].upper()}: +{coin['price_change_percentage_24h']:.2f}% (${coin['current_price']:,.2f})\n"
        msg += "\n📉 <b>Top giảm mạnh</b>\n"
        for coin in top_down:
            msg += f"🔸 {coin['symbol'].upper()}: {coin['price_change_percentage_24h']:.2f}% (${coin['current_price']:,.2f})\n"
    except Exception:
        msg += "⚠️ Không thể lấy dữ liệu thị trường.\n"
    return msg

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (is_admin(update.message.from_user.id) or is_registered(update.message.from_user.id)):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    msg = generate_report()
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)

# === AI CHAT ===
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.chat.type in ["group", "supergroup"]:
        if not msg.entities or not any(e.type == MessageEntity.MENTION and "@girlhonghot" in msg.text for e in msg.entities):
            return
    prompt = msg.text.replace("@girlhonghot", "").strip()
    if not prompt:
        return
    # send typing
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
    except Exception:
        pass
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.chatanywhere.tech/v1/chat/completions",
                headers={"Authorization": f"Bearer {CHATANYWHERE_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "Bạn là cô trợ lý crypto dễ thương, thông minh và thân thiện. Hãy trả lời ngắn gọn, rõ ràng và bằng tiếng Việt."},
                        {"role": "user", "content": prompt},
                    ],
                    "max_tokens": 500
                },
                timeout=30
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    await msg.reply_text(f"⚠️ Lỗi AI ({resp.status}): {text[:200]}")
                    return
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi khi gọi AI: {e}")

# === DAILY BACKGROUND TASK ===
async def daily_report_task(app: Application):
    while True:
        try:
            now = datetime.now().strftime("%H:%M")
            cfg = load_config()
            if now == cfg.get("report_time", "08:00"):
                msg = generate_report()
                # send to group
                if GROUP_ID:
                    try:
                        await app.bot.send_message(GROUP_ID, msg, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception as e:
                        print("⚠️ Lỗi gửi báo cáo vào group:", e)
                # send to users
                for uid in cfg.get("users", {}):
                    try:
                        await app.bot.send_message(uid, msg, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception:
                        pass
                print("✅ Báo cáo đã gửi lúc", now)
                await asyncio.sleep(60)
        except Exception as e:
            print("⚠️ Lỗi trong daily_report_task:", e)
        await asyncio.sleep(20)

# === STARTUP (WEBHOOK MODE - RENDER READY) ===
import os
import nest_asyncio
import asyncio
from flask import request
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# === TOKEN & URL ===
BASE_URL = os.getenv("BASE_URL", "https://girlhonghot.onrender.com")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# === FLASK APP (dùng chung web_app đã có ở trên) ===
app = web_app  # tái sử dụng Flask app từ trên

@app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    """Nhận dữ liệu từ Telegram gửi về"""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
        user = update.effective_user
        if user and update.message:
            print(f"[Webhook] 📩 @{user.username or user.id}: {update.message.text}")
    except Exception as e:
        print(f"⚠️ Lỗi xử lý webhook: {e}")
    return "OK", 200

# === TELEGRAM APPLICATION ===
application = Application.builder().token(BOT_TOKEN).build()

# --- Đăng ký handlers ---
handlers = [
    ("start", start),
    ("help", help_command),
    ("dangky", dangky),
    ("them", them),
    ("xoa", xoa),
    ("listuser", listuser),
    ("price", price),
    ("top", top),
    ("news", news),
    ("addnews", addnews),
    ("delnews", delnews),
    ("listnews", listnews),
    ("settime", settime),
    ("report", report_cmd),
]
for cmd, fn in handlers:
    application.add_handler(CommandHandler(cmd, fn))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))


# === TASK NỀN ===
async def background_tasks():
    """Chạy task báo cáo định kỳ"""
    await asyncio.sleep(5)
    asyncio.create_task(daily_report_task(application))


# === CHẠY WEBHOOK ===
async def start_bot():
    print("🤖 Bot @girlhonghot - starting with Webhook...")
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        await application.bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set: {WEBHOOK_URL}")
    except Exception as e:
        print(f"⚠️ Lỗi set webhook: {e}")
    asyncio.create_task(background_tasks())


def run():
    """Khởi động bot + Flask song song"""
    nest_asyncio.apply()
    Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000))), daemon=True).start()
    asyncio.run(start_bot())
    asyncio.get_event_loop().run_forever()


if __name__ == "__main__":
    run()

