"""
Master Orchestrator for High-Velocity 4-Day Rotating Publishing Cadence:
- Day 1: Cinema Group (12 Genres, dynamic virality score)
- Day 2: TV & Web Series Group (100% dynamic series discovery)
- Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED FOREVER)
- Day 4: Song Trend Edits (Zero Voiceover, 3 rotating subcategories)

Supports Twice-Daily Execution producing ~8 videos daily across 4 peak Shorts windows:
- Slot 1: 10:00 AM IST (04:30 UTC) - Morning Commute
- Slot 2:  1:30 PM IST (08:00 UTC) - Lunch Break Peak
- Slot 3:  5:30 PM IST (12:00 UTC) - Evening Prime Rush
- Slot 4:  8:00 PM IST (14:30 UTC) - Night Climax

VIRALITY-FIRST PRE-CHECK:
Scans live multi-platform virality radar BEFORE creating any videos.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CADENCE_STATE_FILE = STATE_DIR / "pipeline_cadence_state.json"
DIGEST_FILE = STATE_DIR / "weekly_virality_digest.json"
PATRICK_JANE_FILE = ROOT / "patrick_jane_series.json"

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


def cleanup_temp_files():
    """Removes leftover scratch clips from input/ and temp/ segments to prevent disk bloat."""
    for folder in (ROOT / "input", ROOT / "temp"):
        if folder.exists():
            for f in folder.glob("*"):
                if f.is_file():
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass


def audit_live_virality() -> dict:
    """
    VIRALITY-FIRST ENGINE:
    Scans live Google Trends, YouTube autocomplete, Reddit, and RSS across all genres
    BEFORE producing any videos. Returns top candidates and logs an executive dashboard.
    """
    logging.info("================================================================================")
    logging.info("🔥 VIRALITY ENGINE: PRE-PRODUCTION LIVE MULTI-PLATFORM INTELLIGENCE AUDIT 🔥")
    logging.info("================================================================================")

    audit_results = {
        "cinema": [],
        "tv_series": None,
        "song_trends": None,
        "mentalist_pillar": None,
    }

    # 1. Cinema Scan
    try:
        from virality_radar import scan_virality, REPORT_PATH
        skip_yt = False
        if REPORT_PATH.exists() and (time.time() - REPORT_PATH.stat().st_mtime) < 3 * 3600:
            skip_yt = True
        cinema_rep = scan_virality(skip_yt=skip_yt)
        top_topics = cinema_rep.get("top_topics") or [cinema_rep.get("winner", {})]
        cat_file = ROOT / "niche_catalog.json"
        cat = json.loads(cat_file.read_text(encoding="utf-8")) if cat_file.exists() else {}
        recent = {t.lower() for t in cat.get("recent_topics", [])}
        fresh_topics = [t for t in top_topics if t.get("topic", "").lower() not in recent and not any(r in t.get("topic", "").lower() for r in recent if len(r) > 4)]
        audit_results["cinema"] = (fresh_topics or top_topics)[:6]
        logging.info("[Virality Audit] Top Live Cinema Candidates:")
        for idx, t in enumerate(audit_results["cinema"], 1):
            logging.info(f"   #{idx}: '{t.get('topic')}' | Genre: {t.get('genre')} | Score: {t.get('score', 0):.1f}")
    except Exception as e:
        logging.warning(f"[Virality Audit] Cinema scan error: {e}")

    # 2. TV & Web Series Scan
    try:
        from tv_series_radar import scan_dynamic_tv_virality
        tv_rep = scan_dynamic_tv_virality()
        audit_results["tv_series"] = tv_rep.get("ranked_shows") or [tv_rep.get("winner", {})]
        top_tv = audit_results["tv_series"][0].get("series_name", "Breaking Bad") if audit_results["tv_series"] else "Breaking Bad"
        score_tv = audit_results["tv_series"][0].get("total_views", 0) if audit_results["tv_series"] else 0
        logging.info(f"[Virality Audit] Top TV/Web Series: '{top_tv}' ({score_tv:,} views)")
    except Exception as e:
        logging.warning(f"[Virality Audit] TV scan error: {e}")

    # 3. Song Trend Scan
    try:
        from song_trend_radar import scan_dynamic_song_virality
        song_rep = scan_dynamic_song_virality()
        audit_results["song_trends"] = song_rep.get("trending_songs") or [song_rep.get("winner", {})]
        top_song = audit_results["song_trends"][0].get("song_name", "Starboy") if audit_results["song_trends"] else "Starboy"
        vel_song = audit_results["song_trends"][0].get("total_views", 0) if audit_results["song_trends"] else 0
        logging.info(f"[Virality Audit] Top Trending Audio: '{top_song}' ({vel_song:,} views)")
    except Exception as e:
        logging.warning(f"[Virality Audit] Song scan error: {e}")

    # 4. Mentalist Flagship Pillar Status
    if PATRICK_JANE_FILE.exists():
        try:
            pj_cfg = json.loads(PATRICK_JANE_FILE.read_text(encoding="utf-8"))
            done = int(pj_cfg.get("completed_episodes", 0))
            max_ep = int(pj_cfg.get("max_episodes", 40))
            themes = pj_cfg.get("query_themes", [])
            next_theme = themes[done % len(themes)] if themes else "Patrick Jane edit"
            audit_results["mentalist_pillar"] = {
                "episode": done + 1,
                "max_episodes": max_ep,
                "next_theme": next_theme,
            }
            logging.info(f"[Virality Audit] The Mentalist Flagship: Ep #{done + 1} of {max_ep} ready (Theme: '{next_theme}')")
        except Exception as e:
            logging.warning(f"[Virality Audit] Mentalist pillar check error: {e}")

    logging.info("================================================================================\n")
    return audit_results


def run_day_1_cinema(topic: str | None = None, genre: str | None = None, dry_run: bool = True) -> dict:
    """Executes Day 1: Cinema Group."""
    logging.info(f"========== DAY 1: CINEMA GROUP [{topic or 'Auto-Viral'}] ==========")
    cmd = [sys.executable, "run_pipeline.py", "--format", "edit_ranking"]
    if topic:
        cmd.extend(["--topic", topic])
    if genre:
        cmd.extend(["--genre", genre])
    if not dry_run:
        cmd.append("--upload")
    else:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, check=True)
    return {"status": "success", "day": 1, "topic": topic, "returncode": proc.returncode}


def run_day_2_tv_series(series_name: str | None = None, dry_run: bool = True) -> dict:
    """Executes Day 2: Dynamic TV & Web Series Group with multi-candidate fallback cascade."""
    logging.info(f"========== DAY 2: TV & WEB SERIES GROUP [{series_name or 'Auto-Viral'}] ==========")
    from tv_series_radar import scan_dynamic_tv_virality
    tv_rep = scan_dynamic_tv_virality()
    tv_cands = []
    if series_name:
        tv_cands.append(series_name)
    for s in tv_rep.get("ranked_shows", []):
        name = s.get("series_name")
        if name and name not in tv_cands:
            tv_cands.append(name)
    fallback_pool = ["Breaking Bad", "Suits", "Yellowstone", "Squid Game", "Shameless", "Snowfall", "Stranger Things", "Peaky Blinders"]
    for s in fallback_pool:
        if s not in tv_cands:
            tv_cands.append(s)

    last_err = None
    for cand_show in tv_cands[:8]:
        logging.info(f"[Day 2 TV] Attempting series candidate: '{cand_show}'")
        cmd = [
            sys.executable, "run_pipeline.py",
            "--topic", cand_show,
            "--format", "edit_ranking",
        ]
        if not dry_run:
            cmd.append("--upload")
        else:
            cmd.append("--dry-run")
        try:
            proc = subprocess.run(cmd, check=True)
            return {"status": "success", "day": 2, "series": cand_show, "returncode": proc.returncode}
        except subprocess.CalledProcessError as e:
            logging.warning(f"[Day 2 TV] Candidate '{cand_show}' failed ({e}), trying next TV show...")
            last_err = e

    raise RuntimeError(f"All TV series candidates failed: {last_err}")


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


def run_day_4_song_edits(subcat: str, top_song: str | None = None, dry_run: bool = True) -> dict:
    """Executes Day 4: Song Trend Edits with specialized subcategory."""
    logging.info(f"========== DAY 4: SONG TREND EDITS [{subcat}] ==========")
    from song_trend_radar import scan_dynamic_song_virality, scout_song_subcategories
    from song_ranking_renderer import render_song_edit_ranking
    from clip_harvester import download_clip

    rep = scan_dynamic_song_virality()
    trending_list = rep.get("trending_songs", [])
    candidate_songs = []
    if top_song:
        candidate_songs.append(top_song)
    winner_name = rep.get("winner", {}).get("song_name")
    if winner_name and winner_name not in candidate_songs:
        candidate_songs.append(winner_name)
    for s in trending_list:
        if s not in candidate_songs:
            candidate_songs.append(s)
    fallback_pool = ["Starboy", "Paparazzi", "Memory Reboot", "Timeless", "Montagem", "Softcore", "Love Me"]
    for s in fallback_pool:
        if s not in candidate_songs:
            candidate_songs.append(s)

    chosen_song = None
    downloaded = []
    chosen_banner = ""
    for cand_song in candidate_songs:
        sub_data = scout_song_subcategories(subcat, cand_song)
        banner_title = sub_data.get("banner_title", f"RANKING THE BEST {cand_song.upper()} EDITS")
        edits = sub_data.get("edits", [])
        cand_downloaded = []
        for e in edits:
            p = download_clip(e)
            if p:
                e["local_path"] = str(p)
                cand_downloaded.append(e)
                if len(cand_downloaded) >= 3:
                    break
        if len(cand_downloaded) >= 2:
            chosen_song = cand_song
            downloaded = cand_downloaded
            chosen_banner = banner_title
            break
        logging.warning(f"[Day 4 Song] Insufficient clips ({len(cand_downloaded)}) for '{cand_song}', trying next candidate...")

    if not chosen_song or len(downloaded) < 2:
        raise RuntimeError(f"Not enough clean clips harvested across candidate songs for subcategory '{subcat}'")

    safe_name = re.sub(r"[^a-z0-9]+", "_", chosen_song.lower()).strip("_")
    out_mp4 = ROOT / "output" / f"song_ranking_{safe_name}_{subcat}_master.mp4"
    render_song_edit_ranking(chosen_banner, downloaded, out_mp4, clip_dur=8.0)

    from qa_gate import verify_video
    qa = verify_video(out_mp4, make_proof=True)
    logging.info(f"[Day 4 Song] Master complete: {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'}")

    upload_res = None
    if not dry_run:
        if not qa["passed"]:
            raise RuntimeError(f"QA Gate failed ({qa['issues']}); upload aborted.")
        from metadata_uploader import build_metadata, upload_private_canary_and_schedule
        meta = build_metadata(chosen_song, "edit_ranking", downloaded, handle="@OtakuSnapster")
        meta["title"] = f"Ranking Best {chosen_song} Edits! 🔥💀 #shorts #naofloppa #shortsfeed"[:100]
        out_mp4.with_suffix(".meta.json").write_text(
            json.dumps({"song": chosen_song, "qa": qa, "metadata": meta}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        upload_res = upload_private_canary_and_schedule(out_mp4, meta)

    return {
        "status": "success",
        "day": 4,
        "song": chosen_song,
        "subcategory": subcat,
        "video": str(out_mp4),
        "qa": qa,
        "upload": upload_res,
    }


def execute_batch_cadence(
    batch_count: int = 4,
    day_override: int = 0,
    dry_run: bool = True,
    force_weekly_digest: bool = False,
) -> list[dict]:
    """
    Executes a high-velocity batch of Shorts (default 4 videos per run = 8 daily across 2 runs).
    First performs a Virality Audit, maps videos to live trending candidates,
    schedules them across peak Shorts windows, and automatically cleans up local MP4s.
    """
    # 1. Weekly digest check
    is_sunday = datetime.datetime.now(datetime.timezone.utc).weekday() == 6
    digest_age = (time.time() - DIGEST_FILE.stat().st_mtime) if DIGEST_FILE.exists() else 999999
    if force_weekly_digest or not DIGEST_FILE.exists() or (is_sunday and digest_age > 12 * 3600):
        logging.info("[Cadence] Triggering Weekly Multi-Platform Virality Synthesis...")
        try:
            from weekly_radar_digest import generate_weekly_virality_digest
            generate_weekly_virality_digest()
        except Exception as e:
            logging.error(f"[Cadence] Weekly digest failed: {e}")

    # 2. PRE-PRODUCTION VIRALITY AUDIT FIRST
    audit = audit_live_virality()

    state = load_cadence_state()
    start_day = day_override if day_override in (1, 2, 3, 4) else state.get("current_day_index", 1)

    batch_results = []
    logging.info(f"🚀 INITIATING PRODUCTION BATCH ({batch_count} Videos) Starting at Pillar #{start_day}")

    for step_num in range(batch_count):
        curr_day = ((start_day - 1 + step_num) % 4) + 1
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logging.info(f"\n---> [Batch Step {step_num + 1}/{batch_count}] Producing Pillar #{curr_day}: {CADENCE_NAMES[curr_day]}")

        result = {}
        try:
            if curr_day == 1:
                # Top live cinema candidate
                cinema_cand = audit["cinema"][step_num % len(audit["cinema"])] if audit.get("cinema") else {}
                topic = cinema_cand.get("topic")
                genre = cinema_cand.get("genre")
                result = run_day_1_cinema(topic=topic, genre=genre, dry_run=dry_run)
            elif curr_day == 2:
                # Top live TV candidate
                tv_list = audit.get("tv_series") or []
                tv_cand = tv_list[step_num % len(tv_list)].get("series_name") if tv_list else None
                result = run_day_2_tv_series(series_name=tv_cand, dry_run=dry_run)
            elif curr_day == 3:
                # Strictly locked flagship pillar (The Mentalist)
                result = run_day_3_mentalist_pillar(dry_run=dry_run)
            elif curr_day == 4:
                # Top live song candidate
                sub_idx = state.get("song_subcat_index", 0) % len(SONG_SUBCATEGORIES)
                current_subcat = SONG_SUBCATEGORIES[sub_idx]
                song_list = audit.get("song_trends") or []
                song_cand = song_list[step_num % len(song_list)].get("song_name") if song_list else None
                result = run_day_4_song_edits(subcat=current_subcat, top_song=song_cand, dry_run=dry_run)
                state["song_subcat_index"] = (sub_idx + 1) % len(SONG_SUBCATEGORIES)

            batch_results.append(result)
        except Exception as e:
            logging.error(f"[Batch Step {step_num + 1}] Failed with error: {e}", exc_info=True)
            batch_results.append({"status": "failed", "day": curr_day, "error": str(e)})

        # Only advance state wheel on SUCCESSFUL video production
        if result.get("status") == "success":
            state["current_day_index"] = (curr_day % 4) + 1
            state["last_run_utc"] = now_iso
            if curr_day == 4:
                state["cycle_count"] = state.get("cycle_count", 1) + 1

            state["history"].append({
                "timestamp_utc": now_iso,
                "day": curr_day,
                "name": CADENCE_NAMES[curr_day],
                "result": "success",
            })
        else:
            state["last_run_utc"] = now_iso
            state["history"].append({
                "timestamp_utc": now_iso,
                "day": curr_day,
                "name": CADENCE_NAMES[curr_day],
                "result": "failed",
                "error": str(batch_results[-1].get("error", "Production step failed")),
            })

        state["history"] = state["history"][-30:]
        save_cadence_state(state)

        # Cleanup temp scratch files after each step to prevent disk pressure
        cleanup_temp_files()

    failed_runs = [r for r in batch_results if r.get("status") == "failed"]
    if failed_runs:
        logging.error(f"⚠️ BATCH FINISHED WITH {len(failed_runs)} FAILURE(S): {failed_runs}")
        raise RuntimeError(f"{len(failed_runs)} production step(s) failed in batch: {failed_runs}")

    logging.info(f"\n🎉 BATCH COMPLETE: Successfully processed {len(batch_results)}/{batch_count} videos.")
    return batch_results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Master Autonomous Virality-First Shorts Cadence Engine")
    p.add_argument("--batch-count", type=int, default=1, help="Number of videos to produce in this run (each scheduled 1 per day in 4-group rotating format)")
    p.add_argument("--day", type=int, default=0, choices=[0, 1, 2, 3, 4], help="0=auto-advance 4-day wheel, 1-4=day override")
    p.add_argument("--upload", action="store_true", help="Upload and schedule canary release")
    p.add_argument("--dry-run", action="store_true", help="Dry run test without publishing (default)")
    p.add_argument("--weekly-digest", action="store_true", help="Force weekly multi-platform digest")
    args = p.parse_args()

    execute_batch_cadence(
        batch_count=args.batch_count,
        day_override=args.day,
        dry_run=not args.upload,
        force_weekly_digest=args.weekly_digest,
    )
