import os
import json
import time
import asyncio
import nest_asyncio
import aiohttp
import requests
from datetime import datetime
from threading import Thread
from flask import Flask, request
from bs4 import BeautifulSoup
from telegram import Update, MessageEntity, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

nest_asyncio.apply()

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GROUP_ID = os.getenv("GROUP_ID")
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")
CONFIG_FILE = "config.json"
BASE_URL = os.getenv("BASE_URL","https://girlhonghot.onrender.com")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN chưa được thiết lập!")

# ====== FLASK HEALTHCHECK ======
app = Flask(__name__)

@app.route("/")
def health():
    return "🤖 Bot @girlhonghot is running (Render)."

# ====== CONFIG HELPERS ======
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

# ====== NEWS RSS HELPER ======
def fetch_items_from_feed(src):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(src, timeout=8, headers=headers)
        soup = BeautifulSoup(r.content,"xml")
        items = soup.find_all("item")
        if not items:
            soup = BeautifulSoup(r.content,"html.parser")
            items = soup.find_all("item")
        return items
    except:
        return []

# ====== TELEGRAM COMMANDS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if not (is_registered(user.id) or is_admin(user.id)):
        return await update.message.reply_text("🔒 Bạn chưa được kích hoạt. Dùng /dangky để gửi yêu cầu.")
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

async def dangky(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cfg = load_config()
    if str(user.id) in cfg["users"]:
        return await update.message.reply_text("✅ Bạn đã được kích hoạt!")
    msg = f"📩 *YÊU CẦU ĐĂNG KÝ*\n👤 @{user.username or 'Không có'}\n🆔 `{user.id}`"
    if ADMIN_ID:
        try: await context.bot.send_message(ADMIN_ID,msg,parse_mode="Markdown")
        except: pass
    await update.message.reply_text("🕐 Đã gửi yêu cầu đến admin, vui lòng chờ duyệt 💬")

async def them(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        uid = context.args[0]
        cfg = load_config()
        user_info = await context.bot.get_chat(uid)
        cfg["users"][uid] = user_info.username or user_info.first_name or "User"
        save_config(cfg)
        await update.message.reply_text(f"✅ Đã kích hoạt {cfg['users'][uid]} ({uid})")
        try: await context.bot.send_message(uid,"🎉 Bạn đã được kích hoạt! 💖")
        except: pass
    except: await update.message.reply_text("❌ Sai cú pháp: /them <id>")

async def xoa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    try:
        uid = context.args[0]
        cfg = load_config()
        if uid not in cfg["users"]: return await update.message.reply_text("❌ Không tìm thấy user này.")
        del cfg["users"][uid]
        save_config(cfg)
        await update.message.reply_text(f"🗑️ Đã xóa {uid}")
    except: await update.message.reply_text("❌ Sai cú pháp: /xoa <id>")

async def listuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    cfg = load_config()
    if not cfg["users"]:
        return await update.message.reply_text("📭 Chưa có người dùng nào.")
    msg = "👥 *Danh sách người dùng:*\n\n"
    for k,v in cfg["users"].items():
        msg += f"• {v} – `{k}`\n"
    await update.message.reply_text(msg,parse_mode="Markdown")

# ====== AI CHAT ======
async def ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text: return
    if msg.chat.type in ["group","supergroup"]:
        if not msg.entities or not any(e.type == MessageEntity.MENTION and "@girlhonghot" in msg.text for e in msg.entities):
            return
    prompt = msg.text.replace("@girlhonghot","").strip()
    if not prompt: return
    try:
        await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.TYPING)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.chatanywhere.tech/v1/chat/completions",
                headers={"Authorization": f"Bearer {CHATANYWHERE_API_KEY}","Content-Type":"application/json"},
                json={
                    "model":"gpt-4o-mini",
                    "messages":[
                        {"role":"system","content":"Bạn là trợ lý crypto dễ thương, trả lời ngắn gọn và bằng tiếng Việt."},
                        {"role":"user","content":prompt}
                    ],
                    "max_tokens":500
                },
                timeout=30
            ) as resp:
                if resp.status != 200:
                    return await msg.reply_text(f"⚠️ Lỗi AI ({resp.status})")
                data = await resp.json()
                reply = data["choices"][0]["message"]["content"]
                await msg.reply_text(reply)
    except Exception as e:
        await msg.reply_text(f"⚠️ Lỗi khi gọi AI: {e}")

# ====== DAILY REPORT ======
async def fetch_fng_index():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.alternative.me/fng/?limit=1",timeout=8) as resp:
                data = await resp.json()
                fng = data.get("data",[{}])[0]
                return fng.get("value","N/A"), fng.get("value_classification","N/A")
    except: return "N/A","N/A"

async def fetch_market_data():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=1&sparkline=false",timeout=10) as resp:
            return await resp.json()

async def fetch_news_rss(limit=3):
    cfg = load_config()
    news_msg = ""
    for src in cfg.get("news_sources",[]):
        items = fetch_items_from_feed(src)[:limit]
        for i in items:
            title = i.title.text if getattr(i,"title",None) else "Không tiêu đề"
            link = i.link.text if getattr(i,"link",None) else src
            news_msg += f"• [{title}]({link})\n"
    return news_msg

async def daily_report_msg():
    market = await fetch_market_data()
    fng_val,fng_status = await fetch_fng_index()
    top_gain = sorted(market,key=lambda c:c.get("price_change_percentage_24h",0),reverse=True)[:5]
    top_loss = sorted(market,key=lambda c:c.get("price_change_percentage_24h",0))[:5]
    news_msg = await fetch_news_rss(limit=3)

    msg = "📊 *BÁO CÁO THỊ TRƯỜNG CRYPTO*\n\n"
    msg += f"🧠 Fear & Greed Index: {fng_val} ({fng_status})\n\n"
    msg += "📈 *Top tăng 5 coin 24h:*\n"
    for c in top_gain:
        msg += f"{c['symbol'].upper()}: ${c['current_price']:,} ({c['price_change_percentage_24h']:+.2f}%)\n"
    msg += "\n📉 *Top giảm 5 coin 24h:*\n"
    for c in top_loss:
        msg += f"{c['symbol'].upper()}: ${c['current_price']:,} ({c['price_change_percentage_24h']:+.2f}%)\n"
    if news_msg:
        msg += "\n📰 *Tin tức mới:*\n" + news_msg
    return msg

async def send_daily_report(app: Application):
    msg = await daily_report_msg()
    cfg = load_config()
    if GROUP_ID:
        try: await app.bot.send_message(GROUP_ID,msg,parse_mode="Markdown",disable_web_page_preview=False)
        except: pass
    for uid in cfg.get("users",{}):
        try: await app.bot.send_message(uid,msg,parse_mode="Markdown",disable_web_page_preview=False)
        except: pass

async def daily_report_task(app: Application):
    while True:
        now = datetime.now().strftime("%H:%M")
        cfg = load_config()
        if now == cfg.get("report_time","08:00"):
            await send_daily_report(app)
            await asyncio.sleep(60)
        await asyncio.sleep(20)

# ====== FLASK WEBHOOK ======
@app.route(WEBHOOK_PATH, methods=["POST"])
async def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        await application.process_update(update)
    except Exception as e:
        print("⚠️ Lỗi webhook:", e)
    return "OK",200

# ====== TELEGRAM APPLICATION ======
application = Application.builder().token(BOT_TOKEN).build()
# --- Register handlers ---
cmds=[
    ("start",start),("help",help_command),("dangky",dangky),
    ("them",them),("xoa",xoa),("listuser",listuser),
    ("price",price),("top",top),
    ("news",news),("addnews",addnews),("delnews",delnews),("listnews",listnews),
    ("settime",settime),("report",report_cmd)
for cmd,fn in cmds:
    application.add_handler(CommandHandler(cmd,fn))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,ai_chat))

async def start_bot():
    print("🤖 Bot @girlhonghot - starting Webhook...")
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        await application.bot.set_webhook(url=WEBHOOK_URL)
        print(f"✅ Webhook set: {WEBHOOK_URL}")
    except Exception as e:
        print("⚠️ Lỗi set webhook:",e)
    asyncio.create_task(daily_report_task(application))

def run():
    Thread(target=lambda: app.run(host="0.0.0.0",port=int(os.getenv("PORT",10000))),daemon=True).start()
    asyncio.run(start_bot())
    asyncio.get_event_loop().run_forever()

if __name__=="__main__":
    run()
