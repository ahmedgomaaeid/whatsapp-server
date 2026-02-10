"""
Logger — simple timestamped console logger.
"""
import time


def log(text):
    """Print a timestamped log line."""
    print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)
