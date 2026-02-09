import os
import time
import random
import threading
import subprocess
import sqlite3
import traceback
import uuid
import pyautogui as pg
import pyperclip
from flask import Flask, request, jsonify, send_file

# --- إعدادات البيئة ---
os.environ["DISPLAY"] = ":99"
os.environ["XAUTHORITY"] = "/root/.Xauthority"
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
MESSAGE_BOX_IMG = os.path.join(ASSETS_DIR, 'message_box.png')  # Input field image for locating

# Screen resolution (should match Xvfb settings)
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

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
            status TEXT DEFAULT 'pending',
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
    for attempt in range(3):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM messages WHERE status='pending' ORDER BY created_at ASC LIMIT 1")
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except sqlite3.OperationalError as e:
            log(f"DB locked (attempt {attempt+1}/3): {e}")
            time.sleep(1)
    return None

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
    """Open Chrome with Docker and Fluxbox compatible settings"""
    log(f"Attempting to open Chrome with URL: {url}")
    
    # Kill any existing Chrome processes
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome"], stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass
    
    # Clean up Chrome profile lock files
    profile_dir = "/data/chrome_profile"
    lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie"]
    for lock_file in lock_files:
        lock_path = os.path.join(profile_dir, lock_file)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
                log(f"Removed lock file: {lock_file}")
        except Exception as e:
            log(f"Could not remove {lock_file}: {e}")
    
    # Ensure DISPLAY is set
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    
    try:
        process = subprocess.Popen([
            "google-chrome",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--start-maximized",
            "--window-size=1920,1080",
            "--window-position=0,0",
            "--user-data-dir=/data/chrome_profile",
            url
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log(f"Chrome started with PID: {process.pid}")
        return process
    except Exception as e:
        log(f"ERROR starting Chrome: {e}")
        return None

def wait_for_chat_load(timeout=40, assume_loaded_on_timeout=True):
    """
    Wait for WhatsApp chat to load.
    If assume_loaded_on_timeout=True, will assume chat loaded if no invalid number detected.
    """
    start_wait = time.time()
    check_count = 0
    
    while time.time() - start_wait < timeout:
        check_count += 1
        elapsed = int(time.time() - start_wait)
        
        try:
            # Try to detect loaded chat with lower confidence
            loaded_loc = pg.locateOnScreen(LOADED_CHECK_IMG, confidence=0.6)
            if loaded_loc:
                log(f"Chat loaded detected at check #{check_count} ({elapsed}s)")
                return "loaded"
            
            # Check for invalid number
            invalid_loc = pg.locateOnScreen(INVALID_NUMBER_IMG, confidence=0.6)
            if invalid_loc:
                log(f"Invalid number detected at check #{check_count} ({elapsed}s)")
                return "invalid"
                
        except Exception as e:
            if check_count <= 2:  # Only log first few errors
                log(f"Image detection error: {e}")
        
        # Log progress every 10 seconds
        if check_count % 10 == 0:
            log(f"Still waiting for chat... ({elapsed}s elapsed)")
        
        time.sleep(1)
    
    # Timeout reached - take debug screenshot
    try:
        debug_path = os.path.join(BASE_DIR, 'debug_timeout.png')
        pg.screenshot(debug_path)
        log(f"Timeout screenshot saved to {debug_path}")
    except Exception as e:
        log(f"Could not save debug screenshot: {e}")
    
    # If assume_loaded_on_timeout is True, we proceed anyway
    # This helps when the loaded_check.png doesn't match current WhatsApp UI
    if assume_loaded_on_timeout:
        log("Timeout reached, but assuming chat loaded (image detection may have failed)")
        return "loaded"
    
    return "timeout"

# --- 3. منطق الإرسال (Core Logic) ---

def find_message_input():
    """Find the message input field - try image recognition first, then fallback to coordinates"""
    # Try to find the input field by image
    try:
        location = pg.locateOnScreen(MESSAGE_BOX_IMG, confidence=0.8)
        if location:
            # Click center of the found element
            center = pg.center(location)
            log(f"Found message input at {center}")
            return center
    except Exception as e:
        log(f"Could not locate input by image: {e}")
    
    # Fallback: Use coordinates relative to screen size
    # WhatsApp message box is typically at the bottom center
    # Approximately 60-70% from left, 90-95% from top
    x = int(SCREEN_WIDTH * 0.60)  # 60% across the screen
    y = int(SCREEN_HEIGHT * 0.92)  # Near the bottom
    log(f"Using fallback coordinates: ({x}, {y})")
    return (x, y)


def process_message(task):
    phone = task['phone']
    message = task['message']
    image_path = task['image_path']
    
    log(f"Processing ID:{task['id']} -> {phone}")
    
    try:
        # 1. فتح واتساب
        link = f"https://web.whatsapp.com/send?phone={phone}"
        open_browser(link)
        
        # 2. الانتظار
        status = wait_for_chat_load()
        if status != "loaded":
            log(f"Failed loading chat: {status}")
            pg.hotkey('ctrl', 'w')
            return False

        time.sleep(2)
        
        # 3. البحث عن حقل الإدخال والنقر عليه
        input_pos = find_message_input()
        pg.click(x=input_pos[0], y=input_pos[1])
        time.sleep(0.5)
        
        # التأكد من التركيز بالضغط مرة أخرى
        pg.click(x=input_pos[0], y=input_pos[1])
        time.sleep(0.3)
        
        # 4. السيناريو
        if image_path and os.path.exists(image_path):
            # نسخ الصورة للحافظة
            if not copy_image_to_clipboard_linux(image_path):
                pg.hotkey('ctrl', 'w')
                return False
            
            # لصق الصورة
            pg.hotkey('ctrl', 'v')
            time.sleep(3)  # انتظار أطول لتحميل الصورة
            
            if message:
                # عند لصق صورة، يظهر حقل التعليق (Caption) تلقائياً
                # يجب كتابة النص مباشرة بعد لصق الصورة
                time.sleep(0.5)
                pyperclip.copy(message)
                time.sleep(0.5)
                
                # التحقق من نسخ النص
                copied_text = pyperclip.paste()
                log(f"Copied to clipboard: {copied_text[:50]}..." if len(copied_text) > 50 else f"Copied to clipboard: {copied_text}")
                
                # لصق النص في حقل التعليق
                pg.hotkey('ctrl', 'v')
                time.sleep(1)
        else:
            if message:
                # نسخ النص للحافظة
                pyperclip.copy(message)
                time.sleep(0.5)
                
                # التحقق من نسخ النص
                copied_text = pyperclip.paste()
                log(f"Copied to clipboard: {copied_text[:50]}..." if len(copied_text) > 50 else f"Copied to clipboard: {copied_text}")
                
                # لصق النص
                pg.hotkey('ctrl', 'v')
                time.sleep(1)

        # 5. الإرسال بالضغط على Enter
        time.sleep(0.5)
        pg.press('enter')
        log("Pressed Enter to send")
        
        # انتظار إرسال الرسالة
        time.sleep(3)
        
        # إغلاق التاب
        pg.hotkey('ctrl', 'w')
        return True

    except Exception as e:
        log(f"Error processing: {e}")
        traceback.print_exc()
        try:
            pg.hotkey('ctrl', 'w')
        except Exception:
            pass
        return False

# --- 4. الـ Worker ---

def worker_loop():
    log("Worker thread started...")
    while True:
        try:
            task = get_next_pending()
            if task:
                update_status(task['id'], 'processing')
                success = process_message(task)
                if success:
                    update_status(task['id'], 'completed')
                    log(f"Task {task['id']} COMPLETED.")
                    sleep_time = random.randint(30, 60)
                    log(f"Sleeping {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    update_status(task['id'], 'failed')
                    log(f"Task {task['id']} FAILED.")
                    time.sleep(5)
            else:
                time.sleep(5)
        except Exception as e:
            log(f"Worker Error: {e}")
            time.sleep(5)

# --- 5. الـ API Endpoint ---

@app.route('/send-message', methods=['POST'])
def api_send_message():
    phone = request.form.get('phone')
    message = request.form.get('message', '')
    image = request.files.get('image')

    if not phone:
        return jsonify({"error": "Phone number is required"}), 400

    saved_image_path = None
    if image:
        ext = os.path.splitext(image.filename)[1]
        filename = f"{uuid.uuid4()}{ext}"
        saved_image_path = os.path.join(UPLOADS_DIR, filename)
        image.save(saved_image_path)

    msg_id = add_to_queue(phone, message, saved_image_path)

    return jsonify({
        "status": "queued",
        "message_id": msg_id
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
    # Kill any existing Chrome instances first
    try:
        subprocess.run(["pkill", "-f", "chrome"], stderr=subprocess.DEVNULL)
        time.sleep(2)
    except Exception:
        pass
    
    open_browser("https://web.whatsapp.com")
    log("Opening WhatsApp Web...")
    
    # Wait for Chrome to fully load
    time.sleep(15)
    
    # Try to focus the Chrome window
    try:
        subprocess.run(["xdotool", "search", "--name", "WhatsApp", "windowactivate"], 
                      stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        pass
    
    return jsonify({"msg": "Browser opened. Wait a few seconds then check /view-qr"})

@app.route('/view-qr', methods=['GET'])
def view_qr():
    path = os.path.join(BASE_DIR, 'debug_qr.png')
    try:
        subprocess.run(["scrot", path], check=True)
    except Exception as e:
        log(f"Scrot failed: {e}")
        try:
            pg.screenshot(path)
        except Exception as e2:
            log(f"Screenshot failed: {e2}")
            return jsonify({"error": "Failed to take screenshot"}), 500
            
    return send_file(path, mimetype='image/png')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring"""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return jsonify({
        "status": "running",
        "database": db_status,
        "display": os.environ.get("DISPLAY", "not set")
    })

@app.route('/debug', methods=['GET'])
def debug_check():
    """Debug endpoint to check system status"""
    results = {}
    
    # Check Chrome installation
    try:
        result = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)
        results["chrome_path"] = result.stdout.strip() if result.returncode == 0 else "NOT FOUND"
    except Exception as e:
        results["chrome_path"] = f"error: {e}"
    
    # Check Chrome version
    try:
        result = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True)
        results["chrome_version"] = result.stdout.strip() if result.returncode == 0 else "error"
    except Exception as e:
        results["chrome_version"] = f"error: {e}"
    
    # Check DISPLAY
    results["display"] = os.environ.get("DISPLAY", "NOT SET")
    
    # Check Xvfb is running
    try:
        result = subprocess.run(["pgrep", "-f", "Xvfb"], capture_output=True, text=True)
        results["xvfb_running"] = "yes" if result.returncode == 0 else "NO"
    except Exception as e:
        results["xvfb_running"] = f"error: {e}"
    
    # Check fluxbox is running
    try:
        result = subprocess.run(["pgrep", "-f", "fluxbox"], capture_output=True, text=True)
        results["fluxbox_running"] = "yes" if result.returncode == 0 else "NO"
    except Exception as e:
        results["fluxbox_running"] = f"error: {e}"
    
    # Test Chrome can start
    try:
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        process = subprocess.Popen(
            ["google-chrome", "--no-sandbox", "--version"],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(timeout=5)
        results["chrome_test"] = "ok" if process.returncode == 0 else f"failed: {stderr.decode()[:200]}"
    except Exception as e:
        results["chrome_test"] = f"error: {e}"
    
    return jsonify(results)

@app.route('/test-chrome', methods=['GET'])
def test_chrome():
    """Test Chrome launch and capture any errors"""
    log("Testing Chrome launch...")
    
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    
    try:
        # Launch Chrome with stderr capture
        process = subprocess.Popen([
            "google-chrome",
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-software-rasterizer",
            "--start-maximized",
            "--window-size=1920,1080",
            "--window-position=0,0",
            "--user-data-dir=/data/chrome_profile",
            "https://www.google.com"
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        log(f"Chrome test started with PID: {process.pid}")
        
        # Wait a bit for Chrome to start or fail
        time.sleep(5)
        
        # Check if process is still running
        poll = process.poll()
        
        if poll is None:
            # Process still running - good sign
            return jsonify({
                "status": "Chrome appears to be running",
                "pid": process.pid,
                "check_vnc": "Look at VNC screen now"
            })
        else:
            # Process exited - get error output
            stdout, stderr = process.communicate()
            return jsonify({
                "status": "Chrome exited",
                "exit_code": poll,
                "stderr": stderr.decode()[:2000],
                "stdout": stdout.decode()[:500]
            })
            
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    init_db()
    threading.Thread(target=worker_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)