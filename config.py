"""
Configuration — paths, constants, and environment setup.
"""
import os
import pyautogui as pg

# --- Environment ---
os.environ["DISPLAY"] = ":99"
os.environ["XAUTHORITY"] = "/root/.Xauthority"
pg.FAILSAFE = False

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
DB_PATH = os.path.join(BASE_DIR, 'db', 'queue.db')

# Ensure directories exist
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'db'), exist_ok=True)

# --- Asset images for screen detection ---
LOADED_CHECK_IMG = os.path.join(ASSETS_DIR, 'loaded_check.png')
INVALID_NUMBER_IMG = os.path.join(ASSETS_DIR, 'invalid_number.png')
MESSAGE_BOX_IMG = os.path.join(ASSETS_DIR, 'message_box.png')

# --- Screen resolution (must match Xvfb) ---
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# --- Telegram notifications ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
