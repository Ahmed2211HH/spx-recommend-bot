from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# إعدادات
TOKEN = '7737113763:AAFk0HZd6GYLTXW8vBwO_3dXoUH36Sp1VgQ'
CHANNEL_ID_VIP = -1002352256587
CHANNEL_INVITE_LINK = 'https://t.me/+H45CVheiU45iOTZk'
STORE_LINK = 'https://options-x.com/باقة-قناة-سباكس-لمدة-٣٠-يوم/p1136204150'
OWNER_ID = 7123756100

pending_users = {}
approved_users = {}

# دالة بدء المحادثة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    inline_keyboard = [
        [InlineKeyboardButton("زيارة المتجر", url=STORE_LINK)],
        [InlineKeyboardButton("إرسال إيصال الدفع", callback_data="send_receipt")],
        [InlineKeyboardButton("الدعم الفني", url="https://t.me/OptionXn")]
    ]
    reply_markup_inline = InlineKeyboardMarkup(inline_keyboard)

    reply_keyboard = [["القائمة"]]
    reply_markup_keyboard = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True)

    await update.message.reply_text(
        f"مرحباً {user.first_name}! 👋\nاختر أحد الخيارات أدناه:",
        reply_markup=reply_markup_inline
    )
    await update.message.reply_text("استخدم الزر في الأسفل للعودة إلى القائمة.", reply_markup=reply_markup_keyboard)

# دالة عند الضغط على "إرسال إيصال الدفع"
async def send_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    if user_id in approved_users:
        await query.edit_message_text("تمت إضافتك بالفعل إلى القناة الخاصة!")
    elif user_id in pending_users:
        await query.edit_message_text("طلبك قيد المراجعة بالفعل. يرجى الانتظار.")
    else:
        await query.edit_message_text("يرجى إرسال صورة إيصال الدفع هنا للتحقق.")
        context.user_data["awaiting_receipt"] = True

# دالة معالجة الإيصال
async def check_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_receipt") and update.message.photo:
        user = update.effective_user
        user_id = user.id

        if user_id in pending_users:
            await update.message.reply_text("طلبك قيد المراجعة بالفعل.")
            return

        keyboard = [[
            InlineKeyboardButton("✅ الموافقة على الإضافة", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ رفض الإضافة", callback_data=f"reject_{user_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_photo(chat_id=OWNER_ID, photo=update.message.photo[-1].file_id,
                                     caption=f"📥 إيصال من {user.first_name} (ID: {user_id})", reply_markup=reply_markup)

        pending_users[user_id] = user
        context.user_data["awaiting_receipt"] = False
        await update.message.reply_text("✅ تم استلام الإيصال بنجاح، سيتم التحقق منه قريباً.")

# دالة الموافقة أو الرفض
async def handle_approval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        if user_id in pending_users:
            user = pending_users.pop(user_id)
            try:
                await context.bot.send_message(chat_id=user_id, text=f"🎉 تم التحقق من إيصالك! يمكنك الآن الانضمام إلى القناة الخاصة:\n{CHANNEL_INVITE_LINK}")
                await query.edit_message_caption(caption="✅ تم الموافقة على الإضافة وإرسال الدعوة.", reply_markup=None)
                approved_users[user_id] = user
            except Exception as e:
                await context.bot.send_message(chat_id=OWNER_ID, text=f"❌ خطأ أثناء إضافة المستخدم {user_id}: {e}")
        else:
            await query.edit_message_caption(caption="⚠️ المستخدم غير موجود في قائمة الانتظار.", reply_markup=None)

    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        if user_id in pending_users:
            pending_users.pop(user_id)
            await query.edit_message_caption(caption="❌ تم رفض الإضافة.", reply_markup=None)
            await context.bot.send_message(chat_id=user_id, text="❌ تم رفض طلبك. يمكنك التواصل معنا لمزيد من التفاصيل.")
        else:
            await query.edit_message_caption(caption="⚠️ المستخدم غير موجود في قائمة الانتظار.", reply_markup=None)

# دالة التعامل مع زر "القائمة"
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "القائمة":
        await start(update, context)

# تشغيل البوت
def main():
    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(send_receipt, pattern="^send_receipt$"))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, check_receipt))
    application.add_handler(CallbackQueryHandler(handle_approval, pattern="^(approve_|reject_).*"))
    application.add_handler(MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, handle_text))

    from keep_alive import keep_alive
    keep_alive()
    application.run_polling()

if __name__ == "__main__":
    main()
