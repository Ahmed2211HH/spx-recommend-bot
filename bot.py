import os, logging, sqlite3
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from webull import webull

TOKEN       = os.environ['TELEGRAM_TOKEN']
GROUP_ID    = int(os.environ['GROUP_ID_VIP'])
STORE_LINK  = os.environ['STORE_LINK']
OWNER_PHONE = os.environ['OWNER_PHONE']

logging.basicConfig(level=logging.INFO)
conn = sqlite3.connect('subs.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS subs (phone TEXT, chat_id INTEGER, sub_date TEXT)')
conn.commit()

wb = webull()
wb.login(username=os.environ['WB_USER'], password=os.environ['WB_PASS'])

async def start(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("مشاركة رقمي", request_contact=True)]], one_time_keyboard=True)
    await u.message.reply_text("أهلاً! أرسل رقمك:", reply_markup=kb)

async def contact(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    phone = u.message.contact.phone_number
    c.execute("SELECT sub_date FROM subs WHERE phone = ?", (phone,))
    row = c.fetchone()
    if row and datetime.fromisoformat(row[0]) + timedelta(days=30) > datetime.now():
        await u.message.reply_text("✔️ اشتراكك ساري.")
        return
    await u.message.reply_text(f"يبدو أنك غير مشترك.\nاشترك هنا: {STORE_LINK}\nثم أرسل إيصال الدفع.")

async def receipt(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    await cx.bot.forward_message(chat_id=OWNER_PHONE, from_chat_id=u.effective_chat.id, message_id=u.message.message_id)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ موافقة", callback_data=f"ok:{u.message.from_user.id}"),
                                InlineKeyboardButton("❌ رفض", callback_data="no")]])
    await u.message.reply_text("تم إرسال إيصالك للمراجعة.", reply_markup=kb)

async def cb(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    if u.data.startswith("ok"):
        uid = int(u.data.split(":")[1])
        c.execute("INSERT OR REPLACE INTO subs VALUES (?,?,?)", ("manual", uid, datetime.now().isoformat()))
        conn.commit()
        await cx.bot.invite_chat_member(chat_id=GROUP_ID, user_id=uid)
        await cx.bot.send_message(uid, "🎉 تمت إضافتك للمجموعة.")
    else:
        await cx.bot.send_message(u.from_user.id, "❌ تم رفض الإيصال.")
    await u.answer()

scheduler = AsyncIOScheduler()
async def monitor():
    for ct in tracked_contracts:
        price = float(wb.get_option_market_data(ct['symbol'])['mark'])
        if price >= ct['last'] + ct['step']:
            await app.bot.send_message(GROUP_ID, f"{ct['symbol']} ➜ {price}")
            ct['last'] = price
scheduler.add_job(monitor, 'interval', minutes=1)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, contact))
    app.add_handler(MessageHandler(filters.PHOTO, receipt))
    app.add_handler(CallbackQueryHandler(cb))
    scheduler.start()
    app.run_polling()
