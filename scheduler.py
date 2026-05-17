"""Smart scheduler for posting at natural times throughout the day.

Posts 5 tweets per day at random times within these WIB (UTC+7) windows:
- Pagi (07:30 - 09:00)
- Siang (12:00 - 13:00)
- Sore (16:30 - 17:30)
- Malam (19:00 - 21:00)
- Larut Malam (22:30 - 23:30)
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# UTC+7 (WIB)
WIB = timezone(timedelta(hours=7))

# Posting windows as (start_hour, start_minute, end_hour, end_minute)
POSTING_WINDOWS = [
    (7, 30, 9, 0),    # Pagi
    (12, 0, 13, 0),   # Siang
    (16, 30, 17, 30),  # Sore
    (19, 0, 21, 0),   # Malam
    (22, 30, 23, 30),  # Larut Malam
]

SCHEDULE_FILE = "post_schedule.json"
MAX_POSTS_PER_DAY = 5


def _random_time_in_window(date: datetime, start_h: int, start_m: int, end_h: int, end_m: int) -> datetime:
    """Generate a random datetime within the given WIB window for the given date."""
    start = date.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end = date.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    delta_seconds = int((end - start).total_seconds())
    random_offset = random.randint(0, delta_seconds)
    return start + timedelta(seconds=random_offset)


def generate_daily_schedule(date: Optional[datetime] = None) -> List[datetime]:
    """Generate 5 random posting times for today (in WIB), one per window."""
    if date is None:
        date = datetime.now(WIB)
    else:
        date = date.astimezone(WIB)

    times = []
    for start_h, start_m, end_h, end_m in POSTING_WINDOWS:
        t = _random_time_in_window(date, start_h, start_m, end_h, end_m)
        times.append(t)

    return sorted(times)


def load_schedule() -> dict:
    """Load the current schedule from disk."""
    path = Path(SCHEDULE_FILE)
    if not path.exists():
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_schedule(data: dict) -> None:
    """Persist schedule to disk."""
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def get_todays_schedule() -> dict:
    """Get or create today's posting schedule.
    
    Returns dict with:
        - date: today's date string
        - slots: list of {time: ISO string, posted: bool}
        - posts_today: count of posts made today
    """
    today_str = datetime.now(WIB).strftime("%Y-%m-%d")
    data = load_schedule()

    # If schedule is for today and valid, return it
    if data.get("date") == today_str and "slots" in data:
        return data

    # Generate new schedule for today
    times = generate_daily_schedule()
    slots = [{"time": t.isoformat(), "posted": False} for t in times]
    data = {
        "date": today_str,
        "slots": slots,
        "posts_today": 0,
    }
    save_schedule(data)
    logger.info("Generated new daily schedule for %s: %s",
                today_str, [s["time"] for s in slots])
    return data


def get_next_post_slot() -> Optional[dict]:
    """Get the next unposted slot that's due (current time >= slot time).
    
    Returns the slot dict if it's time to post, None otherwise.
    """
    schedule_data = get_todays_schedule()
    now = datetime.now(WIB)

    for slot in schedule_data["slots"]:
        if slot["posted"]:
            continue
        slot_time = datetime.fromisoformat(slot["time"])
        if now >= slot_time:
            return slot

    return None


def mark_slot_posted(slot_time: str) -> None:
    """Mark a specific slot as posted."""
    data = load_schedule()
    for slot in data.get("slots", []):
        if slot["time"] == slot_time:
            slot["posted"] = True
            break
    data["posts_today"] = sum(1 for s in data.get("slots", []) if s["posted"])
    save_schedule(data)


def posts_remaining_today() -> int:
    """How many posts are left for today."""
    data = get_todays_schedule()
    return sum(1 for s in data["slots"] if not s["posted"])


def get_schedule_summary() -> dict:
    """Get a human-readable summary of today's schedule."""
    data = get_todays_schedule()
    now = datetime.now(WIB)
    return {
        "date": data["date"],
        "posts_today": data["posts_today"],
        "posts_remaining": posts_remaining_today(),
        "current_time_wib": now.strftime("%H:%M:%S"),
        "slots": [
            {
                "time": s["time"],
                "posted": s["posted"],
                "label": _slot_label(i),
            }
            for i, s in enumerate(data["slots"])
        ],
    }


def _slot_label(index: int) -> str:
    labels = ["Pagi", "Siang", "Sore", "Malam", "Larut Malam"]
    return labels[index] if index < len(labels) else f"Slot {index + 1}"
