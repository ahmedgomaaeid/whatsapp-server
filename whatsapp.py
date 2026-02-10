"""
WhatsApp — message-sending logic with send confirmation.
"""
import os
import time
import pyautogui as pg
import pyperclip
import numpy as np
from PIL import Image as PILImage

from config import BASE_DIR
from logger import log
from browser import (
    open_browser, wait_for_chat_load,
    find_message_input, copy_image_to_clipboard,
)


# ---------------------------------------------------------------------------
# Send-confirmation
# ---------------------------------------------------------------------------

def _capture_chat_region():
    """
    Capture the chat area as a numpy array for comparison.
    The chat messages area is roughly the middle-right portion of the screen.
    """
    try:
        screenshot = pg.screenshot()
        # Crop to the chat area (right 50% of screen, middle 70% vertically)
        w, h = screenshot.size
        box = (int(w * 0.40), int(h * 0.10), int(w * 0.95), int(h * 0.85))
        chat_region = screenshot.crop(box)
        return np.array(chat_region)
    except Exception as e:
        log(f"Failed to capture chat region: {e}")
        return None


def wait_for_message_sent(before_snapshot, timeout=20):
    """
    Compare the chat area before and after sending to detect change.
    A significant pixel difference means a new message bubble appeared.
    Returns True if send is confirmed, False on timeout.
    """
    start = time.time()
    checks = 0

    while time.time() - start < timeout:
        checks += 1
        time.sleep(2)

        after_snapshot = _capture_chat_region()
        if before_snapshot is None or after_snapshot is None:
            log("Snapshot unavailable — assuming sent")
            return True

        # Handle possible shape mismatch
        if before_snapshot.shape != after_snapshot.shape:
            log("Screen shape changed — message likely sent")
            return True

        # Calculate pixel difference percentage
        diff = np.abs(before_snapshot.astype(int) - after_snapshot.astype(int))
        change_pct = (diff > 30).mean() * 100  # pixels that changed > threshold

        log(f"Send check #{checks}: {change_pct:.1f}% pixels changed")

        if change_pct > 2.0:  # More than 2% change means new content appeared
            log(f"Message sent confirmed ✓ ({change_pct:.1f}% change)")
            return True

    log(f"Send confirmation timeout after {timeout}s")

    # Save debug screenshot
    try:
        debug = os.path.join(BASE_DIR, "debug_send_timeout.png")
        pg.screenshot(debug)
        log(f"Debug screenshot → {debug}")
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Core send logic
# ---------------------------------------------------------------------------

def process_message(task):
    """
    Send a WhatsApp message (text, image, or both).
    Returns a tuple: (success: bool, fail_reason: str | None)
    """
    phone = task['phone']
    message = task['message']
    image_path = task['image_path']
    has_image = image_path and os.path.exists(image_path)

    log(f"Processing ID:{task['id']} → {phone}")

    try:
        # 1. Open WhatsApp chat
        link = f"https://web.whatsapp.com/send?phone={phone}"
        open_browser(link)

        # 2. Wait for chat to load
        status = wait_for_chat_load()
        if status == "invalid":
            log(f"Invalid number: {phone}")
            pg.hotkey('ctrl', 'w')
            return False, "invalid_number"
        if status == "timeout":
            log(f"Chat load timeout for {phone}")
            pg.hotkey('ctrl', 'w')
            return False, "chat_load_timeout"

        time.sleep(2)

        # 3. Click the message input field
        input_pos = find_message_input()
        pg.click(x=input_pos[0], y=input_pos[1])
        time.sleep(0.5)
        pg.click(x=input_pos[0], y=input_pos[1])
        time.sleep(0.3)

        # 4. Prepare content
        if has_image:
            if not copy_image_to_clipboard(image_path):
                pg.hotkey('ctrl', 'w')
                return False, "clipboard_copy_failed"

            # Paste image
            pg.hotkey('ctrl', 'v')
            time.sleep(3)  # Wait for image preview to appear

            # Add caption if provided
            if message:
                time.sleep(0.5)
                pyperclip.copy(message)
                time.sleep(0.5)
                pg.hotkey('ctrl', 'v')
                time.sleep(1)
        else:
            if message:
                pyperclip.copy(message)
                time.sleep(0.5)

                copied = pyperclip.paste()
                log(f"Clipboard: {copied[:50]}{'…' if len(copied) > 50 else ''}")

                pg.hotkey('ctrl', 'v')
                time.sleep(1)

        # 5. Capture chat BEFORE sending (for confirmation check)
        before_snapshot = _capture_chat_region()

        # 6. Send
        time.sleep(0.5)
        pg.press('enter')
        log("Pressed Enter to send")

        # 7. Wait for send confirmation
        send_timeout = 30 if has_image else 15
        confirmed = wait_for_message_sent(before_snapshot, timeout=send_timeout)

        if not confirmed:
            log("⚠️ Send not confirmed — message may not have been delivered")
            pg.hotkey('ctrl', 'w')
            return False, "send_unconfirmed"

        # 8. Close tab
        time.sleep(1)
        pg.hotkey('ctrl', 'w')
        return True, None

    except Exception as e:
        log(f"Error processing message: {e}")
        try:
            pg.hotkey('ctrl', 'w')
        except Exception:
            pass
        return False, f"exception: {e}"
