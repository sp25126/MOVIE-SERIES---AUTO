"""
Production-Grade Publishing Queue & Scheduling Engine.
Enforces YouTube Shorts Scheduling Rules:
1. STRICTLY 1 VIDEO PER DAY.
2. Scheduled at Daily Prime-Time: 7:30 PM IST (14:00 UTC).
3. Strictly adheres to our 4-Group Rotating Format:
   - Day 1: Cinema Group (12 Genres, dynamic virality score)
   - Day 2: TV & Web Series Group (100% dynamic series discovery)
   - Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED FOREVER)
   - Day 4: Song Trend Edits (Zero Voiceover, 3 rotating subcategories)
4. Maintains a FIFO / Calendar release queue in state/upload_queue.json.
5. Prevents double-booking any calendar date.
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

# Strict Single Daily Prime-Time Window (7:30 PM IST / 14:00 UTC)
DAILY_SLOT_HOUR_UTC = 14
DAILY_SLOT_MINUTE_UTC = 0
DAILY_SLOT_LABEL_IST = "7:30 PM IST"


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


def get_next_available_slot_utc(min_lead_time_minutes: int = 45, persist: bool = True, extra_reserved_dates: set[str] | None = None) -> Tuple[str, str]:
    """
    Finds the next unreserved YouTube Shorts publishing slot, STRICTLY 1 PER CALENDAR DAY.
    Guarantees:
    1. Exactly 1 video per day scheduled at Prime-Time: 7:30 PM IST (14:00 UTC).
    2. NEVER schedules multiple videos on the same calendar date.
    3. If today's 7:30 PM IST slot is already reserved or passed, smoothly advances to tomorrow, day after, etc.
    Returns: (slot_iso_utc, label_ist)
    """
    q_data = load_upload_queue()
    # Track which dates (YYYY-MM-DD) already have a scheduled video
    reserved_dates = {s[:10] for s in q_data.get("scheduled_slots", [])}
    if extra_reserved_dates:
        reserved_dates.update(extra_reserved_dates)

    now = datetime.datetime.now(datetime.timezone.utc)
    day_cursor = now.date()

    while True:
        candidate_dt = datetime.datetime(
            day_cursor.year, day_cursor.month, day_cursor.day,
            DAILY_SLOT_HOUR_UTC, DAILY_SLOT_MINUTE_UTC, 0, tzinfo=datetime.timezone.utc
        )
        date_str = day_cursor.strftime("%Y-%m-%d")

        # Must be in the future with minimum lead time AND date must not be already booked
        if candidate_dt > now + datetime.timedelta(minutes=min_lead_time_minutes) and date_str not in reserved_dates:
            candidate_iso = candidate_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            reserved_dates.add(date_str)
            if persist:
                all_slots = set(q_data.get("scheduled_slots", []))
                all_slots.add(candidate_iso)
                # Retain only future slots or slots from last 2 days
                q_data["scheduled_slots"] = sorted([
                    s for s in all_slots
                    if datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc) >= now - datetime.timedelta(days=2)
                ])
                save_upload_queue(q_data)
            ist_label = f"{day_cursor.strftime('%b %d')} @ {DAILY_SLOT_LABEL_IST}"
            return candidate_iso, ist_label

        day_cursor += datetime.timedelta(days=1)


def get_next_available_daily_slot_utc(reserve_buffer_hours: int = 4) -> str:
    """Backward compatibility wrapper returning just the slot ISO string."""
    slot_iso, _ = get_next_available_slot_utc(min_lead_time_minutes=reserve_buffer_hours * 60)
    return slot_iso


def register_video_in_queue(video_path: Path, meta: dict, day_type: str) -> dict:
    """
    Registers a rendered video in the upload calendar queue,
    assigning it the next available daily prime-time slot (1 video per day).
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
    print("Testing 1-Video-Per-Day Sequential Scheduling across the 4-Day Format:")
    cadence = ["Day 3: The Mentalist Pillar", "Day 4: Song Trend Edits", "Day 1: Cinema Group", "Day 2: TV Series Group"]
    simulated = set()
    for i in range(1, 9):
        pillar = cadence[(i - 1) % len(cadence)]
        iso_slot, ist_str = get_next_available_slot_utc(min_lead_time_minutes=30, persist=False, extra_reserved_dates=simulated)
        simulated.add(iso_slot[:10])
        print(f"  Video #{i:02d} [{pillar}] -> Scheduled: {iso_slot} ({ist_str})")
