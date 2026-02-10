"""
WhatsApp Web Automation Server
==============================
Minimal entry point: creates the Flask app, registers routes,
initialises the database, and starts the background worker.
"""
import threading
from flask import Flask

import config  # noqa: F401  — triggers env/path setup on import
from database import init_db
from routes import register_routes
from worker import worker_loop

app = Flask(__name__)
register_routes(app)

if __name__ == '__main__':
    init_db()
    threading.Thread(target=worker_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)