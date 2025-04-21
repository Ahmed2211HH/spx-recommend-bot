import os, logging, sqlite3
from datetime import datetime
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from webull import webull
from screenshot import capture_contract_screenshot

TOKEN = os.environ['TELEGRAM_TOKEN']
GROUP_ID = int(os.environ['GROUP_ID_VIP'])
STORE_LINK = os.environ['STORE_LINK']
OWNER_ID = int(os.environ['OWNER_ID'])

logging.basicConfig(level=logging.INFO)
conn = sqlite3.connect('subs.db', check_same_thread=False)
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS subs (phone TEXT PRIMARY KEY, sub_date TEXT)')
conn.commit()

wb = webull()
wb.login(username=os.environ['WB_USER'], password=os.environ['WB_PASS'])

# إعداد عقود المراقبة
tracked_contracts = [{
    "ticker": "SPXW",
    "strike": 5365,
    "type": "CALL",
    "expiry": "04/21/2025",
    "last": 0,
    "step": 10.0
}]

async def start(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    kb = ReplyKeyboardMarkup([[KeyboardButton("أرسل رقمك", request_contact=True)]], resize_keyboard=True)
    await u.message.reply_text("أرسل رقمك للتحقق", reply_markup=kb)

async def contact(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    phone = u.message.contact.phone_number
    c.execute("SELECT sub_date FROM subs WHERE phone=?", (phone,))
    row = c.fetchone()
    if row and datetime.fromisoformat(row[0]) > datetime.now():
        await u.message.reply_text("✅ أنت مشترك")
else:
     await u.message.reply_text(f"يبدو أنك غير مشترك، اشترك هنا: {STORE_LINK}")




async def receipt(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    await cx.bot.forward_message(chat_id=OWNER_ID, from_chat_id=u.effective_chat.id, message_id=u.message.message_id)
    await u.message.reply_text("تم إرسال الإيصال للمراجعة")

async def cb(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    if u.callback_query.data.startswith("ok:"):
        uid = int(u.callback_query.data.split(":")[1])
        await cx.bot.send_message(uid, "تم تفعيل اشتراكك!")
        await cx.bot.invite_chat_member(GROUP_ID, uid)
    await u.callback_query.answer()

async def setstep(u: Update, cx: ContextTypes.DEFAULT_TYPE):
    if u.effective_user.id != OWNER_ID:
        await u.message.reply_text("غير مصرح لك.")
        return
    try:
        val = float(u.message.text.split()[1])
        tracked_contracts[0]['step'] = val
        await u.message.reply_text(f"تم تعديل التحديث إلى {val} دولار.")
    except:
        await u.message.reply_text("استخدم الأمر بهذا الشكل: /setstep 10")

scheduler = BackgroundScheduler()
async def monitor():
    for ct in tracked_contracts:
        price = float(wb.get_option_market_data(ct['ticker'], ct['strike'], ct['type'], ct['expiry']))
        if price >= ct['last'] + ct['step']:
            path = capture_contract_screenshot(ct['ticker'], ct['strike'], ct['type'], ct['expiry'])
            await app.bot.send_photo(GROUP_ID, photo=open(path, 'rb'))
            ct['last'] = price

scheduler.add_job(lambda: app.create_task(monitor()), 'interval', minutes=1)

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setstep", setstep))
app.add_handler(MessageHandler(filters.CONTACT, contact))
app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, receipt))
app.add_handler(CallbackQueryHandler(cb))

if __name__ == "__main__":
    scheduler.start()
    app.run_polling()
