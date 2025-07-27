import os
import json
import asyncio
import datetime
import pytz
from telegram import Update, InputMediaPhoto, ChatInviteLink
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

# إعدادات
BOT_TOKEN = '8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4'
GROUP_ID = -1002789810612
ADMINS = [7123756100, 6356823688]
TIMEZONE = pytz.timezone("Asia/Riyadh")
DATA_FILE = 'subs.json'

# تحميل بيانات الاشتراكات
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as f:
        subscriptions = json.load(f)
else:
    subscriptions = {}

# حفظ البيانات
def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(subscriptions, f)

# إرسال تنبيه قبل انتهاء الاشتراك
async def notify_before_end(app, user_id):
    try:
        await app.bot.send_message(user_id, "📢 تذكير: تبقى 3 أيام على انتهاء اشتراكك. يمكنك التجديد الآن لتجنب انقطاع الخدمة.")
    except:
        pass

# طرد المستخدم من القروب
async def remove_user(app, user_id):
    try:
        await app.bot.ban_chat_member(GROUP_ID, user_id)
        await app.bot.unban_chat_member(GROUP_ID, user_id)
    except:
        pass

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("مرحبًا! الرجاء إرسال إيصال الدفع كصورة لإتمام الاشتراك.")
    else:
        await update.message.reply_text("مرحبًا مشرف. أي صورة إيصال يتم إرسالها ستصلك للموافقة.")

# استقبال صورة الإيصال
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not update.message.photo:
        return await update.message.reply_text("الرجاء إرسال الإيصال كصورة فقط (لا PDF).")

    photo = update.message.photo[-1].file_id
    for admin_id in ADMINS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo,
                caption=f"🧾 إيصال جديد من {user.full_name}\nID: {user_id}\n\nللموافقة: /approve_{user_id}"
            )
        except:
            continue

    await update.message.reply_text("📩 تم استلام الإيصال بنجاح، بانتظار موافقة الإدارة.")

# الموافقة من المشرف
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    command = update.message.text
    if not command.startswith("/approve_"):
        return

    user_id = int(command.split("_")[1])
    app = context.application

    try:
        invite_link = await app.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            member_limit=1,
            creates_join_request=False,
            expire_date=datetime.datetime.now(TIMEZONE) + datetime.timedelta(minutes=1)
        )

        await app.bot.send_message(user_id, f"✅ تم تفعيل اشتراكك، هذا رابط الدخول المؤقت:\n{invite_link.invite_link}")

        now = datetime.datetime.now(TIMEZONE)
        end_date = now + datetime.timedelta(days=28)
        warn_date = end_date - datetime.timedelta(days=3)

        subscriptions[str(user_id)] = end_date.strftime('%Y-%m-%d %H:%M:%S')
        save_data()

        scheduler.add_job(
            notify_before_end,
            trigger=DateTrigger(run_date=warn_date),
            args=[app, user_id]
        )
        scheduler.add_job(
            remove_user,
            trigger=DateTrigger(run_date=end_date),
            args=[app, user_id]
        )

    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء إنشاء الرابط:\n{e}")

# إعداد السكيجولر
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
scheduler.start()

# إنشاء البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/approve_\d+$'), approve))

# تشغيل البوت
if __name__ == "__main__":
    app.run_polling()
