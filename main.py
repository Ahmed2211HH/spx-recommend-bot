import logging
import asyncio
import json
import sys
import traceback
from datetime import datetime, timedelta
from telegram import Update, ChatInviteLink
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = '8427790232:AAHc_D6Bs7iXtLVeC7S_ya92KLJwUxI8YZ4'
GROUP_ID = -1002789810612
ADMINS = [6356823688, 7123756100]
SUBSCRIPTIONS_FILE = 'subscriptions.json'

logging.basicConfig(level=logging.INFO)

def load_data():
    try:
        with open(SUBSCRIPTIONS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(SUBSCRIPTIONS_FILE, 'w') as f:
        json.dump(data, f)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1]

    for admin_id in ADMINS:
        await context.bot.send_photo(
            chat_id=admin_id,
            photo=photo.file_id,
            caption=f"ð¥ Ø¥ÙØµØ§Ù Ø¬Ø¯ÙØ¯ ÙÙ: {user.full_name}
ID: {user.id}

ÙÙÙÙØ§ÙÙØ©:
/accept {user.id}
ÙÙØ±ÙØ¶:
/reject {user.id}"
        )
    await update.message.reply_text("â ØªÙ Ø§Ø³ØªÙØ§Ù Ø§ÙØ¥ÙØµØ§Ù. Ø³ÙØªÙ ÙØ±Ø§Ø¬Ø¹ØªÙ ÙÙ ÙØ¨Ù Ø§ÙØ¥Ø¯Ø§Ø±Ø©.")

async def accept_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if len(context.args) != 1:
        await update.message.reply_text("â ÙØ±Ø¬Ù ØªØ­Ø¯ÙØ¯ ID Ø§ÙÙØ³ØªØ®Ø¯Ù: /accept USER_ID")
        return

    user_id = int(context.args[0])
    invite_link: ChatInviteLink = await context.bot.create_chat_invite_link(
        chat_id=GROUP_ID,
        expire_date=datetime.now() + timedelta(seconds=60),
        member_limit=1
    )
    await context.bot.send_message(chat_id=user_id, text=f"ð ØªÙ ÙØ¨ÙÙ Ø§Ø´ØªØ±Ø§ÙÙ! ÙØ°Ø§ Ø±Ø§Ø¨Ø· Ø§ÙÙØ¬ÙÙØ¹Ø© (ØµØ§ÙØ­ ÙØ¯ÙÙÙØ© ÙØ§Ø­Ø¯Ø© ÙÙØ·):
{invite_link.invite_link}")

    data = load_data()
    data[str(user_id)] = {
        "start": datetime.now().isoformat()
    }
    save_data(data)

async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMINS:
        return

    if len(context.args) != 1:
        await update.message.reply_text("â ÙØ±Ø¬Ù ØªØ­Ø¯ÙØ¯ ID Ø§ÙÙØ³ØªØ®Ø¯Ù: /reject USER_ID")
        return

    user_id = int(context.args[0])
    await context.bot.send_message(chat_id=user_id, text="â ÙÙ ÙØªÙ ÙØ¨ÙÙ Ø§ÙØ¥ÙØµØ§Ù. ÙØ±Ø¬Ù Ø§ÙØªÙØ§ØµÙ ÙØ¹ Ø§ÙØ¥Ø¯Ø§Ø±Ø© Ø¥Ø°Ø§ ÙØ§Ù ÙÙØ§Ù Ø®Ø·Ø£.")

async def check_subscriptions(application):
    data = load_data()
    now = datetime.now()

    for user_id, sub in list(data.items()):
        start_date = datetime.fromisoformat(sub['start'])
        end_date = start_date + timedelta(days=28)
        notify_date = end_date - timedelta(days=3)

        if 'notified' not in sub and now >= notify_date:
            try:
                await application.bot.send_message(
                    chat_id=int(user_id),
                    text="â³ ØªØ¨ÙÙ 3 Ø£ÙØ§Ù Ø¹ÙÙ ÙÙØ§ÙØ© Ø§Ø´ØªØ±Ø§ÙÙ. ÙØ±Ø¬Ù Ø§ÙØªØ¬Ø¯ÙØ¯ ÙØªØ¬ÙØ¨ Ø§ÙØ·Ø±Ø¯ ÙÙ Ø§ÙÙØ¬ÙÙØ¹Ø©."
                )
                sub['notified'] = True
            except:
                pass

        if now >= end_date:
            try:
                await application.bot.ban_chat_member(chat_id=GROUP_ID, user_id=int(user_id), until_date=now + timedelta(seconds=60))
                await application.bot.unban_chat_member(chat_id=GROUP_ID, user_id=int(user_id))
            except:
                pass
            del data[user_id]

    save_data(data)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Start command received from: {update.effective_user.id}")
    await update.message.reply_text("ð ÙØ±Ø­Ø¨Ø§Ù! Ø§ÙØ±Ø¬Ø§Ø¡ Ø¥Ø±Ø³Ø§Ù Ø¥ÙØµØ§Ù Ø§ÙØ¯ÙØ¹ (ØµÙØ±Ø© ÙÙØ·) ÙÙØªÙ ÙØ±Ø§Ø¬Ø¹Ø© Ø§Ø´ØªØ±Ø§ÙÙ.")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("accept", accept_command))
    app.add_handler(CommandHandler("reject", reject_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_subscriptions, "interval", hours=24, args=[app])
    scheduler.start()

    print("â Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        with open("error.log", "w") as f:
            f.write("Fatal Error:\n")
            traceback.print_exc(file=f)
        sys.exit(1)
