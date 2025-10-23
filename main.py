import os
import json
import asyncio
import requests
import nest_asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, MessageEntity
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
import html
import time

nest_asyncio.apply()

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GROUP_ID = os.getenv("GROUP_ID")
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
CONFIG_FILE = "config.json"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN chưa được thiết lập trong biến môi trường Render!")

# === CONFIG HELPERS ===
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
    except:
        cfg = {}
    cfg.setdefault("users", {})
    cfg.setdefault("news_sources", ["https://coin68.com/feed/"])
    cfg.setdefault("report_time", "08:00")
    return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def is_admin(uid): return str(uid) == str(ADMIN_ID)
def is_registered(uid): return str(uid) in load_config()["users"]

# === /start & /dangky ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not (is_registered(user.id) or is_admin(user.id)):
        return await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
    await update.message.reply_text(f"👋 Chào {user.first_name}! Tôi là @girlhonghot – trợ lý crypto của bạn 💖")

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
        await context.bot.send_message(ADMIN_ID, msg, parse_mode="Markdown")
    except Exception:
        pass
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin, vui lòng chờ duyệt 💬")

# === USER MANAGEMENT ===
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

# === PRICE ===
COIN_CACHE = {"data": [], "last_update": 0}

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_registered(update.message.from_user.id):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /price btc hoặc /price bitcoin")
    query = context.args[0].lower()

    global COIN_CACHE
    if time.time() - COIN_CACHE["last_update"] > 3600 or not COIN_CACHE["data"]:
        try:
            COIN_CACHE["data"] = requests.get("https://api.coingecko.com/api/v3/coins/list", timeout=10).json()
            COIN_CACHE["last_update"] = time.time()
        except Exception:
            pass

    coins = COIN_CACHE["data"]
    match = next((c for c in coins if c.get("id","").lower() == query), None)
    if not match:
        symbol_matches = [c for c in coins if c.get("symbol","").lower() == query]
        if len(symbol_matches) == 1:
            match = symbol_matches[0]
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

# === NEWS ===
async def news(update, context):
    cfg = load_config()
    msg = "📰 <b>TIN TỨC CRYPTO MỚI NHẤT</b>\n\n"
    for src in cfg.get("news_sources", []):
        try:
            r = requests.get(src, timeout=8)
            soup = BeautifulSoup(r.content, "xml")
            items = soup.find_all("item")
            for i in items[:5]:
                title = html.escape(i.title.text.strip()) if i.title else "Không có tiêu đề"
                link = i.link.text.strip() if i.link else src
                msg += f"• <a href=\"{link}\">{title}</a>\n"
            msg += "\n"
        except Exception as e:
            msg += f"⚠️ Lỗi đọc nguồn {src}\n\n"
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=False)

# === AI CHAT (ChatAnywhere) ===
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.chat.type in ["group", "supergroup"]:
        if not msg.entities or not any(
            e.type == MessageEntity.MENTION and "@girlhonghot" in msg.text
            for e in msg.entities
        ):
            return
    prompt = msg.text.replace("@girlhonghot", "").strip()
    if not prompt:
        return
    await msg.reply_chat_action("typing")
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
                    await msg.reply_text(f"⚠️ Lỗi AI ({resp.status}): {text[:100]}")
                    return
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi khi gọi AI: {e}")

# === DAILY REPORT (simple background loop) ===
async def daily_report(bot):
    while True:
        now = datetime.now().strftime("%H:%M")
        cfg = load_config()
        if now == cfg.get("report_time", "08:00"):
            try:
                await bot.send_message(GROUP_ID, "📊 Báo cáo crypto hàng ngày đang được xử lý...")
            except Exception as e:
                print("⚠️ Lỗi gửi báo cáo:", e)
            await asyncio.sleep(60)
        await asyncio.sleep(20)

# === MAIN ===
app = ApplicationBuilder().token(BOT_TOKEN).build()

for cmd, fn in [
    ("start", start), ("dangky", dangky),
    ("them", them), ("xoa", xoa), ("listuser", listuser),
    ("price", price), ("news", news)
]:
    app.add_handler(CommandHandler(cmd, fn))

app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), ai_chat))

async def run_bot():
    print("🤖 Bot @girlhonghot đang chạy trên Render...")
    asyncio.create_task(daily_report(app.bot))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())
