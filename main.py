import asyncio
import datetime
from telegram import Update, ChatInviteLink
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)

# إعدادات
BOT_TOKEN = "8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4"
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
subscribers = {}

# الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("❌ هذا الأمر للمشرفين فقط.")
        return

    await update.message.reply_text("أرسل إيصال الدفع الآن (صورة فقط).")

# استقبال الإيصال
async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ الرجاء إرسال الإيصال كصورة فقط.")
        return

    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=update.message.photo[-1].file_id,
            caption=f"🧾 إيصال جديد من المستخدم: {update.effective_user.mention_html()}",
            parse_mode="HTML",
            reply_markup=None
        )

    await update.message.reply_text("✅ تم استلام الإيصال وسيتم مراجعته من قبل المشرف.")

# أمر قبول الاشتراك
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if len(context.args) != 1:
        await update.message.reply_text("❗ استخدم الأمر بالشكل التالي:\n/approve USER_ID")
        return

    user_id = int(context.args[0])
    invite_link = await context.bot.create_chat_invite_link(
        chat_id=GROUP_ID,
        member_limit=1,
        creates_join_request=False,
        expire_date=datetime.datetime.now() + datetime.timedelta(seconds=60)
    )

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ تم قبول اشتراكك.\nاضغط هنا للانضمام: {invite_link.invite_link}"
    )

    subscribers[user_id] = datetime.datetime.now()
    await update.message.reply_text("👍 تم إرسال رابط الانضمام المؤقت.")

# إزالة المنتهين
async def check_expired():
    now = datetime.datetime.now()
    for user_id, start_time in list(subscribers.items()):
        if (now - start_time).days >= 28:
            try:
                await app.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
                await app.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
                await app.bot.send_message(chat_id=user_id, text="❌ انتهى اشتراكك.")
                del subscribers[user_id]
            except:
                pass

# إعداد البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("approve", approve))
app.add_handler(MessageHandler(filters.PHOTO, handle_receipt))

# تشغيل الجدولة
async def main():
    while True:
        await check_expired()
        await asyncio.sleep(86400)  # تحقق يومي

if __name__ == "__main__":
    app.run_polling(non_stop=True)
    asyncio.run(main())
