import os
import pytz
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# إعدادات البوت
BOT_TOKEN = '8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4'
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
TIMEZONE = pytz.timezone('Asia/Riyadh')
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
subscriptions = {}

logging.basicConfig(level=logging.INFO)

# ====== أوامر البوت ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id in ADMINS:
        await update.message.reply_text("مرحباً بك، أنت مشرف ✅")
    else:
        await update.message.reply_text("👋 أهلاً بك، الرجاء إرسال إيصال الدفع (صورة فقط).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("❗ الرجاء إرسال الإيصال كصورة فقط.")
        return
    
    file_id = update.message.photo[-1].file_id
    caption = (
        f"📥 إيصال جديد من {user.full_name}\n"
        f"ID: {user.id}\n\n"
        f"للموافقة:\n/accept_{user.id}\n"
        f"للرفض:\n/reject_{user.id}"
    )
    buttons = [
        [
            InlineKeyboardButton("✅ قبول", callback_data=f"accept_{user.id}"),
            InlineKeyboardButton("❌ رفض", callback_data=f"reject_{user.id}")
        ]
    ]
    markup = InlineKeyboardMarkup(buttons)

    for admin_id in ADMINS:
        await context.bot.send_photo(chat_id=admin_id, photo=file_id, caption=caption, reply_markup=markup)

    await update.message.reply_text("✅ تم إرسال الإيصال للمشرفين وسيتم الرد عليك قريباً.")

async def accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.split("_")[1])
        now = datetime.now(TIMEZONE)
        end_date = now + timedelta(days=28)
        subscriptions[user_id] = end_date

        # إنشاء رابط مؤقت
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=GROUP_ID,
            expire_date=now + timedelta(minutes=5),
            member_limit=1
        )

        await context.bot.send_message(chat_id=user_id, text=f"✅ تم قبول اشتراكك! رابط المجموعة:\n{invite_link.invite_link}")
        await update.message.reply_text(f"✅ تم قبول المستخدم {user_id}")

        scheduler.add_job(kick_user, 'date', run_date=end_date, args=[user_id])
        scheduler.add_job(warn_user, 'date', run_date=end_date - timedelta(days=3), args=[user_id])
    except:
        await update.message.reply_text("❌ حدث خطأ أثناء قبول الاشتراك.")

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text.split("_")[1])
        await context.bot.send_message(chat_id=user_id, text="❌ تم رفض إيصالك، يرجى التواصل مع الدعم.")
        await update.message.reply_text(f"🚫 تم رفض المستخدم {user_id}")
    except:
        await update.message.reply_text("❌ حدث خطأ أثناء الرفض.")

async def warn_user(user_id):
    await app.bot.send_message(chat_id=user_id, text="⚠️ تبقى 3 أيام على انتهاء اشتراكك، يرجى التجديد لتفادي الطرد.")

async def kick_user(user_id):
    try:
        await app.bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await app.bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
        await app.bot.send_message(chat_id=user_id, text="📛 انتهى اشتراكك وتم إخراجك من المجموعة.")
    except:
        pass

# ====== إنشاء التطبيق وتشغيله ======
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CommandHandler("accept", accept_command))
app.add_handler(CommandHandler("reject", reject_command))

scheduler.start()

if __name__ == "__main__":
    print("🚀 Bot is running...")
    app.run_polling()
