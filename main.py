import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

# إعدادات البوت
TOKEN = '7885914349:AAHFM6qMX_CYOOajGwhczwXl3mnLjqRJIAg'
OWNER_ID = 7123756100
CHANNEL_ID = -1002529600259

monitoring = False
contract_name = ""
threshold = 0.3
last_price = 0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    keyboard = [
        [InlineKeyboardButton("تحديد العقد", callback_data="set_contract")],
        [InlineKeyboardButton("إيقاف التحديث", callback_data="stop_monitoring")],
        [InlineKeyboardButton("إرسال تجربة", callback_data="test_capture")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("مرحباً! تحكم في العقد من هنا:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if update.effective_user.id != OWNER_ID:
        return
    if query.data == "set_contract":
        await query.edit_message_text("أرسل اسم العقد (مثال: SPXW 5740C 02May):")
        return 1
    elif query.data == "stop_monitoring":
        global monitoring
        monitoring = False
        await query.edit_message_text("تم إيقاف التحديث ❌")
        return -1
    elif query.data == "test_capture":
        await capture_image()
        with open("contract.png", "rb") as photo:
            await context.bot.send_photo(chat_id=OWNER_ID, photo=photo)
        await query.edit_message_text("تم إرسال الصورة التجريبية.")
        return -1

async def receive_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global contract_name
    contract_name = update.message.text.strip()
    await update.message.reply_text("الآن أرسل قيمة التحديث (مثال 0.30):")
    return 2

async def receive_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global threshold, monitoring, last_price
    try:
        threshold = float(update.message.text.strip())
        monitoring = True
        last_price = 0
        await update.message.reply_text("✅ تم بدء المراقبة للعقد...")
        asyncio.create_task(monitor_contract(context))
    except:
        await update.message.reply_text("❌ تأكد من كتابة رقم صحيح.")
    return -1

async def capture_image():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        await page.goto("https://app.webull.com/paper/desktop")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="contract.png")
        await browser.close()

async def monitor_contract(context: ContextTypes.DEFAULT_TYPE):
    global last_price
    while monitoring:
        await capture_image()
        new_price = round(last_price + threshold, 2)  # محاكاة
        if new_price - last_price >= threshold:
            last_price = new_price
            with open("contract.png", "rb") as photo:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo)
        await asyncio.sleep(3)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=OWNER_ID), receive_contract))
    app.add_handler(MessageHandler(filters.TEXT & filters.User(user_id=OWNER_ID), receive_threshold))
    app.run_polling()
