from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from datetime import datetime
import asyncio
from PIL import Image, ImageDraw

# إعدادات
TOKEN = '7737113763:AAF2XR_qUMIFwbMUz37imbJZP22wYh4ulDQ'
CHANNEL_ID_VIP = -1002529600259
CHANNEL_INVITE_LINK = 'https://t.me/+DaHQpgAd3doyMTg0'
STORE_LINK = 'https://options-x.com/باقة-قناة-سباكس-لمدة-٣٠-يوم/p1136204150'
OWNER_ID = 7123756100

pending_users = {}
approved_users = {}
WATCHED_CONTRACT = {"ticker": "", "strike": 0, "type": "call", "expiry": "", "step": 1.0}
last_price = None

# بدء المحادثة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("زيارة المتجر", url=STORE_LINK)],
        [InlineKeyboardButton("إرسال إيصال الدفع", callback_data="send_receipt")]
    ]
    await update.message.reply_text(
        f"مرحباً {user.first_name}! 👋\nاختر أحد الخيارات أدناه:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# إرسال إيصال
async def send_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if user_id in approved_users:
        await query.edit_message_text("تمت إضافتك بالفعل إلى القناة الخاصة!")
    elif user_id in pending_users:
        await query.edit_message_text("طلبك قيد المراجعة بالفعل.")
    else:
        await query.edit_message_text("يرجى إرسال صورة إيصال الدفع هنا للتحقق.")
        context.user_data["awaiting_receipt"] = True

# التحقق من الإيصال
async def check_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_receipt") and update.message.photo:
        user = update.effective_user
        user_id = user.id
        if user_id in pending_users:
            await update.message.reply_text("طلبك قيد المراجعة بالفعل.")
            return
        keyboard = [[
            InlineKeyboardButton("✅ الموافقة", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ الرفض", callback_data=f"reject_{user_id}")
        ]]
        await context.bot.send_photo(
            chat_id=OWNER_ID,
            photo=update.message.photo[-1].file_id,
            caption=f"📥 إيصال من {user.first_name} (ID: {user_id})",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        pending_users[user_id] = user
        context.user_data["awaiting_receipt"] = False
        await update.message.reply_text("✅ تم استلام الإيصال وسيتم مراجعته.")

# الموافقة / الرفض
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        if user_id in pending_users:
            user = pending_users.pop(user_id)
            await context.bot.send_message(chat_id=user_id, text=f"🎉 تم التحقق! رابط القناة:\n{CHANNEL_INVITE_LINK}")
            await query.edit_message_caption("✅ تمت الموافقة.", reply_markup=None)
            approved_users[user_id] = user
    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        if user_id in pending_users:
            pending_users.pop(user_id)
            await query.edit_message_caption("❌ تم الرفض.", reply_markup=None)
            await context.bot.send_message(chat_id=user_id, text="❌ تم رفض الطلب.")

# تعيين العقد
async def set_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("الصيغة: /set_contract SPXW 5490 call 2025-04-23 0.5")
        return
    WATCHED_CONTRACT["ticker"] = args[0]
    WATCHED_CONTRACT["strike"] = float(args[1])
    WATCHED_CONTRACT["type"] = args[2].lower()
    WATCHED_CONTRACT["expiry"] = args[3]
    WATCHED_CONTRACT["step"] = float(args[4]) if len(args) >= 5 else 1.0
    await update.message.reply_text(f"✅ تم ضبط العقد:\n{WATCHED_CONTRACT}")

# رسم صورة (مؤقت)
async def capture_contract_image():
    img = Image.new('RGB', (400, 200), color='black')
    d = ImageDraw.Draw(img)
    d.text((10, 80), f"{WATCHED_CONTRACT['ticker']} @ {WATCHED_CONTRACT['strike']}", fill=(0, 255, 0))
    path = "/tmp/contract.png"
    img.save(path)
    return path

# المراقبة الآلية
async def monitor_price(context: ContextTypes.DEFAULT_TYPE):
    global last_price
    try:
        current_price = round(datetime.now().second + 1.5, 2)
        if last_price is None or abs(current_price - last_price) >= WATCHED_CONTRACT['step']:
            last_price = current_price
            img_path = await capture_contract_image()
            await context.bot.send_photo(chat_id=CHANNEL_ID_VIP, photo=open(img_path, 'rb'),
                caption=f"تحديث تلقائي\nالعقد: {WATCHED_CONTRACT['ticker']}\nالسعر: {current_price}")
    except Exception as e:
        await context.bot.send_message(chat_id=OWNER_ID, text=f"خطأ في التحديث: {e}")

# تشغيل البوت
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set_contract", set_contract))
    app.add_handler(CallbackQueryHandler(send_receipt, pattern="^send_receipt$"))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, check_receipt))
    app.add_handler(CallbackQueryHandler(handle_approval, pattern="^(approve_|reject_).*"))
    app.job_queue.run_repeating(monitor_price, interval=30, first=5)
    app.run_polling()

if __name__ == "__main__":
    main()
