import os
import time
import random
import threading
import subprocess
import sqlite3
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
import pyautogui as pg
import pyperclip

# --- إعدادات البيئة ---
os.environ["DISPLAY"] = ":99"
pg.FAILSAFE = False

app = Flask(__name__)

# مسارات المجلدات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'db', 'queue.db')

# التأكد من وجود المجلدات
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'db'), exist_ok=True)

# صور التحقق
LOADED_CHECK_IMG = os.path.join(ASSETS_DIR, 'loaded_check.png')
INVALID_NUMBER_IMG = os.path.join(ASSETS_DIR, 'invalid_number.png')

# --- 1. التعامل مع قاعدة البيانات (SQLite) ---

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            message TEXT,
            image_path TEXT,
            status TEXT DEFAULT 'pending', -- pending, processing, completed, failed
            attempts INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_to_queue(phone, message, image_path=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (phone, message, image_path) VALUES (?, ?, ?)', 
              (phone, message, image_path))
    conn.commit()
    msg_id = c.lastrowid
    conn.close()
    return msg_id

def get_next_pending():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # نأخذ أقدم رسالة لم يتم إرسالها
    c.execute("SELECT * FROM messages WHERE status='pending' ORDER BY created_at ASC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_status(msg_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE messages SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, msg_id))
    conn.commit()
    conn.close()

# --- 2. دوال النظام والتحكم (Helpers) ---

def log(text):
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)

def copy_image_to_clipboard_linux(image_path):
    try:
        subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png", "-i", image_path], check=True)
        return True
    except Exception as e:
        log(f"Error xclip: {e}")
        return False

def open_browser(url):
    # نستخدم Popen لفتح المتصفح وعدم انتظار إغلاقه
    subprocess.Popen([
        "google-chrome", "--no-sandbox", "--disable-gpu", "--start-maximized", 
        "--user-data-dir=/data/chrome_profile", url
    ])

def wait_for_chat_load(timeout=40):
    start_wait = time.time()
    while time.time() - start_wait < timeout:
        try:
            if pg.locateOnScreen(LOADED_CHECK_IMG, confidence=0.8):
                return "loaded"
            if pg.locateOnScreen(INVALID_NUMBER_IMG, confidence=0.8):
                return "invalid"
        except:
            pass
        time.sleep(1)
    return "timeout"

# --- 3. منطق الإرسال (Core Logic) ---

def process_message(task):
    phone = task['phone']
    message = task['message']
    image_path = task['image_path']
    
    log(f"Processing ID:{task['id']} -> {phone}")
    
    try:
        # 1. فتح واتساب
        link = f"https://web.whatsapp.com/send?phone={phone}"
        if not image_path:
            # إذا نص فقط، نكتبه في الرابط ليدخل مربع الكتابة مباشرة
            # لكن يجب ترميز النص للرابط (URL Encode) - هنا نعتمد على النسخ واللصق أفضل للعربية
            pass
            
        open_browser(link)
        
        # 2. الانتظار
        status = wait_for_chat_load()
        if status != "loaded":
            log(f"Failed loading chat: {status}")
            pg.hotkey('ctrl', 'w')
            return False

        time.sleep(2)
        
        # 3. التركيز
        pg.click(x=960, y=540) # وسط الشاشة
        
        # 4. السيناريو
        if image_path and os.path.exists(image_path):
            # --- حالة صورة + نص (Caption) ---
            if not copy_image_to_clipboard_linux(image_path):
                pg.hotkey('ctrl', 'w')
                return False
            
            pg.hotkey('ctrl', 'v') # لصق الصورة
            time.sleep(2) # انتظار المعاينة
            
            if message:
                pyperclip.copy(message) # نسخ النص
                time.sleep(0.5)
                pg.hotkey('ctrl', 'v') # لصق النص كـ Caption
                time.sleep(1)
                
        else:
            # --- حالة نص فقط ---
            # نتأكد أننا في مربع الكتابة
            if message:
                pyperclip.copy(message)
                time.sleep(0.5)
                pg.hotkey('ctrl', 'v')
                time.sleep(1)

        # 5. الإرسال
        pg.press('enter')
        log("Pressed Enter")
        
        time.sleep(3) # انتظار خروج الرسالة
        pg.hotkey('ctrl', 'w') # إغلاق
        return True

    except Exception as e:
        log(f"Error processing: {e}")
        try: pg.hotkey('ctrl', 'w') 
        except: pass
        return False

# --- 4. الـ Worker (يعمل في الخلفية) ---

def worker_loop():
    log("Worker thread started...")
    while True:
        task = get_next_pending()
        
        if task:
            # تحديث الحالة إلى جاري المعالجة
            update_status(task['id'], 'processing')
            
            success = process_message(task)
            
            if success:
                update_status(task['id'], 'completed')
                log(f"Task {task['id']} COMPLETED.")
                # فترة راحة عشوائية بين الرسائل (حماية)
                sleep_time = random.randint(30, 60)
                log(f"Sleeping {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                update_status(task['id'], 'failed')
                log(f"Task {task['id']} FAILED.")
                time.sleep(5) # راحة قصيرة بعد الفشل
        else:
            # لا توجد رسائل، ننتظر قليلاً ثم نعيد الفحص
            time.sleep(5)

# --- 5. الـ API Endpoint ---

@app.route('/send-message', methods=['POST'])
def api_send_message():
    # استقبال البيانات (Form Data لدعم رفع الصور)
    phone = request.form.get('phone')
    message = request.form.get('message', '')
    image = request.files.get('image') # اختياري

    if not phone:
        return jsonify({"error": "Phone number is required"}), 400

    saved_image_path = None
    if image:
        # حفظ الصورة بامتداد فريد
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        saved_image_path = os.path.join(UPLOADS_DIR, filename)
        image.save(saved_image_path)

    # الإضافة للطابور
    msg_id = add_to_queue(phone, message, saved_image_path)

    return jsonify({
        "status": "queued",
        "message_id": msg_id,
        "position": "end of queue"
    }), 201

@app.route('/queue-status', methods=['GET'])
def queue_status():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT status, count(*) as count FROM messages GROUP BY status")
    rows = c.fetchall()
    conn.close()
    return jsonify({row['status']: row['count'] for row in rows})

@app.route('/scan-qr', methods=['GET'])
def scan_qr():
    open_browser("https://web.whatsapp.com")
    time.sleep(10) # وقت للفتح
    return jsonify({"msg": "Browser opened for QR scan. Check /view-qr"})

@app.route('/view-qr', methods=['GET'])
def view_qr():
    from flask import send_file
    path = os.path.join(BASE_DIR, 'debug_qr.png')
    pg.screenshot(path)
    return send_file(path, mimetype='image/png')

# --- التشغيل ---
if __name__ == '__main__':
    # 1. تهيئة قاعدة البيانات
    init_db()
    
    # 2. تشغيل الـ Worker في خيط منفصل
    threading.Thread(target=worker_loop, daemon=True).start()
    
    # 3. تشغيل الـ Flask
    app.run(host='0.0.0.0', port=5000)