import logging
import pytz
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ====== إعداداتك ======
BOT_TOKEN = '8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4'
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
TIMEZONE = pytz.timezone("Asia/Riyadh")

# قاعدة بيانات مؤقتة
pending_users = {}  # user_id: photo_file_id
subscriptions = {}  # user_id: {'end': datetime, 'warned': False}

# جدولة المهام
scheduler = AsyncIOScheduler()

# ====== الأوامر ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        await update.message.reply_text("هذا البوت مخصص لإدارة الاشتراكات. الرجاء إرسال إيصال الدفع كصورة.")
    else:
        await update.message.reply_text("مرحبًا، أنت مشرف. سيتم إشعارك بأي طلب اشتراك.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in ADMINS:
        return

    photo = update.message.photo[-1]
    file_id = photo.file_id
    pending_users[user_id] = file_id

    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=file_id,
            caption=f"📥 طلب اشتراك من: {user_id}\n\nللموافقة أرسل الأمر التالي:\n/approve {user_id}"
        )

    await update.message.reply_text("📨 تم استلام الإيصال. بانتظار الموافقة من المشرفين.")

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMINS:
        return

    try:
        target_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ استخدم الأمر بشكل صحيح: /approve [user_id]")
        return

    if target_id not in pending_users:
        await update.message.reply_text("❌ لا يوجد طلب معلق لهذا المستخدم.")
        return

    invite_link = await context.bot.create_chat_invite_link(
        chat_id=GROUP_ID,
        member_limit=1,
        expire_date=datetime.now() + timedelta(minutes=1)
    )

    await context.bot.send_message(
        chat_id=target_id,
        text=f"✅ تم قبول اشتراكك. هذا رابط الدخول (صالح لدقيقة واحدة فقط):\n{invite_link.invite_link}"
    )

    end_time = datetime.now(TIMEZONE) + timedelta(days=28)
    subscriptions[target_id] = {"end": end_time, "warned": False}
    del pending_users[target_id]

    await update.message.reply_text("✅ تم قبول المستخدم وإرسال الرابط المؤقت.")

# ====== متابعة الاشتراكات ======
async def check_subscriptions(bot: Bot):
    now = datetime.now(TIMEZONE)
    to_remove = []

    for user_id, sub in subscriptions.items():
        if not sub["warned"] and sub["end"] - now <= timedelta(days=3):
            try:
                await bot.send_message(chat_id=user_id, text="📢 تنبيه: تبقى 3 أيام على انتهاء اشتراكك، يرجى التجديد.")
                subscriptions[user_id]["warned"] = True
            except:
                pass

        elif now >= sub["end"]:
            try:
                await bot.ban_chat_member(chat_id=GROUP_ID, user_id=user_id)
                await bot.unban_chat_member(chat_id=GROUP_ID, user_id=user_id)
            except:
                pass
            to_remove.append(user_id)

    for user_id in to_remove:
        del subscriptions[user_id]

# ====== التشغيل ======
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    scheduler.add_job(check_subscriptions, "interval", hours=6, args=[app.bot])
    scheduler.start()

    await app.run_polling()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
