"""
Database — SQLite queue operations.
"""
import time
import sqlite3
from config import DB_PATH
from logger import log


def init_db():
    """Create the messages table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            message TEXT,
            status TEXT DEFAULT 'pending',
            fail_reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()


def add_to_queue(phone, message):
    """Insert a new message into the queue."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT INTO messages (phone, message) VALUES (?, ?)',
        (phone, message)
    )
    conn.commit()
    msg_id = c.lastrowid
    conn.close()
    return msg_id


def get_next_pending():
    """Fetch the oldest pending message. Retries up to 3 times on DB lock."""
    for attempt in range(3):
        try:
            conn = sqlite3.connect(DB_PATH, timeout=10)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute(
                "SELECT * FROM messages WHERE status='pending' "
                "ORDER BY created_at ASC LIMIT 1"
            )
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None
        except sqlite3.OperationalError as e:
            log(f"DB locked (attempt {attempt + 1}/3): {e}")
            time.sleep(1)
    return None


def count_pending():
    """Return the number of pending messages in the queue."""
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM messages WHERE status='pending'")
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def update_status(msg_id, status, fail_reason=None):
    """Update a message's status and optionally record a failure reason."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE messages SET status=?, fail_reason=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (status, fail_reason, msg_id)
    )
    conn.commit()
    conn.close()
