import os
import json
import asyncio
import requests
import nest_asyncio
import requests, html
from datetime import datetime
from bs4 import BeautifulSoup
from telegram import Update, MessageEntity
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
from datetime import datetime


# Keep Replit / hosting awake (optional)
try:
    from keep_alive import keep_alive
    keep_alive()
except Exception:
    pass

nest_asyncio.apply()

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
GROUP_ID = os.getenv("GROUP_ID")
CHATANYWHERE_API_KEY = os.getenv("CHATANYWHERE_API_KEY")  # ChatAnywhere API Key

CONFIG_FILE = "config.json"

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

    import time
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


    # === NEWS ===
async def news(update, context):
    cfg = load_config()
    msg = "📰 <b>TIN TỨC CRYPTO MỚI NHẤT</b>\n\n"

    for src in cfg.get("news_sources", []):
        try:
            r = requests.get(src, timeout=8)

            try:
                soup = BeautifulSoup(r.content, "xml")
                items = soup.find_all("item")
                if not items:
                    raise Exception("Empty XML")
            except Exception:
                soup = BeautifulSoup(r.content, "html.parser")
                items = soup.find_all("item")

            if not items:
                msg += f"⚠️ Không tìm thấy tin nào từ {src}\n\n"
                continue

            for i in items[:5]:
                title = html.escape(i.title.text.strip()) if i.title else "Không có tiêu đề"

                if i.find("link") and i.find("link").text.strip().startswith("http"):
                    link = i.find("link").text.strip()
                elif i.find("guid") and "http" in i.find("guid").text:
                    link = i.find("guid").text.strip()
                else:
                    link = src

                msg += f"• <a href=\"{link}\">{title}</a>\n"

            msg += "\n"

        except Exception as e:
            print(f"Lỗi đọc nguồn tin {src}: {e}")
            msg += f"⚠️ Lỗi đọc nguồn {src}\n\n"

    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=False)

# === MANAGE NEWS ===
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

# === SET TIME / REPORT ===
async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id):
        return await update.message.reply_text("🚫 Không có quyền.")
    if not context.args:
        return await update.message.reply_text("⚙️ Dùng: /settime HH:MM")
    t = context.args[0]
    cfg = load_config()
    cfg["report_time"] = t
    save_config(cfg)
    await update.message.reply_text(f"🕐 Đã đặt giờ báo cáo: {t}")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.message.from_user.id) and not is_registered(update.message.from_user.id):
        return await update.message.reply_text("🔒 Cần /dangky trước.")
    msg = generate_report()
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)

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


# === REPORT GENERATION ===
def generate_report():

    cfg = load_config()

    # Separator dài (bạn có thể đổi độ dài)
    sep = "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    now = datetime.now().strftime("%H:%M — %d/%m/%Y")

    msg = "📊 <b>BÁO CÁO TỔNG HỢP CRYPTO</b>\n" + sep + "\n\n"

    # ========== TỔNG QUAN THỊ TRƯỜNG ==========
    try:
        global_data = requests.get("https://api.coingecko.com/api/v3/global", timeout=10).json()["data"]
        total_mcap = global_data["total_market_cap"]["usd"]
        total_volume = global_data["total_volume"]["usd"]
        btc_dominance = global_data["market_cap_percentage"]["btc"]

        msg += "🌍 <b>TỔNG QUAN THỊ TRƯỜNG</b>\n"
        msg += f"• Tổng vốn hóa: ${total_mcap:,.0f}\n"
        msg += f"• Khối lượng 24h: ${total_volume:,.0f}\n"
        msg += f"• BTC Dominance: {btc_dominance:.2f}%\n"

        try:
            fear = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8).json()["data"][0]
            msg += f"• Chỉ số Fear & Greed: {fear['value']} ({fear['value_classification']})\n"
        except Exception:
            msg += "• Chỉ số Fear & Greed: N/A\n"

        msg += f"\n{sep}\n\n"
    except Exception as e:
        print("Lỗi global:", e)
        msg += "⚠️ Không thể lấy dữ liệu tổng quan.\n\n" + sep + "\n\n"

    # ========== TIN TỨC NỔI BẬT ==========
    msg += "📰 <b>TIN TỨC NỔI BẬT</b>\n"
    for src in cfg.get("news_sources", []):
        try:
            r = requests.get(src, timeout=8)

            # Ưu tiên parse XML
            try:
                soup = BeautifulSoup(r.content, "xml")
                items = soup.find_all("item")
                if not items:
                    raise Exception("Empty XML")
            except Exception:
                soup = BeautifulSoup(r.content, "html.parser")
                items = soup.find_all("item")

            if not items:
                msg += f"⚠️ Không có bài viết từ {src}\n\n"
                continue

            for i in items[:5]:
                title = html.escape(i.title.text.strip()) if i.title else "Không có tiêu đề"
                if i.find("link") and i.find("link").text.strip().startswith("http"):
                    link = i.find("link").text.strip()
                elif i.find("guid") and "http" in i.find("guid").text:
                    link = i.find("guid").text.strip()
                else:
                    link = src
                msg += f"• <a href=\"{link}\">{title}</a>\n"
            msg += "\n"
        except Exception as e:
            print(f"Lỗi đọc tin {src}: {e}")
            msg += f"⚠️ Lỗi đọc nguồn {src}\n\n"

    msg += sep + "\n\n"

    # ========== THỊ TRƯỜNG HIỆN TẠI ==========
    msg += "💹 <b>THỊ TRƯỜNG HIỆN TẠI</b>\n"
    try:
        coins = ["bitcoin", "ethereum", "bnb", "solana", "xrp"]
        coin_icons = {
            "bitcoin": "🟠",
            "ethereum": "💎",
            "bnb": "🟡",
            "solana": "🟣",
            "xrp": "💠",
        }

        data = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + ",".join(coins),
            timeout=10
        ).json()

        for c in data:
            name = c["name"]
            icon = coin_icons.get(c["id"], "💰")
            price = c["current_price"]
            change = c.get("price_change_percentage_24h", 0)
            msg += f"{icon} <b>{name}</b>: ${price:,.2f} ({change:+.2f}%)\n"

        # Top tăng/giảm mạnh
        market_data = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=50",
            timeout=10
        ).json()

        top_up = sorted(market_data, key=lambda x: x.get("price_change_percentage_24h", 0), reverse=True)[:3]
        top_down = sorted(market_data, key=lambda x: x.get("price_change_percentage_24h", 0))[:3]

        msg += f"\n{sep}\n\n📈 <b>Top tăng mạnh</b>\n"
        for coin in top_up:
            msg += f"🔹 {coin['symbol'].upper()}: +{coin['price_change_percentage_24h']:.2f}% (${coin['current_price']:,.2f})\n"

        msg += f"\n📉 <b>Top giảm mạnh</b>\n"
        for coin in top_down:
            msg += f"🔸 {coin['symbol'].upper()}: {coin['price_change_percentage_24h']:.2f}% (${coin['current_price']:,.2f})\n"

        msg += f"\n{sep}\n🕐 <b>Cập nhật lúc:</b> {now}\nCập nhật theo dữ liệu CoinGecko và Binance."
    except Exception as e:
        print("Lỗi phần thị trường:", e)
        msg += "⚠️ Không thể lấy dữ liệu thị trường.\n"

    return msg


# === DAILY REPORT TASK ===
async def daily_report(bot):
    while True:
        now = datetime.now().strftime("%H:%M")
        cfg = load_config()
        if now == cfg.get("report_time", "08:00"):
            try:
                msg = generate_report()
                if GROUP_ID:
                    try:
                        await bot.send_message(GROUP_ID, msg, parse_mode="Markdown", disable_web_page_preview=True)
                    except Exception as e:
                        print("⚠️ Lỗi gửi báo cáo vào group:", e)
                for uid in cfg.get("users", {}):
                    try:
                        await bot.send_message(uid, msg, parse_mode="", disable_web_page_preview=True)
                    except Exception:
                        pass
                print(f"✅ Báo cáo đã gửi lúc {now}")
            except Exception as e:
                print("⚠️ Lỗi gửi báo cáo:", e)
            await asyncio.sleep(60)
        await asyncio.sleep(20)

# === MAIN ===
app = ApplicationBuilder().token(BOT_TOKEN).build()

for cmd, fn in [
    ("start", start), ("dangky", dangky),
    ("them", them), ("xoa", xoa), ("listuser", listuser),
    ("price", price), ("top", top), ("news", news),
    ("addnews", addnews), ("delnews", delnews), ("listnews", listnews),
    ("settime", settime), ("report", report)
]:
    app.add_handler(CommandHandler(cmd, fn))

app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), ai_chat))

async def run_bot():
    print("🤖 Bot @girlhonghot đang chạy...")
    asyncio.create_task(daily_report(app.bot))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(run_bot())
    