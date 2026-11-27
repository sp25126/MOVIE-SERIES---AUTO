"""
Unified 360° Virality Engine for All Category Videos.
Executes daily BEFORE any video production across all 4 publishing pillars:
1. Category 1: Cinema Group (12 dynamic genres, multi-horizon scoring)
2. Category 2: TV & Web Series Group (100% dynamic series discovery across K-Drama, HBO, Netflix)
3. Category 3: The Mentalist Flagship Pillar (Locked flagship episode progress & theme scouting)
4. Category 4: Song Trend Edits (TikTok / Instagram Reels / Shorts audio trends & 3 subcategories)

Saves consolidated intelligence to:
- state/daily_virality_digest.json
- state/virality_report.json
- state/dynamic_tv_virality_report.json
- state/dynamic_song_virality_report.json
- niche_catalog.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DAILY_DIGEST_PATH = STATE_DIR / "daily_virality_digest.json"
PATRICK_JANE_FILE = ROOT / "patrick_jane_series.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_all_category_virality_scan(force_fresh_yt: bool = True) -> Dict[str, Any]:
    """
    Executes a comprehensive virality audit across ALL categories:
    Cinema, TV Series, Flagship Pillar, and Song Trends.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logging.info("================================================================================")
    logging.info("🔥 [VIRALITY ENGINE] STARTING 360° PRE-SCAN ACROSS ALL CATEGORY VIDEOS 🔥")
    logging.info(f"   Timestamp (UTC): {now_iso}")
    logging.info("================================================================================")

    digest: Dict[str, Any] = {
        "scan_time_utc": now_iso,
        "categories": {
            "cinema": {},
            "tv_series": {},
            "mentalist_pillar": {},
            "song_trends": {},
        },
        "summary": {},
    }

    # -------------------------------------------------------------------------
    # 1. CATEGORY 1: CINEMA GROUP (12 Genres, Reddit, News RSS, YouTube)
    # -------------------------------------------------------------------------
    logging.info("\n[1/4] Scanning Cinema Group (12 Genres, Blockbuster Feeds & Multi-Horizon)...")
    try:
        from virality_radar import scan_virality
        skip_yt = not force_fresh_yt
        cinema_rep = scan_virality(skip_yt=skip_yt)
        winner = cinema_rep.get("winner", {})
        top_topics = cinema_rep.get("top_topics", [])

        digest["categories"]["cinema"] = {
            "status": "success",
            "lead_winner": winner.get("topic", "Cinema"),
            "lead_genre": winner.get("genre", "action_thriller"),
            "lead_score": winner.get("score", 0.0),
            "top_candidates": top_topics[:10],
            "top_yt_today": cinema_rep.get("top_yt_today", [])[:5],
            "top_yt_week": cinema_rep.get("top_yt_week", [])[:5],
            "top_yt_month": cinema_rep.get("top_yt_month", [])[:5],
            "genre_leaderboard": cinema_rep.get("genre_leaderboard", []),
        }
        logging.info(f"  ✓ Cinema #1 Dynamic Winner: '{winner.get('topic')}' (Score: {winner.get('score')})")
        for win_label, key in (("TODAY", "top_yt_today"), ("THIS WEEK", "top_yt_week"), ("THIS MONTH", "top_yt_month")):
            items = cinema_rep.get(key, [])[:3]
            if items:
                logging.info(f"    [{win_label}] " + " | ".join(f"{x['title'][:32]} ({x['views']:,})" for x in items))
    except Exception as e:
        logging.error(f"  ✗ Cinema scan error: {e}", exc_info=True)
        digest["categories"]["cinema"] = {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # 2. CATEGORY 2: TV & WEB SERIES GROUP (K-Drama, HBO, Netflix, Amazon)
    # -------------------------------------------------------------------------
    logging.info("\n[2/4] Scanning TV & Web Series Group (Global Viral Edit Probes)...")
    try:
        from tv_series_radar import scan_dynamic_tv_virality
        tv_rep = scan_dynamic_tv_virality()
        tv_winner = tv_rep.get("winner", {})
        ranked_shows = tv_rep.get("ranked_shows", [])

        digest["categories"]["tv_series"] = {
            "status": "success",
            "lead_winner": tv_winner.get("series_name", "Breaking Bad"),
            "lead_views": tv_winner.get("total_views", 0),
            "top_candidates": ranked_shows[:8],
        }
        logging.info(f"  ✓ TV/Web Series #1 Winner: '{tv_winner.get('series_name')}' ({tv_winner.get('total_views', 0):,} views)")
    except Exception as e:
        logging.error(f"  ✗ TV series scan error: {e}", exc_info=True)
        digest["categories"]["tv_series"] = {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # 3. CATEGORY 3: THE MENTALIST FLAGSHIP PILLAR (Locked Pillar Progress)
    # -------------------------------------------------------------------------
    logging.info("\n[3/4] Auditing The Mentalist Flagship Pillar Status...")
    try:
        if PATRICK_JANE_FILE.exists():
            pj_cfg = json.loads(PATRICK_JANE_FILE.read_text(encoding="utf-8"))
            done = int(pj_cfg.get("completed_episodes", 0))
            max_ep = int(pj_cfg.get("max_episodes", 40))
            themes = pj_cfg.get("query_themes", [])
            next_theme = themes[done % len(themes)] if themes else "Patrick Jane edit"
            digest["categories"]["mentalist_pillar"] = {
                "status": "success",
                "current_episode": done + 1,
                "max_episodes": max_ep,
                "next_theme": next_theme,
                "pillar_locked": True,
            }
            logging.info(f"  ✓ The Mentalist: Episode #{done + 1} of {max_ep} ready (Theme: '{next_theme}')")
        else:
            digest["categories"]["mentalist_pillar"] = {"status": "not_found"}
            logging.warning("  ! patrick_jane_series.json not found")
    except Exception as e:
        logging.error(f"  ✗ Mentalist pillar check error: {e}", exc_info=True)
        digest["categories"]["mentalist_pillar"] = {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # 4. CATEGORY 4: SONG TREND EDITS GROUP (TikTok, IG Reels, Shorts Audio)
    # -------------------------------------------------------------------------
    logging.info("\n[4/4] Scanning Song Trend Edits (TikTok, Instagram Reels & YouTube Audio)...")
    try:
        from song_trend_radar import scan_dynamic_song_virality
        song_rep = scan_dynamic_song_virality()
        song_winner = song_rep.get("winner", {})
        trending_songs = song_rep.get("trending_songs", [])

        digest["categories"]["song_trends"] = {
            "status": "success",
            "lead_winner": song_winner.get("song_name", "Starboy"),
            "lead_views": song_winner.get("total_views", 0),
            "top_candidates": trending_songs[:8],
        }
        logging.info(f"  ✓ Song Trends #1 Winner: '{song_winner.get('song_name')}' ({song_winner.get('total_views', 0):,} views)")
    except Exception as e:
        logging.error(f"  ✗ Song trend scan error: {e}", exc_info=True)
        digest["categories"]["song_trends"] = {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # 5. LLM CULTURAL ZEITGEIST BRAIN (Breaking Event Preemption)
    # -------------------------------------------------------------------------
    try:
        from llm_virality_brain import execute_virality_brain_scan, LLM_REPORT_PATH
        if LLM_REPORT_PATH.exists() and (time.time() - LLM_REPORT_PATH.stat().st_mtime) < 900:
            llm_rep = json.loads(LLM_REPORT_PATH.read_text(encoding="utf-8"))
        else:
            llm_rep = execute_virality_brain_scan()
        digest["llm_brain"] = llm_rep
        if llm_rep.get("breaking_event_detected"):
            bw = llm_rep.get("breaking_winner", {})
            logging.info(f"  🚨 [LLM Brain] BREAKING EVENT: '{bw.get('topic')}' (Hype: {bw.get('hype_score')})")
    except Exception as e:
        logging.warning(f"  ! LLM Virality Brain skipped: {e}")
        digest["llm_brain"] = {}

    # -------------------------------------------------------------------------
    # 6. CONSOLIDATED SUMMARY & PERSISTENCE
    # -------------------------------------------------------------------------
    digest["summary"] = {
        "cinema_leader": digest["categories"]["cinema"].get("lead_winner", "N/A"),
        "tv_series_leader": digest["categories"]["tv_series"].get("lead_winner", "N/A"),
        "mentalist_episode": digest["categories"]["mentalist_pillar"].get("current_episode", "N/A"),
        "song_trend_leader": digest["categories"]["song_trends"].get("lead_winner", "N/A"),
    }

    DAILY_DIGEST_PATH.write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"\n[Virality Engine] Consolidated daily digest saved to: {DAILY_DIGEST_PATH}")

    # Executive Output Dashboard
    logging.info("\n================================================================================")
    logging.info("🎯 DAILY VIRALITY INTELLIGENCE DASHBOARD (ALL 4 CATEGORIES) 🎯")
    logging.info("================================================================================")
    logging.info(f" • [Day 1 - Cinema Group]      Leader: '{digest['summary']['cinema_leader']}'")
    logging.info(f" • [Day 2 - TV Series Group]   Leader: '{digest['summary']['tv_series_leader']}'")
    logging.info(f" • [Day 3 - Mentalist Pillar]  Next Ep: #{digest['summary']['mentalist_episode']}")
    logging.info(f" • [Day 4 - Song Trend Edits]  Leader: '{digest['summary']['song_trend_leader']}'")
    logging.info("================================================================================\n")

    return digest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="360° Virality Engine Pre-Scan for All Category Videos")
    p.add_argument("--skip-yt", action="store_true", help="Skip YouTube live probes for offline/fast mode")
    args = p.parse_args()

    run_all_category_virality_scan(force_fresh_yt=not args.skip_yt)
