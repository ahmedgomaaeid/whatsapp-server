"""
Telegram — send failure notifications via Telegram Bot API.
"""
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from logger import log


def _send(text):
    """Low-level: send a message to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("Telegram not configured — skipping notification")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            log("Telegram notification sent ✓")
            return True
        else:
            log(f"Telegram API error {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        log(f"Telegram request failed: {e}")
        return False


def notify_invalid_number(phone, task_id):
    """Alert: the phone number does not exist on WhatsApp."""
    text = (
        "⚠️ <b>Invalid Number</b>\n\n"
        f"📱 Phone: <code>{phone}</code>\n"
        f"🆔 Task ID: {task_id}\n"
        "❌ This number does not exist on WhatsApp."
    )
    return _send(text)


def notify_failed_message(phone, task_id, reason="Unknown error"):
    """Alert: the message failed to send."""
    text = (
        "🔴 <b>Message Failed</b>\n\n"
        f"📱 Phone: <code>{phone}</code>\n"
        f"🆔 Task ID: {task_id}\n"
        f"📝 Reason: {reason}"
    )
    return _send(text)


def notify_send_timeout(phone, task_id):
    """Alert: message might not have been sent (confirmation timed out)."""
    text = (
        "🟡 <b>Send Unconfirmed</b>\n\n"
        f"📱 Phone: <code>{phone}</code>\n"
        f"🆔 Task ID: {task_id}\n"
        "⏱️ Could not confirm message delivery (timeout).\n"
        "The message <i>may</i> have been sent — please verify manually."
    )
    return _send(text)
