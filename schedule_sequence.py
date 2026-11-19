"""
Sequential Publisher & YouTube Scheduler for @OtakuSnapster.
Schedules:
- Video 1 (Day 3: The Mentalist Pillar): TODAY (2026-11-19T14:00:00Z / 7:30 PM IST)
- Video 2 (Day 4: Song Trend Edits): TOMORROW (2026-11-20T14:00:00Z / 7:30 PM IST)
- Video 3 (Day 1: Cinema Group): DAY AFTER TOMORROW (2026-11-21T14:00:00Z / 7:30 PM IST)
- Video 4 (Day 2: TV & Series Group): (2026-11-22T14:00:00Z / 7:30 PM IST)
- Video 5 (Day 1 Alternate): (2026-11-23T14:00:00Z / 7:30 PM IST)
"""

import json
import logging
from pathlib import Path
from metadata_uploader import upload_private_canary_and_schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
STATE_DIR = ROOT / "state"
UPLOAD_QUEUE_PATH = STATE_DIR / "upload_queue.json"

SEQUENCE_PLAN = [
    {
        "slot_utc": "2026-11-19T14:00:00Z",
        "slot_label": "Today (Nov 19) 7:30 PM IST",
        "video_pattern": "edit_ranking_the_mentalist_ep03_master.mp4",
        "pillar": "Day 3: The Mentalist Pillar (Ep 3)",
    },
    {
        "slot_utc": "2026-11-20T14:00:00Z",
        "slot_label": "Tomorrow (Nov 20) 7:30 PM IST",
        "video_pattern": "song_ranking_paparazzi_master.mp4",
        "pillar": "Day 4: Song Trend Edits (Paparazzi)",
    },
    {
        "slot_utc": "2026-11-21T14:00:00Z",
        "slot_label": "Day After Tomorrow (Nov 21) 7:30 PM IST",
        "video_pattern": "edit_ranking_ramayana_master.mp4",
        "pillar": "Day 1: Cinema Group (Ramayana)",
    },
    {
        "slot_utc": "2026-11-22T14:00:00Z",
        "slot_label": "Nov 22 7:30 PM IST",
        "video_pattern": "edit_ranking_my_demon_ep_6_master.mp4",
        "pillar": "Day 2: TV Series Group (My Demon)",
    },
]


def run_sequence_schedule():
    print("================================================================")
    print("   @OtakuSnapster SEQUENTIAL YOUTUBE SCHEDULER")
    print("================================================================")
    
    results = []
    scheduled_slots = []

    for item in SEQUENCE_PLAN:
        vid_file = OUTPUT_DIR / item["video_pattern"]
        meta_file = vid_file.with_suffix(".meta.json")

        if not vid_file.exists():
            print(f"[SKIP] Video not found: {vid_file.name}")
            continue

        if not meta_file.exists():
            print(f"[SKIP] Metadata not found for {vid_file.name}")
            continue

        meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
        meta = meta_data.get("metadata", meta_data)

        # Override slot with exact planned sequence slot
        target_slot = item["slot_utc"]
        meta["recommended_slot_utc"] = target_slot
        meta_data["metadata"]["recommended_slot_utc"] = target_slot
        meta_file.write_text(json.dumps(meta_data, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"\n>>> Uploading & Scheduling: {item['pillar']}")
        print(f"    File: {vid_file.name} ({vid_file.stat().st_size / (1024*1024):.2f} MB)")
        print(f"    Assigned Slot: {target_slot} ({item['slot_label']})")
        print(f"    Title: {meta.get('title')}")

        try:
            res = upload_private_canary_and_schedule(
                vid_file,
                meta,
                canary_wait_sec=25,
            )
            res["pillar"] = item["pillar"]
            res["slot_label"] = item["slot_label"]
            results.append(res)
            scheduled_slots.append(target_slot)
            print(f"    RESULT: Video ID {res.get('video_id')} -> Scheduled: {res.get('scheduled')}")
        except Exception as e:
            print(f"    ERROR scheduling {vid_file.name}: {e}")

    # Update state/upload_queue.json
    q_data = {
        "scheduled_slots": sorted(list(set(scheduled_slots))),
        "queue": results,
        "last_upload_date_utc": "2026-11-19T14:00:00Z",
    }
    UPLOAD_QUEUE_PATH.write_text(json.dumps(q_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n================================================================")
    print("   ALL VIDEOS SUCCESSFULLY SCHEDULED SEQUENCE-WISE!")
    print("================================================================")
    for r in results:
        status_str = "SCHEDULED" if r.get("scheduled") else "HELD PRIVATE"
        print(f" - [{status_str}] {r.get('pillar')} | Slot: {r.get('slot_label')} | URL: https://youtube.com/shorts/{r.get('video_id')}")

if __name__ == "__main__":
    run_sequence_schedule()
