"""
Production-Grade Publishing Queue & Scheduling Conflict Engine.
Enforces the 1 Video/Day Rule regardless of how many times triggers run.
Maintains a FIFO / Calendar release queue in state/upload_queue.json.
Calculates unique, non-overlapping future prime-time slots (14:00 UTC / 7:30 PM IST).
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = STATE_DIR / "upload_queue.json"


def load_upload_queue() -> dict:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "scheduled_slots": [],  # List of ISO timestamp strings already reserved
        "queue": [],            # List of queued video entries
        "last_upload_date_utc": None,
    }


def save_upload_queue(queue_data: dict):
    QUEUE_FILE.write_text(json.dumps(queue_data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_next_available_daily_slot_utc(reserve_buffer_hours: int = 4) -> str:
    """
    Finds the next strictly available 14:00 UTC (7:30 PM IST) slot.
    Guarantees:
    1. NEVER schedules two videos on the same calendar day.
    2. If today's slot is within reserve_buffer_hours or already reserved, pushes to Tomorrow 14:00 UTC.
    3. If Tomorrow is reserved, pushes to Day After Tomorrow, etc.
    """
    q_data = load_upload_queue()
    reserved_slots = set(q_data.get("scheduled_slots", []))

    now = datetime.datetime.now(datetime.timezone.utc)
    # Target 14:00 UTC (7:30 PM IST)
    candidate = now.replace(hour=14, minute=0, second=0, microsecond=0)

    # If already past cutoff or within buffer window, start checking from tomorrow
    if now + datetime.timedelta(hours=reserve_buffer_hours) >= candidate:
        candidate += datetime.timedelta(days=1)

    # Advance day-by-day until an unreserved slot is found
    while True:
        candidate_iso = candidate.strftime("%Y-%m-%dT%H:%M:%SZ")
        date_str = candidate.strftime("%Y-%m-%d")

        # Check if any reserved slot already occupies this calendar date
        date_occupied = any(s.startswith(date_str) for s in reserved_slots)
        if candidate_iso not in reserved_slots and not date_occupied:
            # Found unique available day slot
            reserved_slots.add(candidate_iso)
            q_data["scheduled_slots"] = sorted(list(reserved_slots))
            # Clean up old past dates from reserved_slots
            q_data["scheduled_slots"] = [
                s for s in q_data["scheduled_slots"]
                if datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc) >= now - datetime.timedelta(days=2)
            ]
            save_upload_queue(q_data)
            return candidate_iso

        candidate += datetime.timedelta(days=1)


def register_video_in_queue(video_path: Path, meta: dict, day_type: str) -> dict:
    """
    Registers a rendered video in the upload calendar queue,
    assigning it a guaranteed distinct prime-time slot.
    """
    assigned_slot = get_next_available_daily_slot_utc()
    meta["publish_at_utc"] = assigned_slot

    q_data = load_upload_queue()
    entry = {
        "video_path": str(video_path),
        "day_type": day_type,
        "title": meta.get("title", ""),
        "assigned_slot_utc": assigned_slot,
        "assigned_slot_ist": f"{assigned_slot[:10]} 19:30 IST",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "queued_for_schedule",
    }
    q_data["queue"].append(entry)
    save_upload_queue(q_data)

    logger.info(f"[Queue Manager] Video '{video_path.name}' assigned unique slot: {assigned_slot} (7:30 PM IST)")
    return entry


if __name__ == "__main__":
    slot1 = get_next_available_daily_slot_utc()
    slot2 = get_next_available_daily_slot_utc()
    slot3 = get_next_available_daily_slot_utc()
    print("Testing Conflict Prevention - 3 Consecutive Calls Generated:")
    print("  Slot 1:", slot1)
    print("  Slot 2:", slot2)
    print("  Slot 3:", slot3)
