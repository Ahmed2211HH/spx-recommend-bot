import os
import logging
import pytz
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.background import BackgroundScheduler

# ====== الإعدادات ======
BOT_TOKEN = '8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4'
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
TIMEZONE = pytz.timezone('Asia/Riyadh')

# ====== تسجيل الأخطاء ======
logging.basicConfig(level=logging.INFO)

# ====== حفظ الاشتراكات ======
subscriptions = {}

# ====== تهيئة الجدولة ======
scheduler = BackgroundScheduler(timezone=TIMEZONE)
scheduler.start()

# ====== أمر /start ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("أهلاً بك، الرجاء إرسال إيصال الدفع (صورة فقط).")
    else:
        await update.message.reply_text("مرحباً بك، أنت مشرف.")

# ====== استقبال الإيصال ======
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("📸 الرجاء إرسال الإيصال كصورة فقط.")
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id

    # إنشاء الأزرار للمشرفين
    keyboard = [
        [InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user.id}"),
         InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    caption = (
        f"📥 إيصال جديد من {user.full_name}\n"
        f"ID: {user.id}\n\n"
        f"للموافقة:\n/accept_{user.id}\n"
        f"للرفض:\n/reject_{user.id}"
    )

    for admin_id in ADMINS:
        await context.bot.send_photo(chat_id=admin_id, photo=file_id, caption=caption, reply_markup=reply_markup)
    
    await update.message.reply_text("📨 تم إرسال الإيصال للمشرفين، سيتم الرد عليك قريبًا.")

# ====== قبول الاشتراك ======
async def accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.message.text.split("_")[1])
    now = datetime.now(TIMEZONE)
    end_date = now + timedelta(days=28)
    subscriptions[user_id] = end_date

    # إرسال رابط مؤقت
    invite_link = await context.bot.create_chat_invite_link(chat_id=GROUP_ID, member_limit=1, expire_date=int((now + timedelta(minutes=5)).timestamp()))
    await context.bot.send_message(chat_id=user_id, text=f"✅ تم قبول اشتراكك! هذا رابط الدخول للمجموعة:\n{invite_link.invite_link}")

    # إرسال تأكيد للمشرف
    await update.message.reply_text(f"✅ تم قبول اشتراك المستخدم {user_id}")

    # جدولة الطرد بعد 28 يوم
    scheduler.add_job(kick_user, 'date', run_date=end_date, args=[user_id], id=f'kick_{user_id}')

    # تنبيه قبل 3 أيام
    warning_time = end_date - timedelta(days=3)
    scheduler.add_job(warn_user, 'date', run_date=warning_time, args=[user_id], id=f'warn_{user_id}')

# ====== رفض الاشتراك ======
async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = int(update.message.text.split("_")[1])
    await context.bot.send_message(chat_id=user_id, text="❌ تم رفض إيصالك، الرجاء التواصل مع الدعم.")
    await update.message.reply_text(f"❌ تم رفض اشتراك المستخدم {user_id}")

# ====== طرد المستخدم ======
async def kick_user(user_id):
    from telegram.error import BadRequest
    try:
        await app.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await app.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await app.bot.send_message(chat_id=user_id, text="📛 انتهى اشتراكك وتم إخراجك من المجموعة.")
    except BadRequest:
        pass

# ====== تنبيه قبل الانتهاء ======
async def warn_user(user_id):
    await app.bot.send_message(chat_id=user_id, text="⚠️ تبقى 3 أيام على انتهاء اشتراكك. يرجى التجديد لتجنب الطرد.")

# ====== إعداد التطبيق ======
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CommandHandler("accept", accept_command))
app.add_handler(CommandHandler("reject", reject_command))

# ====== تشغيل البوت ======
if __name__ == "__main__":
    print("🚀 Bot is running...")
    app.run_polling()
