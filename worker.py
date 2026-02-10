"""
Worker — background loop that processes queued messages.
"""
import time
import random

from logger import log
from database import get_next_pending, update_status
from whatsapp import process_message
from telegram import notify_invalid_number, notify_failed_message, notify_send_timeout


def worker_loop():
    """Continuously process pending messages from the queue."""
    log("Worker thread started")

    while True:
        try:
            task = get_next_pending()
            if not task:
                time.sleep(5)
                continue

            update_status(task['id'], 'processing')
            success, fail_reason = process_message(task)

            if success:
                update_status(task['id'], 'completed')
                log(f"Task {task['id']} COMPLETED ✓")

                # Random delay between messages to avoid bans
                sleep_time = random.randint(30, 60)
                log(f"Sleeping {sleep_time}s…")
                time.sleep(sleep_time)
            else:
                update_status(task['id'], 'failed', fail_reason)
                log(f"Task {task['id']} FAILED — {fail_reason}")

                # Send Telegram notification based on failure type
                phone = task['phone']
                tid = task['id']

                if fail_reason == "invalid_number":
                    notify_invalid_number(phone, tid)
                elif fail_reason == "send_unconfirmed":
                    notify_send_timeout(phone, tid)
                else:
                    notify_failed_message(phone, tid, reason=fail_reason or "Unknown")

                time.sleep(5)

        except Exception as e:
            log(f"Worker error: {e}")
            time.sleep(5)
