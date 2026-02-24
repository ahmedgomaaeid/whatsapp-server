"""
WhatsApp — message-sending logic with send confirmation.
"""
import os
import time
import pyautogui as pg
import numpy as np

from config import BASE_DIR
from logger import log
from browser import (
    open_browser, navigate_to, wait_for_chat_load,
    find_message_input, paste_text, close_browser,
)


# ── Send confirmation ────────────────────────────────────────────────

def _capture_chat_region():
    """Capture the chat area as a numpy array for later comparison."""
    try:
        screenshot = pg.screenshot()
        w, h = screenshot.size
        box = (int(w * 0.40), int(h * 0.10), int(w * 0.95), int(h * 0.85))
        return np.array(screenshot.crop(box))
    except Exception as e:
        log(f"Failed to capture chat region: {e}")
        return None


def _wait_for_message_sent(before_snapshot, timeout=10):
    """Compare the chat area before/after sending to detect a visual change."""
    start = time.time()

    while time.time() - start < timeout:
        time.sleep(0.5)

        after = _capture_chat_region()
        if before_snapshot is None or after is None:
            return True
        if before_snapshot.shape != after.shape:
            return True

        diff = np.abs(before_snapshot.astype(int) - after.astype(int))
        change_pct = (diff > 30).mean() * 100

        if change_pct > 2.0:
            log(f"Sent confirmed ✓ ({change_pct:.1f}% change, {time.time()-start:.1f}s)")
            return True

    log(f"Send confirmation timeout after {timeout}s")
    try:
        pg.screenshot(os.path.join(BASE_DIR, "debug_send_timeout.png"))
    except Exception:
        pass
    return False


# ── Core send flow ───────────────────────────────────────────────────

def process_message(task, browser_is_open=False):
    """Send a WhatsApp text message.

    Args:
        task:             dict with 'id', 'phone', 'message'
        browser_is_open:  if True, reuse the existing Chrome window
                          instead of launching a new one

    Returns:
        (True, None)          on success
        (False, reason_str)   on failure
    """
    phone = task['phone']
    message = task['message']
    chat_url = f"https://web.whatsapp.com/send?phone={phone}"
    t0 = time.time()
    log(f"Processing ID:{task['id']} → {phone}")

    try:
        # 1. Open / navigate to chat
        if browser_is_open:
            navigate_to(chat_url)
        else:
            open_browser(chat_url)

        # 2. Wait for chat to load
        status = wait_for_chat_load()
        if status == "invalid":
            log(f"Invalid number: {phone}")
            return False, "invalid_number"
        if status == "timeout":
            log(f"Chat load timeout for {phone}")
            return False, "chat_load_timeout"

        time.sleep(1)

        # 3. Click the message input
        input_pos = find_message_input()
        pg.click(x=input_pos[0], y=input_pos[1])

        # 4. Paste text (newlines handled automatically)
        if message:
            paste_text(message)
            time.sleep(0.5)

        # 5. Snapshot before sending (for confirmation check)
        before_snapshot = _capture_chat_region()

        # 6. Send
        pg.press('enter')
        log(f"Pressed Enter (elapsed: {time.time()-t0:.1f}s)")

        # 7. Confirm delivery
        if not _wait_for_message_sent(before_snapshot):
            log("⚠️ Send not confirmed")
            return False, "send_unconfirmed"

        log(f"Task completed in {time.time()-t0:.2f}s")
        return True, None

    except Exception as e:
        log(f"Error processing message: {e}")
        return False, f"exception: {e}"
