"""
Weekly Multi-Platform Virality Synthesis Digest.
Executes every 7 days (or on demand) to analyze cross-platform velocity across:
1. Cinema (Top 5 Movies / Franchises)
2. Television & Web Series (Top 5 Shows)
3. Viral Audio & Songs (Top 5 TikTok/IG Soundtracks)
Saves results to state/weekly_virality_digest.json.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
DIGEST_FILE = STATE_DIR / "weekly_virality_digest.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def generate_weekly_virality_digest() -> dict:
    """Aggregates 7-day multi-platform intelligence across Cinema, TV Shows, and TikTok/IG Audio."""
    logging.info("[Weekly Radar] Initiating 7-day multi-platform virality synthesis...")

    # 1. Cinema 7-Day Radar
    from virality_radar import scan_virality
    cinema_rep = scan_virality(skip_yt=False)
    top_cinema = []
    for t in cinema_rep.get("top_topics", [])[:5]:
        top_cinema.append({
            "topic": t.get("topic"),
            "genre": t.get("genre"),
            "score": t.get("score"),
            "views": t.get("yt_views", 0),
            "format": t.get("recommended_format"),
        })

    # 2. TV Series 7-Day Radar
    from tv_series_radar import scan_dynamic_tv_virality
    tv_rep = scan_dynamic_tv_virality()
    top_tv = []
    for s in tv_rep.get("ranked_shows", [])[:5]:
        top_tv.append({
            "series": s.get("series_name"),
            "total_views": s.get("total_views", 0),
            "clip_count": s.get("clip_count", 0),
            "top_clip": s.get("top_clip_title", "")[:50],
        })

    # 3. TikTok / IG Audio Trends 7-Day Radar
    from song_trend_radar import scan_dynamic_song_virality
    song_rep = scan_dynamic_song_virality()
    top_songs = []
    for s in song_rep.get("trending_songs", [])[:5]:
        top_songs.append({
            "song": s.get("song_name"),
            "banner": s.get("banner_title"),
            "views": s.get("total_views", 0),
            "score": s.get("virality_score", 0),
        })

    digest = {
        "report_generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "period": "7-Day Cross-Platform Synthesis",
        "top_5_cinema": top_cinema,
        "top_5_tv_series": top_tv,
        "top_5_viral_songs": top_songs,
    }

    DIGEST_FILE.write_text(json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"[Weekly Radar] Digest successfully written to {DIGEST_FILE}")
    return digest


if __name__ == "__main__":
    d = generate_weekly_virality_digest()
    print("\n================== WEEKLY VIRALITY REPORT ==================")
    print("🎬 TOP 5 CINEMA TARGETS:")
    for i, c in enumerate(d["top_5_cinema"], 1):
        print(f"  {i}. {c['topic']} [{c['genre']}] - Score: {c['score']} | Views: {c['views']:,}")

    print("\n📺 TOP 5 TV & WEB SERIES:")
    for i, t in enumerate(d["top_5_tv_series"], 1):
        print(f"  {i}. {t['series']} - {t['total_views']:,} views across {t['clip_count']} edits")

    print("\n🎵 TOP 5 TIKTOK/IG VIRAL SONGS:")
    for i, s in enumerate(d["top_5_viral_songs"], 1):
        print(f"  {i}. {s['song']} - Score: {s['score']} | Views: {s['views']:,}")
    print("============================================================\n")
