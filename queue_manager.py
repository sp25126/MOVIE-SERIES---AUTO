"""
Production-Grade Publishing Queue & Scheduling Conflict Engine.
Manages multi-video daily batches (up to 8 videos/day).
Maintains a FIFO / Calendar release queue in state/upload_queue.json.
Calculates unique, non-overlapping future high-traffic slots:
- Slot 1: 10:00 AM IST (04:30 UTC) - Morning Commute
- Slot 2:  1:30 PM IST (08:00 UTC) - Lunch Surge
- Slot 3:  5:30 PM IST (12:00 UTC) - Evening Rush
- Slot 4:  8:00 PM IST (14:30 UTC) - Night Prime Climax
"""

from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
QUEUE_FILE = STATE_DIR / "upload_queue.json"

# 4 Strategic High-Traffic Shorts Publishing Slots (IST and UTC)
DAILY_PUBLISHING_SLOTS = [
    {"hour": 4,  "minute": 30, "label_ist": "10:00 AM IST"},  # Slot 1: Morning Commute
    {"hour": 8,  "minute": 0,  "label_ist": "1:30 PM IST"},   # Slot 2: Lunch Break Peak
    {"hour": 12, "minute": 0,  "label_ist": "5:30 PM IST"},   # Slot 3: Evening Prime Peak
    {"hour": 14, "minute": 30, "label_ist": "8:00 PM IST"},   # Slot 4: Night Climax
]


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


def get_next_available_slot_utc(min_lead_time_minutes: int = 45) -> Tuple[str, str]:
    """
    Finds the next unreserved high-traffic YouTube Shorts publishing slot.
    Rotates through the 4 peak daily slots (10:00 AM, 1:30 PM, 5:30 PM, 8:00 PM IST).
    Guarantees:
    1. NEVER double-books an identical slot.
    2. Only selects slots at least `min_lead_time_minutes` in the future.
    3. Smoothly advances across days to accommodate 4 to 8 videos daily.
    Returns: (slot_iso_utc, label_ist)
    """
    q_data = load_upload_queue()
    reserved_slots = set(q_data.get("scheduled_slots", []))

    now = datetime.datetime.now(datetime.timezone.utc)
    day_cursor = now.date()

    while True:
        for slot in DAILY_PUBLISHING_SLOTS:
            candidate_dt = datetime.datetime(
                day_cursor.year, day_cursor.month, day_cursor.day,
                slot["hour"], slot["minute"], 0, tzinfo=datetime.timezone.utc
            )
            # Must be in the future with minimum lead time
            if candidate_dt <= now + datetime.timedelta(minutes=min_lead_time_minutes):
                continue

            candidate_iso = candidate_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            if candidate_iso not in reserved_slots:
                # Found available slot!
                reserved_slots.add(candidate_iso)
                q_data["scheduled_slots"] = sorted(list(reserved_slots))
                # Clean up old past dates (older than 2 days)
                q_data["scheduled_slots"] = [
                    s for s in q_data["scheduled_slots"]
                    if datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc) >= now - datetime.timedelta(days=2)
                ]
                save_upload_queue(q_data)
                ist_label = f"{day_cursor.strftime('%b %d')} @ {slot['label_ist']}"
                return candidate_iso, ist_label

        day_cursor += datetime.timedelta(days=1)


def get_next_available_daily_slot_utc(reserve_buffer_hours: int = 4) -> str:
    """Backward compatibility wrapper returning just the slot ISO string."""
    slot_iso, _ = get_next_available_slot_utc(min_lead_time_minutes=reserve_buffer_hours * 60)
    return slot_iso


def register_video_in_queue(video_path: Path, meta: dict, day_type: str) -> dict:
    """
    Registers a rendered video in the upload calendar queue,
    assigning it a guaranteed distinct prime-time slot.
    """
    assigned_slot, ist_label = get_next_available_slot_utc()
    meta["publish_at_utc"] = assigned_slot
    meta["recommended_slot_utc"] = assigned_slot

    q_data = load_upload_queue()
    entry = {
        "video_path": str(video_path),
        "day_type": day_type,
        "title": meta.get("title", ""),
        "assigned_slot_utc": assigned_slot,
        "assigned_slot_ist": ist_label,
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "queued_for_schedule",
    }
    q_data["queue"].append(entry)
    save_upload_queue(q_data)

    logger.info(f"[Queue Manager] Video '{video_path.name}' assigned unique slot: {assigned_slot} ({ist_label})")
    return entry


if __name__ == "__main__":
    print("Testing 8 Consecutive Slot Allocations across Peak Viewing Windows:")
    for i in range(1, 9):
        iso_slot, ist_str = get_next_available_slot_utc(min_lead_time_minutes=30)
        print(f"  Video #{i:02d} -> Slot: {iso_slot} ({ist_str})")
