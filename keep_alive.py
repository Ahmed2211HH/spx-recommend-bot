# -*- coding: utf-8 -*-
# ملف لإبقاء التطبيق حياً على منصة الاستضافة (مثل Render)
from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive."

def run():
    # تشغيل التطبيق Flask على المنفذ المحدد من قبل Render أو على المنفذ 8080 افتراضياً
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    # تشغيل الخادم في خيط منفصل حتى لا يمنع تنفيذ الكود الرئيسي
    t = Thread(target=run)
    t.daemon = True
    t.start()
