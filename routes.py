"""
Routes — Flask API endpoints.
"""
import os
import time
import subprocess
import sqlite3
import pyautogui as pg
from flask import request, jsonify, send_file

from config import BASE_DIR, DB_PATH
from logger import log
from database import add_to_queue
from browser import open_browser


def register_routes(app):
    """Register all API routes on the Flask app."""

    # ------------------------------------------------------------------
    # Send a text message
    # ------------------------------------------------------------------
    @app.route('/send-message', methods=['POST'])
    def api_send_message():
        """Queue a text message for delivery.

        Accepts JSON or form-data with:
            phone   — required, recipient phone number
            message — required, text to send (supports \\n for newlines)
        """
        # Support both JSON and form-data
        data = request.get_json(silent=True) or {}
        phone = data.get('phone') or request.form.get('phone')
        message = data.get('message') or request.form.get('message', '')

        if not phone:
            return jsonify({"error": "Phone number is required"}), 400
        if not message:
            return jsonify({"error": "Message text is required"}), 400

        msg_id = add_to_queue(phone, message)
        return jsonify({"status": "queued", "message_id": msg_id}), 201

    # ------------------------------------------------------------------
    # Queue overview
    # ------------------------------------------------------------------
    @app.route('/queue-status', methods=['GET'])
    def queue_status():
        """Return a count of messages grouped by status."""
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
    # QR code helpers
    # ------------------------------------------------------------------
    @app.route('/scan-qr', methods=['GET'])
    def scan_qr():
        """Open WhatsApp Web so the user can scan the QR code."""
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

    @app.route('/view-qr', methods=['GET'])
    def view_qr():
        """Take a screenshot and return it (for viewing the QR code)."""
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
    # Health & debug
    # ------------------------------------------------------------------
    @app.route('/health', methods=['GET'])
    def health_check():
        """Basic health check — verifies DB connectivity."""
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

    @app.route('/debug', methods=['GET'])
    def debug_check():
        """Return diagnostic info about Chrome, Xvfb, and Fluxbox."""
        results = {}

        for label, cmd in [
            ("chrome_path",    ["which", "google-chrome"]),
            ("chrome_version", ["google-chrome", "--version"]),
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True)
                results[label] = r.stdout.strip() if r.returncode == 0 else "NOT FOUND"
            except Exception as e:
                results[label] = f"error: {e}"

        results["display"] = os.environ.get("DISPLAY", "NOT SET")

        for label, pattern in [("xvfb_running", "Xvfb"), ("fluxbox_running", "fluxbox")]:
            try:
                r = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
                results[label] = "yes" if r.returncode == 0 else "NO"
            except Exception as e:
                results[label] = f"error: {e}"

        return jsonify(results)

    @app.route('/test-chrome', methods=['GET'])
    def test_chrome():
        """Launch Chrome with a test URL and report whether it stayed alive."""
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
