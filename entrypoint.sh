#!/bin/bash

# تنظيف الملفات القديمة
rm -f /tmp/.X99-lock

# 1. تشغيل الشاشة الوهمية
Xvfb :99 -screen 0 1920x1080x24 -ac &

# تصدير المتغيرات
export DISPLAY=:99
export XAUTHORITY=/root/.Xauthority
touch /root/.Xauthority

# 2. تشغيل مدير النوافذ (Fluxbox)
fluxbox &

# انتظار لضمان تحميل الواجهة
sleep 3

# 3. Clean Chrome profile lock files (important for container restarts)
echo "Cleaning Chrome profile locks..."
rm -f /data/chrome_profile/SingletonLock
rm -f /data/chrome_profile/SingletonSocket  
rm -f /data/chrome_profile/SingletonCookie
rm -rf /data/chrome_profile/Singleton*
echo "Chrome locks cleaned."

# 4. تشغيل VNC Server للمشاهدة المباشرة
x11vnc -display :99 -nopw -forever -shared -rfbport 5900 &

# 5. تشغيل noVNC للمشاهدة من المتصفح
websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

sleep 2

# 6. تشغيل التطبيق
exec python app.py