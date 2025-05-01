import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from keep_alive import keep_alive

# إعدادات أساسية
TOKEN = '7737113763:AAF2XR_qUMIFwbMUz37imbJZP22wYh4ulDQ'
OWNER_ID = 7123756100
CHANNEL_ID = -1002529600259
STORE_LINK = 'https://options-x.com/باقة-قناة-سباكس-لمدة-٣٠-يوم/p1136204150'

# بيانات
pending_users = {}
approved_users = {}
monitor_config = {}

logging.basicConfig(level=logging.INFO)
# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("🛒 المتجر", url=STORE_LINK)],
        [InlineKeyboardButton("إرسال إيصال", callback_data="send_receipt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"مرحبًا {user.first_name}!\nاختر أحد الخيارات:", reply_markup=reply_markup)

# إرسال إيصال
async def send_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["awaiting_receipt"] = True
    await query.edit_message_text("أرسل الآن صورة إيصال الدفع هنا.")

# استقبال صورة الإيصال
async def check_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_receipt") and update.message.photo:
        user = update.effective_user
        user_id = user.id
        if user_id in pending_users:
            await update.message.reply_text("طلبك قيد المراجعة.")
            return
        keyboard = [[
            InlineKeyboardButton("✅ موافقة", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user_id}")
        ]]
        markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=update.message.photo[-1].file_id,
            caption=f"إيصال من {user.first_name} (ID: {user_id})",
            reply_markup=markup
        )
        pending_users[user_id] = user
        context.user_data["awaiting_receipt"] = False
        await update.message.reply_text("تم استلام الإيصال، في انتظار المراجعة.")
        # معالجة الموافقة أو الرفض من المالك
async def handle_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = int(data.split("_")[1])
    if data.startswith("approve_"):
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID, expire_date=int(datetime.now().timestamp()) + 86400, member_limit=1
        )
        await context.bot.send_message(chat_id=user_id, text=f"✅ تمت الموافقة! هذا رابط القناة:\n{invite_link.invite_link}")
        await query.edit_message_caption("✅ تمت الموافقة.")
        approved_users[user_id] = pending_users.pop(user_id, None)
    elif data.startswith("reject_"):
        await context.bot.send_message(chat_id=user_id, text="❌ تم رفض إيصالك.")
        await query.edit_message_caption("❌ تم الرفض.")
        pending_users.pop(user_id, None)
       # لوحة التحكم: أمر /monitor
async def monitor_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("أرسل اسم العقد (مثال: SPXW 5365C 21Apr25):")
    return 1

async def receive_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    monitor_config["contract_name"] = update.message.text.strip()
    await update.message.reply_text("أرسل الفرق السعري (مثال: 10):")
    return 2

async def receive_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        monitor_config["threshold"] = float(update.message.text.strip())
        monitor_config["last_price"] = 0
        await update.message.reply_text("✅ تم الحفظ. البوت سيبدأ التحديث تلقائي.")
        asyncio.create_task(monitor_loop(context))
    except:
        await update.message.reply_text("❌ تأكد من كتابة رقم صحيح.")
    return -1
# حلقة التحديث التلقائي
async def monitor_loop(context):
    from playwright.async_api import async_playwright
    import time

    await asyncio.sleep(3)
    contract = monitor_config["contract_name"]
    threshold = monitor_config["threshold"]
    last_price = monitor_config["last_price"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://www.webull.com/quote/idxsp-inx")
        await asyncio.sleep(2)

        await page.locator("input[placeholder='Symbol/Name']").fill(contract)
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(4)

        while True:
            try:
                price_element = await page.query_selector("div.price")
                price_text = await price_element.inner_text()
                current_price = float(price_text.replace("$", "").strip())
                if abs(current_price - last_price) >= threshold:
                    last_price = current_price
                    monitor_config["last_price"] = last_price
                    await page.screenshot(path="contract.png")
                    with open("contract.png", "rb") as img:
                        await context.bot.send_photo(chat_id=CHANNEL_ID, photo=img, caption=f"{contract}\nالسعر الحالي: ${current_price}")
                await asyncio.sleep(20)
            except Exception as e:
                print(f"Error during monitoring: {e}")
                await asyncio.sleep(30)
                # إنهاء الأمر
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء.")
    return -1

def main():
    keep_alive()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(send_receipt, pattern="^send_receipt$"))
    app.add_handler(CallbackQueryHandler(handle_admin, pattern="^(approve_|reject_).*"))
    app.add_handler(MessageHandler(filters.PHOTO, check_receipt))

    conv = ConversationHandler(
        entry_points=[CommandHandler("monitor", monitor_command)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_contract)],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_threshold)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)

    app.run_polling()

if __name__ == "__main__":
    main()
