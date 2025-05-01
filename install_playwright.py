# -*- coding: utf-8 -*-
# هذا الملف يقوم بتثبيت المتصفحات اللازمة لتشغيل Playwright (يتم استدعاؤه أثناء عملية التحضير للنشر)
import subprocess
import sys

# تشغيل أمر التثبيت عبر pip
try:
    # الأمر التالي يقوم بتنزيل المتصفحات المطلوبة لـ Playwright
    subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps"], check=True)
    print("Playwright browsers installed successfully.")
except subprocess.CalledProcessError as e:
    print("Failed to install Playwright browsers:", e)
