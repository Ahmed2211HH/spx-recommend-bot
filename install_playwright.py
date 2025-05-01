import subprocess

# تشغيل أمر تثبيت المتصفحات اللازمة لـ Playwright
# سيقوم هذا الأمر بتحميل WebKit و Firefox و Chromium. يمكن تحديد chromium فقط لتقليل الحجم:
subprocess.run(["playwright", "install", "chromium"])
