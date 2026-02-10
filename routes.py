"""
Routes — Flask API endpoints.
"""
import os
import time
import uuid
import subprocess
import sqlite3
import pyautogui as pg
from flask import request, jsonify, send_file

from config import BASE_DIR, UPLOADS_DIR, DB_PATH
from logger import log
from database import add_to_queue
from browser import open_browser


def register_routes(app):
    """Register all API routes on the Flask app."""

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
        return jsonify({"status": "queued", "message_id": msg_id}), 201

    # ------------------------------------------------------------------

    @app.route('/queue-status', methods=['GET'])
    def queue_status():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute(
            "SELECT status, count(*) as count FROM messages GROUP BY status"
        )
        rows = c.fetchall()
        conn.close()
        return jsonify({row['status']: row['count'] for row in rows})

    # ------------------------------------------------------------------

    @app.route('/scan-qr', methods=['GET'])
    def scan_qr():
        try:
            subprocess.run(["pkill", "-f", "chrome"], stderr=subprocess.DEVNULL)
            time.sleep(2)
        except Exception:
            pass

        open_browser("https://web.whatsapp.com")
        log("Opening WhatsApp Web…")
        time.sleep(15)

        try:
            subprocess.run(
                ["xdotool", "search", "--name", "WhatsApp", "windowactivate"],
                stderr=subprocess.DEVNULL, timeout=5,
            )
        except Exception:
            pass

        return jsonify({"msg": "Browser opened. Wait a few seconds then check /view-qr"})

    # ------------------------------------------------------------------

    @app.route('/view-qr', methods=['GET'])
    def view_qr():
        path = os.path.join(BASE_DIR, 'debug_qr.png')
        try:
            subprocess.run(["scrot", path], check=True)
        except Exception:
            try:
                pg.screenshot(path)
            except Exception:
                return jsonify({"error": "Failed to take screenshot"}), 500

        return send_file(path, mimetype='image/png')

    # ------------------------------------------------------------------

    @app.route('/health', methods=['GET'])
    def health_check():
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("SELECT 1")
            conn.close()
            db_status = "ok"
        except Exception as e:
            db_status = f"error: {e}"

        return jsonify({
            "status": "running",
            "database": db_status,
            "display": os.environ.get("DISPLAY", "not set"),
        })

    # ------------------------------------------------------------------

    @app.route('/debug', methods=['GET'])
    def debug_check():
        results = {}

        # Chrome path
        try:
            r = subprocess.run(["which", "google-chrome"], capture_output=True, text=True)
            results["chrome_path"] = r.stdout.strip() if r.returncode == 0 else "NOT FOUND"
        except Exception as e:
            results["chrome_path"] = f"error: {e}"

        # Chrome version
        try:
            r = subprocess.run(["google-chrome", "--version"], capture_output=True, text=True)
            results["chrome_version"] = r.stdout.strip() if r.returncode == 0 else "error"
        except Exception as e:
            results["chrome_version"] = f"error: {e}"

        # Display
        results["display"] = os.environ.get("DISPLAY", "NOT SET")

        # Xvfb
        try:
            r = subprocess.run(["pgrep", "-f", "Xvfb"], capture_output=True, text=True)
            results["xvfb_running"] = "yes" if r.returncode == 0 else "NO"
        except Exception as e:
            results["xvfb_running"] = f"error: {e}"

        # Fluxbox
        try:
            r = subprocess.run(["pgrep", "-f", "fluxbox"], capture_output=True, text=True)
            results["fluxbox_running"] = "yes" if r.returncode == 0 else "NO"
        except Exception as e:
            results["fluxbox_running"] = f"error: {e}"

        # Chrome test
        try:
            env = os.environ.copy()
            env["DISPLAY"] = ":99"
            p = subprocess.Popen(
                ["google-chrome", "--no-sandbox", "--version"],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            stdout, stderr = p.communicate(timeout=5)
            results["chrome_test"] = "ok" if p.returncode == 0 else f"failed: {stderr.decode()[:200]}"
        except Exception as e:
            results["chrome_test"] = f"error: {e}"

        return jsonify(results)

    # ------------------------------------------------------------------

    @app.route('/test-chrome', methods=['GET'])
    def test_chrome():
        log("Testing Chrome launch…")
        env = os.environ.copy()
        env["DISPLAY"] = ":99"

        try:
            process = subprocess.Popen([
                "google-chrome",
                "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--disable-software-rasterizer",
                "--start-maximized", "--window-size=1920,1080",
                "--window-position=0,0",
                "--user-data-dir=/data/chrome_profile",
                "https://www.google.com",
            ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            log(f"Chrome test PID: {process.pid}")
            time.sleep(5)
            poll = process.poll()

            if poll is None:
                return jsonify({
                    "status": "Chrome appears to be running",
                    "pid": process.pid,
                    "check_vnc": "Look at VNC screen now",
                })
            else:
                stdout, stderr = process.communicate()
                return jsonify({
                    "status": "Chrome exited",
                    "exit_code": poll,
                    "stderr": stderr.decode()[:2000],
                    "stdout": stdout.decode()[:500],
                })
        except Exception as e:
            return jsonify({"error": str(e)})
