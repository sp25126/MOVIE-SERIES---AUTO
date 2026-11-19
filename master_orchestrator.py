"""
Master Orchestrator for 4-Day Rotating Publishing Cadence:
- Day 1: Cinema Group (12 Genres, dynamic virality score)
- Day 2: TV & Web Series Group (100% dynamic series discovery)
- Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED FOREVER)
- Day 4: Song Trend Edits (Zero Voiceover, 3 rotating subcategories)
Advances the state wheel daily, handles weekly digest triggers, and manages uploads.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CADENCE_STATE_FILE = STATE_DIR / "pipeline_cadence_state.json"
DIGEST_FILE = STATE_DIR / "weekly_virality_digest.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CADENCE_NAMES = {
    1: "Cinema Group",
    2: "TV & Web Series Group",
    3: "The Mentalist Series (Locked Pillar)",
    4: "Song Trend Edits (Zero Voiceover)",
}

SONG_SUBCATEGORIES = [
    "one_song_multi_franchise",
    "one_song_single_franchise_multi_edits",
    "one_franchise_multi_song_edits",
]


def load_cadence_state() -> dict:
    if CADENCE_STATE_FILE.exists():
        try:
            return json.loads(CADENCE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "current_day_index": 1,
        "song_subcat_index": 0,
        "cycle_count": 1,
        "last_run_utc": None,
        "history": [],
    }


def save_cadence_state(state: dict):
    CADENCE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_day_1_cinema(dry_run: bool = True) -> dict:
    """Executes Day 1: Cinema Group."""
    logging.info("========== DAY 1: CINEMA GROUP ==========")
    cmd = [sys.executable, "run_pipeline.py", "--format", "auto"]
    if not dry_run:
        cmd.append("--upload")
    else:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=True)
    return {"status": "success", "day": 1, "returncode": proc.returncode}


def run_day_2_tv_series(dry_run: bool = True) -> dict:
    """Executes Day 2: Dynamic TV & Web Series Group."""
    logging.info("========== DAY 2: TV & WEB SERIES GROUP ==========")
    from tv_series_radar import scan_dynamic_tv_virality
    tv_rep = scan_dynamic_tv_virality()
    winner_show = tv_rep.get("winner", {}).get("series_name", "Breaking Bad")
    logging.info(f"[Day 2 TV] Selected trending series: '{winner_show}'")

    cmd = [
        sys.executable, "run_pipeline.py",
        "--genre", "drama_prestige",
        "--topic", winner_show,
        "--format", "edit_ranking",
    ]
    if not dry_run:
        cmd.append("--upload")
    else:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=True)
    return {"status": "success", "day": 2, "series": winner_show, "returncode": proc.returncode}


def run_day_3_mentalist_pillar(dry_run: bool = True) -> dict:
    """Executes Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED)."""
    logging.info("========== DAY 3: THE MENTALIST FLAGSHIP PILLAR (LOCKED) ==========")
    cmd = [
        sys.executable, "run_pipeline.py",
        "--series-file", "patrick_jane_series.json",
    ]
    if not dry_run:
        cmd.append("--upload")
    else:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=True)
    return {"status": "success", "day": 3, "pillar": "The Mentalist", "returncode": proc.returncode}


def run_day_4_song_edits(subcat: str, dry_run: bool = True) -> dict:
    """Executes Day 4: Song Trend Edits with specialized subcategory."""
    logging.info(f"========== DAY 4: SONG TREND EDITS [{subcat}] ==========")
    from song_trend_radar import scan_dynamic_song_virality, scout_song_subcategories
    from song_ranking_renderer import render_song_edit_ranking
    from clip_harvester import download_clip

    rep = scan_dynamic_song_virality()
    top_song = rep.get("winner", {}).get("song_name", "Starboy")

    sub_data = scout_song_subcategories(subcat, top_song)
    banner_title = sub_data.get("banner_title", f"RANKING THE BEST {top_song.upper()} EDITS")
    edits = sub_data.get("edits", [])

    downloaded = []
    for e in edits:
        p = download_clip(e)
        if p:
            e["local_path"] = str(p)
            downloaded.append(e)

    if len(downloaded) < 2:
        raise RuntimeError(f"Not enough clean clips harvested for song trend '{top_song}'")

    safe_name = re.sub(r"[^a-z0-9]+", "_", top_song.lower()).strip("_")
    out_mp4 = ROOT / "output" / f"song_ranking_{safe_name}_{subcat}_master.mp4"
    render_song_edit_ranking(banner_title, downloaded, out_mp4, clip_dur=8.0)

    from qa_gate import verify_video
    qa = verify_video(out_mp4, make_proof=True)
    logging.info(f"[Day 4 Song] Master complete: {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'}")

    return {
        "status": "success",
        "day": 4,
        "song": top_song,
        "subcategory": subcat,
        "video": str(out_mp4),
        "qa": qa,
    }


def execute_daily_cadence(day_override: int = 0, dry_run: bool = True, force_weekly_digest: bool = False):
    """Executes the scheduled daily step in the 4-day wheel and advances state."""
    state = load_cadence_state()

    # Check if weekly digest is needed (every 7 days or if Sunday or forced)
    is_sunday = datetime.datetime.now(datetime.timezone.utc).weekday() == 6
    if force_weekly_digest or is_sunday or not DIGEST_FILE.exists():
        logging.info("[Cadence] Triggering Weekly Multi-Platform Virality Synthesis...")
        try:
            from weekly_radar_digest import generate_weekly_virality_digest
            generate_weekly_virality_digest()
        except Exception as e:
            logging.error(f"[Cadence] Weekly digest failed: {e}")

    day = day_override if day_override in (1, 2, 3, 4) else state.get("current_day_index", 1)
    logging.info(f"[Cadence Engine] Starting Step #{day}: {CADENCE_NAMES[day]}")

    result = {}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if day == 1:
        result = run_day_1_cinema(dry_run=dry_run)
    elif day == 2:
        result = run_day_2_tv_series(dry_run=dry_run)
    elif day == 3:
        result = run_day_3_mentalist_pillar(dry_run=dry_run)
    elif day == 4:
        sub_idx = state.get("song_subcat_index", 0) % len(SONG_SUBCATEGORIES)
        current_subcat = SONG_SUBCATEGORIES[sub_idx]
        result = run_day_4_song_edits(subcat=current_subcat, dry_run=dry_run)
        state["song_subcat_index"] = (sub_idx + 1) % len(SONG_SUBCATEGORIES)

    # Advance state wheel
    next_day = (day % 4) + 1
    state["current_day_index"] = next_day
    state["last_run_utc"] = now_iso
    if day == 4:
        state["cycle_count"] = state.get("cycle_count", 1) + 1

    state["history"].append({
        "timestamp_utc": now_iso,
        "day": day,
        "name": CADENCE_NAMES[day],
        "result": result.get("status", "completed"),
    })
    # Keep history bounded
    state["history"] = state["history"][-20:]
    save_cadence_state(state)

    logging.info(f"[Cadence Engine] Day #{day} complete. Wheel advanced to Day #{next_day} ({CADENCE_NAMES[next_day]})")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Master 4-Day Rotating Autonomous Cadence Engine")
    p.add_argument("--day", type=int, default=0, choices=[0, 1, 2, 3, 4], help="0=auto-advance, 1-4=day override")
    p.add_argument("--upload", action="store_true", help="Upload and schedule canary release")
    p.add_argument("--dry-run", action="store_true", help="Dry run test without publishing (default)")
    p.add_argument("--weekly-digest", action="store_true", help="Force weekly multi-platform digest")
    args = p.parse_args()

    execute_daily_cadence(
        day_override=args.day,
        dry_run=not args.upload,
        force_weekly_digest=args.weekly_digest,
    )
