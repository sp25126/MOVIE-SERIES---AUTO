"""
100% Dynamic TV Shows Virality Radar & Discovery Engine.
Tracks trending television & streaming series (HBO, Netflix, Prime, AMC, Disney+)
(e.g., The Mentalist, Breaking Bad, Peaky Blinders, Game of Thrones, The Boys,
Stranger Things, Succession, Better Call Saul, Dexter, Severance, House of the Dragon).
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
TV_REPORT_PATH = STATE_DIR / "tv_virality_report.json"

POPULAR_TV_SERIES_CATALOG = [
    {"series": "The Mentalist", "character": "Patrick Jane", "network": "CBS", "query_theme": "Patrick Jane edit shorts"},
    {"series": "Breaking Bad", "character": "Walter White", "network": "AMC", "query_theme": "Walter White Breaking Bad edit shorts"},
    {"series": "Peaky Blinders", "character": "Thomas Shelby", "network": "BBC / Netflix", "query_theme": "Thomas Shelby edit shorts"},
    {"series": "Better Call Saul", "character": "Saul Goodman / Lalo", "network": "AMC", "query_theme": "Lalo Salamanca edit shorts"},
    {"series": "Game of Thrones", "character": "Jon Snow / Daenerys", "network": "HBO", "query_theme": "Game of Thrones cold edit shorts"},
    {"series": "The Boys", "character": "Homelander / Billy Butcher", "network": "Amazon Prime", "query_theme": "Homelander edit shorts"},
    {"series": "Succession", "character": "Logan Roy / Kendall Roy", "network": "HBO", "query_theme": "Succession Kendall Roy edit shorts"},
    {"series": "Stranger Things", "character": "Eddie Munson / Eleven", "network": "Netflix", "query_theme": "Stranger Things edit shorts"},
    {"series": "Severance", "character": "Mark Scout", "network": "Apple TV+", "query_theme": "Severance edit shorts"},
    {"series": "Sherlock", "character": "Sherlock Holmes", "network": "BBC", "query_theme": "Sherlock Benedict Cumberbatch edit shorts"},
    {"series": "Dexter", "character": "Dexter Morgan", "network": "Showtime", "query_theme": "Dexter Morgan edit shorts"},
    {"series": "Suits", "character": "Harvey Specter", "network": "USA Network", "query_theme": "Harvey Specter coldest edit shorts"},
]


def scout_tv_series_edits(tv_item: dict, count: int = 3) -> List[dict]:
    """
    Scouts YouTube Shorts for the top ranked viral edits for a specific TV show.
    """
    query = tv_item["query_theme"]
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json", "--no-playlist", "--no-warnings",
        "--match-filter", "duration <= 60 & duration >= 8",
        f"ytsearch10:{query}",
    ]
    edits = []
    seen = set()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue

            vid = d.get("id")
            if not vid or vid in seen:
                continue
            seen.add(vid)

            title = d.get("title") or ""
            creator = d.get("channel") or d.get("uploader") or "Creator"
            views = int(d.get("view_count") or 0)
            dur = float(d.get("duration") or 25.0)

            edits.append({
                "id": f"yt_{vid}",
                "platform": "youtube",
                "title": title,
                "creator": f"@{creator.replace(' ', '')}" if not creator.startswith("@") else creator,
                "views": views,
                "duration": dur,
                "url": d.get("webpage_url") or f"https://youtube.com/watch?v={vid}",
            })
    except Exception as e:
        logger.error(f"[TV Radar] Scout error for {query}: {e}")

    edits.sort(key=lambda x: x["views"], reverse=True)
    return edits[:count]


def scan_tv_virality() -> dict:
    """
    Scans the TV show edit landscape and ranks the hottest series by total edit volume & views.
    """
    ranked_shows = []
    for item in POPULAR_TV_SERIES_CATALOG:
        edits = scout_tv_series_edits(item, count=3)
        total_views = sum(e["views"] for e in edits)
        ranked_shows.append({
            "series": item["series"],
            "character": item["character"],
            "network": item["network"],
            "banner_title": f"RANKING THE BEST {item['series'].upper()} EDITS",
            "total_views": total_views,
            "edits": edits,
        })

    ranked_shows.sort(key=lambda x: x["total_views"], reverse=True)
    winner = ranked_shows[0] if ranked_shows else POPULAR_TV_SERIES_CATALOG[0]

    report = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "winner": winner,
        "shows": ranked_shows,
    }
    TV_REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    rep = scan_tv_virality()
    w = rep["winner"]
    print(f"[TV Radar] #1 Trending TV Show: '{w['series']}' ({w.get('character', '')}) with {w['total_views']:,} total views")
    for i, e in enumerate(w.get("edits", []), 1):
        print(f"  #{i}: [{e['views']:,} views] {e['title'][:45]} by {e['creator']}")
