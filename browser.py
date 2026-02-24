"""
Browser — Chrome control, clipboard, and screen-detection helpers.
"""
import os
import time
import subprocess
import pyautogui as pg

from config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, BASE_DIR,
    LOADED_CHECK_IMG, INVALID_NUMBER_IMG, MESSAGE_BOX_IMG,
)
from logger import log


# ── Display environment (shared by all subprocess calls) ─────────────

def _display_env():
    """Return an env dict with DISPLAY=:99 set."""
    env = os.environ.copy()
    env["DISPLAY"] = ":99"
    return env


# ── Clipboard & text input ───────────────────────────────────────────

def copy_text_to_clipboard(text):
    """Copy text to the X clipboard (tries xsel first, then xclip)."""
    env = _display_env()
    try:
        subprocess.run(["pkill", "-f", "xclip"], stderr=subprocess.DEVNULL)

        # Primary: xsel
        result = subprocess.run(
            ["xsel", "--clipboard", "--input"],
            input=text.encode("utf-8"),
            timeout=2, capture_output=True, env=env,
        )
        if result.returncode == 0:
            return True

        # Fallback: xclip
        result = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode("utf-8"),
            timeout=2, capture_output=True, env=env,
        )
        return result.returncode == 0
    except Exception as e:
        log(f"Error copying text to clipboard: {e}")
        return False


def type_text_via_xdotool(text):
    """Type text character-by-character using xdotool (clipboard bypass)."""
    try:
        subprocess.run(
            ["xdotool", "type", "--clearmodifiers", "--delay", "20", text],
            env=_display_env(), timeout=10, capture_output=True,
        )
        return True
    except Exception as e:
        log(f"xdotool type failed: {e}")
        return False


def paste_text(text):
    """Paste text into the focused field.

    Supports multi-line messages: each ``\\n`` in *text* becomes a
    Shift+Enter inside WhatsApp Web (plain Enter would send the message).
    """
    lines = text.split("\n")
    env = _display_env()

    for i, line in enumerate(lines):
        # Paste the current line via clipboard
        if line:
            if copy_text_to_clipboard(line):
                time.sleep(0.1)
                try:
                    subprocess.run(
                        ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                        env=env, timeout=2,
                    )
                except Exception:
                    pg.hotkey('ctrl', 'v')
                time.sleep(0.2)
            else:
                # Fallback: type the line directly
                log("Clipboard paste failed, trying xdotool type…")
                type_text_via_xdotool(line)

        # Insert a newline (Shift+Enter) between lines, but not after the last
        if i < len(lines) - 1:
            try:
                subprocess.run(
                    ["xdotool", "key", "--clearmodifiers", "shift+Return"],
                    env=env, timeout=2,
                )
            except Exception:
                pg.hotkey('shift', 'enter')
            time.sleep(0.1)

    return True


# ── Chrome ───────────────────────────────────────────────────────────

def _remove_chrome_locks():
    """Remove stale Chrome lock files."""
    profile_dir = "/data/chrome_profile"
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(profile_dir, lock)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def open_browser(url):
    """Kill any existing Chrome and launch a fresh instance with *url*."""
    log(f"Opening Chrome → {url}")

    try:
        subprocess.run(["pkill", "-9", "-f", "chrome"], stderr=subprocess.DEVNULL)
        time.sleep(0.5)
    except Exception:
        pass

    _remove_chrome_locks()

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
        ], env=_display_env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        log(f"Chrome PID: {process.pid}")
        return process
    except Exception as e:
        log(f"ERROR starting Chrome: {e}")
        return None


def navigate_to(url):
    """Navigate the current Chrome tab to a new URL using the address bar.

    This avoids killing and restarting Chrome, which is much faster.
    Uses Ctrl+L → paste URL → Enter.
    """
    log(f"Navigating → {url}")
    env = _display_env()

    # Focus address bar
    try:
        subprocess.run(
            ["xdotool", "key", "--clearmodifiers", "ctrl+l"],
            env=env, timeout=2,
        )
    except Exception:
        pg.hotkey('ctrl', 'l')

    time.sleep(0.3)

    # Paste the URL
    if copy_text_to_clipboard(url):
        time.sleep(0.1)
        try:
            subprocess.run(
                ["xdotool", "key", "--clearmodifiers", "ctrl+v"],
                env=env, timeout=2,
            )
        except Exception:
            pg.hotkey('ctrl', 'v')
    else:
        type_text_via_xdotool(url)

    time.sleep(0.2)

    # Press Enter to navigate
    pg.press('enter')
    log("Navigation started")


def close_browser():
    """Kill Chrome entirely."""
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome"], stderr=subprocess.DEVNULL)
        log("Browser closed")
    except Exception:
        pass


# ── Screen detection ─────────────────────────────────────────────────

def wait_for_chat_load(timeout=40, assume_loaded_on_timeout=True):
    """Wait for the WhatsApp chat to appear.

    Returns:
        "loaded"  — chat is ready
        "invalid" — phone number not on WhatsApp
        "timeout" — timed out (returns "loaded" when *assume_loaded_on_timeout*)
    """
    start = time.time()

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            if pg.locateOnScreen(LOADED_CHECK_IMG, confidence=0.6):
                log(f"Chat loaded in {elapsed}s")
                return "loaded"
            if pg.locateOnScreen(INVALID_NUMBER_IMG, confidence=0.6):
                log(f"Invalid number detected in {elapsed}s")
                return "invalid"
        except Exception:
            pass
        time.sleep(0.5)

    # Timeout — save a debug screenshot
    try:
        debug = os.path.join(BASE_DIR, "debug_timeout.png")
        pg.screenshot(debug)
        log(f"Timeout screenshot → {debug}")
    except Exception:
        pass

    if assume_loaded_on_timeout:
        log("Timeout — assuming chat loaded")
        return "loaded"
    return "timeout"


def find_message_input():
    """Locate the message input field by image, with coordinate fallback."""
    try:
        loc = pg.locateOnScreen(MESSAGE_BOX_IMG, confidence=0.8)
        if loc:
            center = pg.center(loc)
            log(f"Input found at {center}")
            return center
    except Exception:
        pass

    # Fallback coordinates (bottom-center of a 1920×1080 screen)
    return (int(SCREEN_WIDTH * 0.60), int(SCREEN_HEIGHT * 0.92))


def take_screenshot(name="debug"):
    """Take a screenshot and return the file path."""
    path = os.path.join(BASE_DIR, f"{name}.png")
    try:
        pg.screenshot(path)
        return path
    except Exception as e:
        log(f"Screenshot failed: {e}")
        return None
