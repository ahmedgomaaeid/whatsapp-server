"""
Worker — background loop that processes queued messages.

Browser lifecycle:
    - Chrome is launched for the first message and kept alive while the
      queue has more pending items.
    - When the queue is empty after a message, Chrome is closed and the
      worker sleeps longer before polling again.
    - A short random delay between consecutive messages avoids bans.
"""
import time
import random

from logger import log
from database import get_next_pending, update_status, count_pending
from whatsapp import process_message
from browser import close_browser
from telegram import notify_invalid_number, notify_failed_message, notify_send_timeout

# Delay between consecutive messages (seconds)
BATCH_DELAY_MIN = 8
BATCH_DELAY_MAX = 15

# Delay after the queue is drained (seconds)
IDLE_DELAY_MIN = 30
IDLE_DELAY_MAX = 60

# How often to poll for new messages when idle (seconds)
POLL_INTERVAL = 5


def worker_loop():
    """Continuously process pending messages from the queue."""
    log("Worker thread started")
    browser_is_open = False

    while True:
        try:
            task = get_next_pending()

            # ── Nothing to do — sleep and poll again ──
            if not task:
                if browser_is_open:
                    close_browser()
                    browser_is_open = False
                    log("Queue empty — browser closed")
                time.sleep(POLL_INTERVAL)
                continue

            # ── Process the message ──
            update_status(task['id'], 'processing')
            success, fail_reason = process_message(task, browser_is_open=browser_is_open)

            if success:
                update_status(task['id'], 'completed')
                browser_is_open = True
                log(f"Task {task['id']} COMPLETED ✓")

                # Check if more messages are waiting
                remaining = count_pending()
                if remaining > 0:
                    # Short delay between messages
                    delay = random.randint(BATCH_DELAY_MIN, BATCH_DELAY_MAX)
                    log(f"{remaining} more pending — sleeping {delay}s")
                    time.sleep(delay)
                else:
                    # Queue drained — close browser and rest longer
                    close_browser()
                    browser_is_open = False
                    delay = random.randint(IDLE_DELAY_MIN, IDLE_DELAY_MAX)
                    log(f"Queue empty — browser closed, sleeping {delay}s")
                    time.sleep(delay)
            else:
                update_status(task['id'], 'failed', fail_reason)
                log(f"Task {task['id']} FAILED — {fail_reason}")

                # On failure, close browser to start fresh next time
                close_browser()
                browser_is_open = False

                # Telegram notification
                phone = task['phone']
                tid = task['id']
                if fail_reason == "invalid_number":
                    notify_invalid_number(phone, tid)
                elif fail_reason == "send_unconfirmed":
                    notify_send_timeout(phone, tid)
                else:
                    notify_failed_message(phone, tid, reason=fail_reason or "Unknown")

                time.sleep(POLL_INTERVAL)

        except Exception as e:
            log(f"Worker error: {e}")
            # Reset browser state on unexpected errors
            try:
                close_browser()
            except Exception:
                pass
            browser_is_open = False
            time.sleep(POLL_INTERVAL)
