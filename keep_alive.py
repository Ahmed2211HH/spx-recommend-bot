from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    # تشغيل الخادم على المنفذ 8080
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    """تشغيل خادم Flask في线程 منفصل للإبقاء على التطبيق نشطًا."""
    t = Thread(target=run)
    t.daemon = True
    t.start()
