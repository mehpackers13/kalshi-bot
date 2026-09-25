"""
Simple timestamped logger that writes to bot.log and stdout.
"""
from zoneinfo import ZoneInfo
import datetime
import sys
from pathlib import Path

LOG_FILE = Path(__file__).parent / "bot.log"


def log(message: str, level: str = "INFO") -> None:
    et = datetime.datetime.now(ZoneInfo("America/New_York"))  # ET approx
    ts = et.strftime("%Y-%m-%d %H:%M:%S ET")
    line = f"[{ts}] [{level}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
