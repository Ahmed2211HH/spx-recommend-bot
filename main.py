import pytz
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
)
from telegram.constants import ChatMemberStatus
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# إعدادات البوت
BOT_TOKEN = "8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4"
GROUP_ID = -1002789810612
ADMINS = [7123756100, 6356823688]
TIMEZONE = pytz.timezone("Asia/Riyadh")

# قاعدة بيانات مصغرة
users_db = {}

# إرسال إيصال إلى الإداريين
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1]
    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=photo.file_id,
            caption=f"🧾 إيصال جديد من: {user.full_name}\nID: {user.id}\n\n✅ للموافقة:\n/accept {user.id}\n❌ للرفض:\n/reject {user.id}"
        )
    await update.message.reply_text("✅ تم استلام الإيصال، سيتم مراجعته من قبل الإدارة.")

# قبول المستخدم
async def accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ الصيغة غير صحيحة. استخدم: /accept USER_ID")
        return

    user_id = int(context.args[0])
    invite = await context.bot.create_chat_invite_link(chat_id=GROUP_ID, member_limit=1, expire_date=datetime.now() + timedelta(minutes=1))
    users_db[user_id] = {
        "join_date": datetime.now(TIMEZONE),
        "notified": False,
    }
    await context.bot.send_message(chat_id=user_id, text=f"✅ تم قبول اشتراكك، هذا رابط الدخول المؤقت:\n{invite.invite_link}")
    await update.message.reply_text("✅ تم إرسال الرابط للمستخدم.")

# رفض المستخدم
async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if len(context.args) != 1:
        await update.message.reply_text("❌ الصيغة غير صحيحة. استخدم: /reject USER_ID")
        return

    user_id = int(context.args[0])
    await context.bot.send_message(chat_id=user_id, text="❌ تم رفض الاشتراك. يرجى التواصل مع الدعم إذا كنت ترى أن هذا خطأ.")
    await update.message.reply_text("🚫 تم رفض المستخدم.")

# فحص الاشتراكات
async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now(TIMEZONE)
    to_remove = []
    for user_id, data in users_db.items():
        join_date = data["join_date"]
        expire_date = join_date + timedelta(days=28)
        remaining_days = (expire_date - now).days

        if remaining_days <= 3 and not data.get("notified"):
            try:
                await context.bot.send_message(chat_id=user_id, text="⏰ متبقي 3 أيام على انتهاء اشتراكك. يرجى التجديد قبل انتهاء المدة.")
                users_db[user_id]["notified"] = True
            except:
                pass

        if now >= expire_date:
            try:
                await context.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id, until_date=now + timedelta(seconds=60))
                await context.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
            except:
                pass
            to_remove.append(user_id)

    for user_id in to_remove:
        users_db.pop(user_id, None)

# أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 أرسل صورة إيصال الدفع كصورة (وليس ملف PDF)، وسيتم مراجعته من الإدارة.")

# تهيئة التطبيق
app = ApplicationBuilder().token(BOT_TOKEN).build()

# جدولة الفحص
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
scheduler.add_job(check_subscriptions, "interval", hours=12, args=[app.bot])
scheduler.start()

# هاندلرز الأوامر والصور
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("accept", accept_command))
app.add_handler(CommandHandler("reject", reject_command))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# تشغيل البوت
app.run_polling()
