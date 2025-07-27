
import os
import datetime
import pytz
from telegram import Update, ChatInviteLink, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# إعدادات
BOT_TOKEN = "8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4"
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
TIMEZONE = pytz.timezone("Asia/Riyadh")

# قاعدة بيانات مصغرة (في الذاكرة)
subscriptions = {}

# استقبال الإيصال
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = update.message.photo[-1].file_id
    caption = f"🧾 إيصال جديد من المستخدم: {user_id}"

    # إرسال لكل مشرف
    for admin in ADMINS:
        await context.bot.send_photo(chat_id=admin, photo=photo, caption=caption)

    await update.message.reply_text("📨 تم استلام الإيصال وسيتم مراجعته من الإدارة.")

# قبول الاشتراك من قبل المشرف
async def accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return await update.message.reply_text("🚫 هذا الأمر للمشرفين فقط.")

    try:
        target_id = int(context.args[0])
    except:
        return await update.message.reply_text("❌ استخدم الأمر كذا:\n/accept 123456789")

    # إنشاء رابط مؤقت
    invite: ChatInviteLink = await context.bot.create_chat_invite_link(
        chat_id=GROUP_ID,
        member_limit=1,
        expire_date=datetime.datetime.now(TIMEZONE) + datetime.timedelta(seconds=30)
    )

    await context.bot.send_message(chat_id=target_id, text=f"✅ تم قبول اشتراكك. هذا رابط الدخول المؤقت:\n{invite.invite_link}")

    # تسجيل الاشتراك
    end_date = datetime.datetime.now(TIMEZONE) + datetime.timedelta(days=28)
    subscriptions[target_id] = end_date

    # جدولة التذكير قبل 3 أيام
    remind_date = end_date - datetime.timedelta(days=3)
    context.job_queue.run_once(
        reminder_job, when=DateTrigger(remind_date), data={"user_id": target_id}
    )

    # جدولة الطرد
    context.job_queue.run_once(
        kick_job, when=DateTrigger(end_date), data={"user_id": target_id}
    )

# تذكير بالتجديد
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    await context.bot.send_message(chat_id=user_id, text="⏳ تبقّى 3 أيام على نهاية اشتراكك. يرجى التجديد لتجنب الطرد.")

# طرد من لم يُجدد
async def kick_job(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.data["user_id"]
    try:
        await context.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await context.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
    except:
        pass

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMINS:
        await update.message.reply_text("أهلاً بك مشرف. أرسل /accept 123456789 لقبول الاشتراكات.")
    else:
        await update.message.reply_text("أرسل صورة إيصال الدفع هنا لمراجعة اشتراكك.")

# إعداد التطبيق
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("accept", accept))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# تشغيل البوت
if __name__ == "__main__":
    import asyncio
    asyncio.run(app.run_polling())
