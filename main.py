import os
import json
import asyncio
import requests
import nest_asyncio
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, MessageEntity
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
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
    raise ValueError("❌ BOT_TOKEN chưa được thiết lập trong Render!")

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

# === COMMANDS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not (is_registered(user.id) or is_admin(user.id)):
        return await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
    await update.message.reply_text(f"👋 Chào {user.first_name}! Tôi là @girlhonghot 💖")

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
    except:
        pass
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin 💬")

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
        await context.bot.send_message(uid, "🎉 Bạn đã được kích hoạt! 💖")
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
    except:
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
async def price(update, context):
    if not is_registered(update.message.from_user.id):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /price btc hoặc /price bitcoin")
    query = context.args[0].lower()
    global COIN_CACHE
    if time.time() - COIN_CACHE["last_update"] > 3600 or not COIN_CACHE["data"]:
        COIN_CACHE["data"] = requests.get("https://api.coingecko.com/api/v3/coins/list").json()
        COIN_CACHE["last_update"] = time.time()
    coins = COIN_CACHE["data"]
    match = next((c for c in coins if c["id"].lower() == query), None)
    if not match:
        match = next((c for c in coins if c["symbol"].lower() == query or c["name"].lower() == query), None)
    if not match:
        return await update.message.reply_text("❌ Không tìm thấy coin.")
    cid = match["id"]
    res = requests.get(f"https://api.coingecko.com/api/v3/simple/price?ids={cid}&vs_currencies=usd").json()
    p = res[cid]["usd"]
    await update.message.reply_text(f"💰 Giá {match['name']} ({match['symbol'].upper()}): ${p:,}")

# === AI CHAT ===
async def ai_chat(update, context):
    msg = update.message
    if not msg or not msg.text:
        return
    if msg.chat.type in ["group", "supergroup"]:
        if not msg.entities or not any(e.type == MessageEntity.MENTION and "@girlhonghot" in msg.text for e in msg.entities):
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
                    "messages": [{"role": "system", "content": "Bạn là cô trợ lý crypto dễ thương 💖"}, {"role": "user", "content": prompt}],
                },
            ) as resp:
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi AI: {e}")

# === BACKGROUND LOOP ===
async def daily_report(app):
    while True:
        now = datetime.now().strftime("%H:%M")
        cfg = load_config()
        if now == cfg.get("report_time", "08:00"):
            try:
                await app.bot.send_message(GROUP_ID, "📊 Báo cáo crypto hàng ngày đang được xử lý...")
            except Exception as e:
                print("⚠️ Lỗi gửi báo cáo:", e)
            await asyncio.sleep(60)
        await asyncio.sleep(20)

# === MAIN ===
async def main():
    print("🤖 Bot @girlhonghot đang khởi động...")
    app = Application.builder().token(BOT_TOKEN).build()

    for cmd, fn in [("start", start), ("dangky", dangky), ("them", them), ("xoa", xoa), ("listuser", listuser), ("price", price)]:
        app.add_handler(CommandHandler(cmd, fn))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat))
    asyncio.create_task(daily_report(app))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
