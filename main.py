# -*- coding: utf-8 -*-
import os
import logging
import re
import time
from threading import Thread

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, ConversationHandler

from playwright.sync_api import sync_playwright
from keep_alive import keep_alive

# قم بوضع توكن البوت الذي حصلت عليه من BotFather
TOKEN = os.environ.get("BOT_TOKEN")  # يمكن أيضا وضع التوكن كسلسلة نصية هنا مباشرة
# معرّف المالك (admin) الذي سيتم إرسال الطلبات له ومخول بالأوامر الخاصة
OWNER_ID = 7123756100
# معرّف القناة الخاصة التي سيتم إرسال تحديثات الأسعار لها
CHANNEL_ID = -1002529600259
# رابط دعوة القناة الخاصة (يتم إرساله للمشتركين بعد الموافقة)
PRIVATE_CHANNEL_LINK = "https://t.me/+DaHQpgAd3doyMTg0"

# إعداد سجل (logging) للمساعدة في تتبع عمل البوت
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# متغيرات حالة المحادثة (Conversation) لأمر /monitor
CONTRACT_NAME, THRESHOLD = range(2)

# مجموعة لتتبع المستخدمين الذين ينتظرون إرسال إيصال الدفع
waiting_for_receipt = set()

# معلومات العقد الجاري متابعته (يتم ملؤها بعد التأكيد ✅)
monitor_info = {}  # سيتم استخدامه لتخزين page والسعر الأخير وغيرها

# تهيئة Playwright (مرة واحدة عند تشغيل البوت)
playwright = sync_playwright().start()
browser = playwright.chromium.launch(headless=True)
context = browser.new_context()  # سياق تصفح (مثل نافذة متصفح مستقلة)
# يمكن ضبط خيارات أخرى للمتصفح عند الحاجة (مثل حجم النافذة أو user agent)

def get_contract_page_and_price(contract_name):
    """
    البحث عن العقد في Webull وإرجاع الصفحة (Page) والسعر الحالي لهذا العقد وصورة لواجهة العقد.
    """
    page = context.new_page()
    # الذهاب إلى موقع Webull الرئيسي أو صفحة البحث
    page.goto("https://app.webull.com/")
    # محاولة العثور على حقل البحث وإدخال اسم العقد
    try:
        # قد يحتاج الأمر إلى تعديل بناءً على هيكل موقع Webull
        page.fill("input[placeholder=\"Search\"]", contract_name)
        page.keyboard.press("Enter")
    except Exception as e:
        logging.error(f"Search input not found or error in search: {e}")
    # انتظار تحميل النتائج أو الصفحة الخاصة بالعقد
    page.wait_for_timeout(3000)  # انتظر 3 ثواني (يمكن تعديلها حسب سرعة الموقع)
    # محاولة النقر على أول نتيجة إذا ظهرت قائمة نتائج (هذا يعتمد على طريقة عرض Webull)
    try:
        # إذا كانت هناك نتيجة أولى في البحث، حاول نقرها
        page.click("li >> text=\"" + contract_name + "\"")
    except Exception as e:
        logging.info("No direct search result click, maybe page navigated directly or element not found.")
    # انتظر قليلاً لتحميل صفحة العقد
    page.wait_for_timeout(5000)
    # التمرير للأعلى للتأكد من أن كل العناصر ظاهرة (إذا كان هناك تمرير)
    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception as e:
        logging.error(f"Scrolling error: {e}")
    # محاولة استخراج السعر الحالي من الصفحة
    price = None
    text_content = ""
    try:
        text_content = page.inner_text("body")
    except Exception as e:
        logging.error(f"Could not get page text content: {e}")
    if text_content:
        # محاولة استخراج سعر العقد من النص باستخدام تعابير منتظمة
        # أولا، ابحث عن نمط "Bid ... Ask ..." ومن ثم "Last ..." في المحتوى
        match_bid_ask = re.search(r"Bid\s*([0-9.]+)\s*Ask\s*([0-9.]+)", text_content)
        if match_bid_ask:
            bid = float(match_bid_ask.group(1))
            ask = float(match_bid_ask.group(2))
            logging.info(f"Found Bid={bid}, Ask={ask}")
        else:
            bid = ask = None
        match_last = re.search(r"Last\s*([0-9.]+)", text_content)
        if match_last:
            price = float(match_last.group(1))
            logging.info(f"Found Last price: {price}")
        elif bid is not None and ask is not None:
            # إذا لم يكن هناك Last، استخدم متوسط السعر بين العرض والطلب كتقدير
            price = (bid + ask) / 2.0
            logging.info(f"No explicit last price found, using mid of Bid/Ask as price: {price}")
        else:
            # إذا لم نجد النصوص، نحاول إيجاد أول رقم عشرى معقول كبديل
            nums = re.findall(r"([0-9]+(?:\.[0-9]+)?)", text_content)
            # تصفية الأرقام المحتملة إلى نطاق معقول (مثل أقل من 1000)
            candidates = [float(x) for x in nums if 0 < float(x) < 10000]
            if candidates:
                price = candidates[0]
                logging.info(f"Using first numeric candidate as price: {price}")
    # التقاط صورة للشاشة الحالية للعقد
    screenshot_bytes = page.screenshot(full_page=True)
    return page, price, screenshot_bytes

def monitor_loop(page, contract_name, threshold, last_price, bot):
    """
    حلقة مراقبة سعر العقد. ترسل تحديثات (صور) إلى القناة كلما تجاوز التغير في السعر العتبة المحددة.
    """
    logging.info(f"Started monitoring contract {contract_name} with threshold {threshold}")
    current_price = last_price
    last_sent_price = last_price
    try:
        while True:
            # الانتظار لفترة قبل التحقق التالي (يمكن ضبط الفترة حسب الحاجة، مثلاً 30 ثانية)
            time.sleep(30)
            # تحديث الصفحة أو إعادة تحميلها للحصول على أحدث الأسعار
            try:
                page.reload()
            except Exception as e:
                logging.error(f"Error reloading page for {contract_name}: {e}")
                break  # خروج من حلقة المراقبة إذا لم نستطع التحديث
            # استخراج السعر الجديد من الصفحة
            new_price = None
            try:
                new_price = None
                text_content = page.inner_text("body")
                if text_content:
                    match_bid_ask = re.search(r"Bid\s*([0-9.]+)\s*Ask\s*([0-9.]+)", text_content)
                    if match_bid_ask:
                        bid = float(match_bid_ask.group(1))
                        ask = float(match_bid_ask.group(2))
                    else:
                        bid = ask = None
                    match_last = re.search(r"Last\s*([0-9.]+)", text_content)
                    if match_last:
                        new_price = float(match_last.group(1))
                    elif bid is not None and ask is not None:
                        new_price = (bid + ask) / 2.0
                    else:
                        nums = re.findall(r"([0-9]+(?:\.[0-9]+)?)", text_content)
                        candidates = [float(x) for x in nums if 0 < float(x) < 10000]
                        if candidates:
                            new_price = candidates[0]
            except Exception as e:
                logging.error(f"Failed to retrieve price from page: {e}")
                new_price = None
            if new_price is None:
                continue  # إذا تعذر الحصول على السعر هذه الدورة، نتخطى إلى التالية
            current_price = new_price
            # التحقق من الفرق السعري
            if abs(current_price - last_sent_price) >= threshold:
                # إرسال صورة محدثة للعقد إلى القناة
                try:
                    screenshot_bytes = page.screenshot(full_page=True)
                    caption_text = f"تحديث سعر {contract_name}: {current_price}"
                    bot.send_photo(chat_id=CHANNEL_ID, photo=screenshot_bytes, caption=caption_text)
                    # تحديث آخر سعر أُرسلت عنده إشعار
                    last_sent_price = current_price
                    logging.info(f"Sent update to channel for {contract_name}, new price {current_price}")
                except Exception as e:
                    logging.error(f"Error sending photo update to channel: {e}")
    finally:
        logging.info(f"Monitoring loop for {contract_name} ended.")

# دالة الأمر /start - ترحيب بالمستخدم وعرض زر إرسال الإيصال
def start_command(update, context):
    user = update.effective_user
    welcome_text = f"مرحبًا {user.first_name}!\\nاضغط على الزر أدناه لإرسال إيصال الدفع للاشتراك."
    # إنشاء زر إرسال الإيصال
    button = InlineKeyboardButton("إرسال إيصال الدفع", callback_data="send_receipt")
    reply_markup = InlineKeyboardMarkup([[button]])
    update.message.reply_text(welcome_text, reply_markup=reply_markup)

# معالجة الضغط على زر "إرسال إيصال الدفع"
def send_receipt_callback(update, context):
    query = update.callback_query
    # تأكيد الاستلام السريع لزر (إزالة ساعة الانتظار في التطبيق)
    query.answer()
    # إرسال تعليمات للمستخدم لإرسال الإيصال
    context.bot.send_message(chat_id=query.from_user.id, text="يرجى الآن إرسال إيصال الدفع (كصورة أو ملف أو نص).")
    # إضافة المستخدم إلى قائمة انتظار الإيصالات
    waiting_for_receipt.add(query.from_user.id)

# معالجة رسالة الإيصال المرسلة من المستخدم
def receipt_handler(update, context):
    user_id = update.effective_user.id
    if user_id not in waiting_for_receipt:
        # إذا لم يكن المستخدم في وضع انتظار الإيصال، لا نفعل شيء
        return
    # تمت استلام الإيصال من المستخدم، إزالته من قائمة الانتظار
    waiting_for_receipt.discard(user_id)
    # إنشاء نص لوصف الطلب يتضمن معلومات المستخدم
    user = update.effective_user
    receipt_text = f"طلب اشتراك من المستخدم {user.first_name} (ID: {user_id})"
    # إذا أرسل المستخدم نصًا كإيصال
    if update.message.text:
        receipt_text += f"\\n\nمحتوى الإيصال:\n{update.message.text}"
        # إرسال الطلب كرسالة نصية إلى المالك مع أزرار الموافقة/الرفض
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("موافقة", callback_data=f"approve:{user_id}"),
                                         InlineKeyboardButton("رفض", callback_data=f"reject:{user_id}")]])
        context.bot.send_message(chat_id=OWNER_ID, text=receipt_text, reply_markup=keyboard)
    elif update.message.photo:
        # أخذ معرف الملف لأفضل دقة للصورة
        file_id = update.message.photo[-1].file_id
        # إرسال الصورة إلى المالك مع نفس التعليق
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("موافقة", callback_data=f"approve:{user_id}"),
                                         InlineKeyboardButton("رفض", callback_data=f"reject:{user_id}")]])
        context.bot.send_photo(chat_id=OWNER_ID, photo=file_id, caption=receipt_text, reply_markup=keyboard)
    elif update.message.document:
        file_id = update.message.document.file_id
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("موافقة", callback_data=f"approve:{user_id}"),
                                         InlineKeyboardButton("رفض", callback_data=f"reject:{user_id}")]])
        context.bot.send_document(chat_id=OWNER_ID, document=file_id, caption=receipt_text, reply_markup=keyboard)
    else:
        # إذا كان نوع رسالة آخر (احتمال ضعيف)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("موافقة", callback_data=f"approve:{user_id}"),
                                         InlineKeyboardButton("رفض", callback_data=f"reject:{user_id}")]])
        context.bot.send_message(chat_id=OWNER_ID, text=receipt_text, reply_markup=keyboard)
    # إشعار المستخدم بأن طلبه قيد المراجعة
    update.message.reply_text("تم إرسال إيصال الدفع إلى الإدارة للمراجعة. ستصلك رسالة بالرد قريبًا.")

# معاينة الرد على الموافقة على الاشتراك (زر "موافقة")
def approve_callback(update, context):
    query = update.callback_query
    query.answer("تمت الموافقة")
    # استخراج معرف المستخدم من البيانات
    try:
        target_user_id = int(query.data.split(":")[1])
    except:
        return
    # إرسال رسالة للمستخدم المستهدف تحتوي على رابط القناة الخاصة
    context.bot.send_message(chat_id=target_user_id, text=f"تهانينا! تم قبول اشتراكك.\nإليك رابط القناة الخاصة: {PRIVATE_CHANNEL_LINK}")
    # تحديث رسالة المالك لإزالة الأزرار وإضافة ملاحظة الموافقة
    try:
        if query.message.photo or query.message.document:
            # إذا كانت الرسالة الأصلية تحتوي على وسائط (صورة/ملف)
            new_caption = (query.message.caption or "") + "\\n\\n✅ تمت الموافقة"
            context.bot.edit_message_caption(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                             caption=new_caption)
        else:
            # إذا كانت الرسالة نصية
            new_text = (query.message.text or "") + "\\n\\n✅ تمت الموافقة"
            context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                          text=new_text)
    except Exception as e:
        logging.error(f"Failed to edit admin message after approval: {e}")

# معاينة الرد على رفض الاشتراك (زر "رفض")
def reject_callback(update, context):
    query = update.callback_query
    query.answer("تم الرفض")
    try:
        target_user_id = int(query.data.split(":")[1])
    except:
        return
    # إرسال رسالة للمستخدم المستهدف تعلمه بالرفض
    context.bot.send_message(chat_id=target_user_id, text="نعتذر، تم رفض طلب اشتراكك.")
    # تحديث رسالة المالك لحذف الأزرار وإضافة ملاحظة الرفض
    try:
        if query.message.photo or query.message.document:
            new_caption = (query.message.caption or "") + "\\n\\n❌ تم الرفض"
            context.bot.edit_message_caption(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                             caption=new_caption)
        else:
            new_text = (query.message.text or "") + "\\n\\n❌ تم الرفض"
            context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                          text=new_text)
    except Exception as e:
        logging.error(f"Failed to edit admin message after rejection: {e}")

# بدء المحادثة لأمر /monitor (هذه الدالة تستدعى عند إدخال الأمر من المالك)
def monitor_start(update, context):
    # التحقق أن من أدخل الأمر هو المالك فقط
    if update.effective_user.id != OWNER_ID:
        update.message.reply_text("هذا الأمر متاح للمالك فقط.")
        return ConversationHandler.END
    update.message.reply_text("أدخل اسم العقد الذي تريد مراقبته (مثال: SPXW 5605P 01May):")
    return CONTRACT_NAME

# استقبال اسم العقد من المالك
def monitor_contract_name(update, context):
    contract_name = update.message.text.strip()
    # حفظ اسم العقد مؤقتًا في بيانات المحادثة
    context.user_data['contract_name'] = contract_name
    # طلب الفارق السعري المطلوب
    update.message.reply_text("تم استلام اسم العقد. الآن أدخل قيمة الفارق السعري المطلوب للتنبيه (مثال: 30):")
    return THRESHOLD

# استقبال قيمة الفارق السعري
def monitor_threshold(update, context):
    threshold_text = update.message.text.strip()
    try:
        threshold_val = float(threshold_text)
    except:
        update.message.reply_text("الرجاء إرسال رقم صحيح لقيمة الفارق السعري.")
        return THRESHOLD  # إعادة طلب نفس المدخل إذا كان خطأ
    context.user_data['threshold'] = threshold_val
    contract_name = context.user_data.get('contract_name')
    if not contract_name:
        update.message.reply_text("حدث خطأ في اسم العقد. أعد المحاولة.")
        return ConversationHandler.END
    # محاولة فتح صفحة العقد والحصول على السعر الحالي والصورة
    update.message.reply_text("جاري البحث عن العقد ومعلوماته، يرجى الانتظار...")
    try:
        page, current_price, screenshot_bytes = get_contract_page_and_price(contract_name)
    except Exception as e:
        logging.error(f"Error in get_contract_page_and_price: {e}")
        update.message.reply_text("تعذر الوصول إلى بيانات العقد. تأكد من اسم العقد وحاول مرة أخرى.")
        return ConversationHandler.END
    if current_price is None:
        # في حال لم يتم العثور على السعر
        update.message.reply_text("لم يتم العثور على سعر العقد. قد يكون اسم العقد غير صحيح.")
    # إرسال الصورة الملتقطة للمالك مع زر التأكيد
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ صحيح", callback_data="confirm_monitor")]])
    caption_text = f"تم العثور على العقد: {contract_name}"
    if current_price is not None:
        caption_text += f"\\nالسعر الحالي: {current_price}"
    caption_text += "\\nاضغط ✅ للتأكيد والبدء بالمراقبة."
    context.bot.send_photo(chat_id=OWNER_ID, photo=screenshot_bytes, caption=caption_text, reply_markup=keyboard)
    # حفظ معلومات المراقبة الحالية في المتغير العام
    monitor_info.clear()
    monitor_info.update({
        "contract": contract_name,
        "threshold": threshold_val,
        "page": page,
        "price": current_price
    })
    # إعلام المالك بالتأكيد المطلوب
    update.message.reply_text("تم إرسال صورة العقد للتأكيد. اضغط على زر ✅ إذا كانت البيانات صحيحة لبدء المراقبة.")
    return ConversationHandler.END

# عند إلغاء المحادثة (على سبيل المثال إذا أرسل المستخدم /cancel)
def monitor_cancel(update, context):
    update.message.reply_text("تم إلغاء عملية المراقبة.")
    return ConversationHandler.END

# معالجة ضغط زر "✅ صحيح" لبدء المراقبة
def confirm_monitor_callback(update, context):
    query = update.callback_query
    # يجب أن يقوم بالضغط المالك فقط
    if query.from_user.id != OWNER_ID:
        query.answer("غير مسموح")
        return
    query.answer("جاري البدء بالمراقبة")
    # جلب معلومات العقد من المتغير العالمي
    contract_name = monitor_info.get("contract")
    threshold = monitor_info.get("threshold")
    page = monitor_info.get("page")
    last_price = monitor_info.get("price")
    if not contract_name or not page or threshold is None:
        query.edit_message_caption(caption="خطأ: لا توجد بيانات عقد للمراقبة.", reply_markup=None)
        return
    # تعديل الرسالة لحذف أزرار التأكيد وإضافة ملاحظة البدء
    try:
        if query.message.photo or query.message.document:
            new_caption = (query.message.caption or "") + "\\n\\n🔄 تم البدء بمراقبة السعر"
            context.bot.edit_message_caption(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                             caption=new_caption)
        else:
            new_text = (query.message.text or "") + "\\n\\n🔄 تم البدء بمراقبة السعر"
            context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=query.message.message_id,
                                          text=new_text)
    except Exception as e:
        logging.error(f"Failed to edit confirmation message: {e}")
    # بدء حلقة المراقبة في خيط منفصل حتى لا تعيق تفاعل البوت الأساسي
    monitor_thread = Thread(target=monitor_loop, args=(page, contract_name, threshold, last_price, context.bot))
    monitor_thread.daemon = True
    monitor_thread.start()

# الدالة الرئيسية لتشغيل البوت
def main():
    updater = Updater(TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # ربط الأوامر بالمعالجات
    dispatcher.add_handler(CommandHandler("start", start_command))
    # إعداد معالج المحادثة لأمر /monitor
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("monitor", monitor_start)],
        states={
            CONTRACT_NAME: [MessageHandler(Filters.text & ~Filters.command, monitor_contract_name)],
            THRESHOLD: [MessageHandler(Filters.text & ~Filters.command, monitor_threshold)],
        },
        fallbacks=[CommandHandler("cancel", monitor_cancel), CommandHandler("stop", monitor_cancel)]
    )
    dispatcher.add_handler(conv_handler)
    # معالجات الأزرار (ردود الأفعال)
    dispatcher.add_handler(CallbackQueryHandler(send_receipt_callback, pattern="^send_receipt$"))
    dispatcher.add_handler(CallbackQueryHandler(approve_callback, pattern="^approve:"))
    dispatcher.add_handler(CallbackQueryHandler(reject_callback, pattern="^reject:"))
    dispatcher.add_handler(CallbackQueryHandler(confirm_monitor_callback, pattern="^confirm_monitor$"))
    # معالج استقبال أي رسائل (للتحقق من الإيصالات المرسلة)
    dispatcher.add_handler(MessageHandler(Filters.all & ~Filters.command, receipt_handler))

    # بدء التشغيل والاستماع
    keep_alive()
    updater.start_polling()
    logging.info("Bot is running...")
    updater.idle()

if __name__ == "__main__":
    main()
