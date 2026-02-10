"""
Browser — Chrome control, clipboard, and screen-detection helpers.
"""
import os
import time
import subprocess
from PIL import Image
import pyautogui as pg

from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, BASE_DIR,
    LOADED_CHECK_IMG, INVALID_NUMBER_IMG, MESSAGE_BOX_IMG,
)
from logger import log


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

def copy_image_to_clipboard(image_path):
    """Convert any image to PNG and copy it to the X clipboard via xclip."""
    try:
        png_path = image_path + ".clipboard.png"
        img = Image.open(image_path)
        img.save(png_path, "PNG")
        log(f"Converted image to PNG: {png_path}")

        # Popen keeps xclip alive so it can serve the clipboard on paste
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard", "-t", "image/png", "-i", png_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        time.sleep(1)

        if process.poll() is not None:
            stderr = process.stderr.read().decode()
            log(f"xclip exited early: {stderr}")
            return False

        log("Image copied to clipboard successfully (xclip serving)")
        return True
    except Exception as e:
        log(f"Error copying image to clipboard: {e}")
        return False


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------

def open_browser(url):
    """Launch Chrome with Docker / Fluxbox compatible flags."""
    log(f"Opening Chrome → {url}")

    # Kill existing Chrome
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome"], stderr=subprocess.DEVNULL)
        time.sleep(1)
    except Exception:
        pass

    # Remove stale lock files
    profile_dir = "/data/chrome_profile"
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(profile_dir, lock)
        try:
            if os.path.exists(path):
                os.remove(path)
                log(f"Removed lock: {lock}")
        except Exception as e:
            log(f"Could not remove {lock}: {e}")

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
            url,
        ], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log(f"Chrome PID: {process.pid}")
        return process
    except Exception as e:
        log(f"ERROR starting Chrome: {e}")
        return None


# ---------------------------------------------------------------------------
# Screen detection
# ---------------------------------------------------------------------------

def wait_for_chat_load(timeout=40, assume_loaded_on_timeout=True):
    """
    Wait for WhatsApp chat to appear.
    Returns: 'loaded', 'invalid', or 'timeout'.
    """
    start = time.time()
    checks = 0

    while time.time() - start < timeout:
        checks += 1
        elapsed = int(time.time() - start)

        try:
            if pg.locateOnScreen(LOADED_CHECK_IMG, confidence=0.6):
                log(f"Chat loaded (check #{checks}, {elapsed}s)")
                return "loaded"

            if pg.locateOnScreen(INVALID_NUMBER_IMG, confidence=0.6):
                log(f"Invalid number detected (check #{checks}, {elapsed}s)")
                return "invalid"
        except Exception as e:
            if checks <= 2:
                log(f"Image detection error: {e}")

        if checks % 10 == 0:
            log(f"Still waiting for chat… ({elapsed}s)")

        time.sleep(1)

    # Timeout — save debug screenshot
    try:
        debug = os.path.join(BASE_DIR, "debug_timeout.png")
        pg.screenshot(debug)
        log(f"Timeout screenshot → {debug}")
    except Exception:
        pass

    if assume_loaded_on_timeout:
        log("Timeout — assuming chat loaded (detection may have failed)")
        return "loaded"

    return "timeout"


def find_message_input():
    """Locate the message input field by image, with coordinate fallback."""
    try:
        loc = pg.locateOnScreen(MESSAGE_BOX_IMG, confidence=0.8)
        if loc:
            center = pg.center(loc)
            log(f"Message input found at {center}")
            return center
    except Exception as e:
        log(f"Could not locate input by image: {e}")

    x = int(SCREEN_WIDTH * 0.60)
    y = int(SCREEN_HEIGHT * 0.92)
    log(f"Using fallback input coords: ({x}, {y})")
    return (x, y)


def take_screenshot(name="debug"):
    """Take a screenshot and return the file path."""
    path = os.path.join(BASE_DIR, f"{name}.png")
    try:
        pg.screenshot(path)
        return path
    except Exception as e:
        log(f"Screenshot failed: {e}")
        return None
