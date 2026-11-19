"""
Dynamic Trending Hashtag Harvester & Booster.
Discovers what hashtags are currently blowing up across Shorts, Reels & TikTok
(e.g., #naofloppa, #shortsfeed, #velocity, #phonk, #viralvideo).
Updated weekly or on-demand, storing live tag clouds in state/trending_hashtags.json.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Set

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
TAGS_CACHE_FILE = STATE_DIR / "trending_hashtags.json"

DEFAULT_VIRAL_TAGS = [
    "#naofloppa", "#shortsfeed", "#viral", "#edits", "#phonk",
    "#cinema", "#trending", "#fyp", "#explore", "#movieclips",
]


def harvest_trending_hashtags(force: bool = False) -> List[str]:
    """
    Extracts high-velocity hashtags from trending edits on YouTube Shorts, TikTok & Reels.
    Caches results for 7 days so it refreshes weekly.
    """
    now_ts = time.time()
    if not force and TAGS_CACHE_FILE.exists():
        try:
            cached = json.loads(TAGS_CACHE_FILE.read_text(encoding="utf-8"))
            if now_ts - cached.get("timestamp", 0) < 7 * 86400:
                return cached.get("trending_hashtags", DEFAULT_VIRAL_TAGS)
        except Exception:
            pass

    queries = [
        "#shorts #viral #edit",
        "#naofloppa",
        "trending edit shorts 2026",
        "velocity edit shorts",
        "viral reels audio edit",
    ]
    hashtags_freq = {}
    for q in queries:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist", "--dump-json", "--no-warnings",
            f"ytsearch5:{q}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                text = f"{d.get('title') or ''} {d.get('description') or ''}"
                for tag in re.findall(r"#([A-Za-z0-9_]+)", text):
                    tl = f"#{tag.lower()}"
                    # Skip noise
                    if len(tl) > 2 and tl not in ("#shorts", "#short"):
                        hashtags_freq[tl] = hashtags_freq.get(tl, 0) + 1
        except Exception as e:
            logger.debug(f"[Hashtag Radar] Query error ({q}): {e}")

    # Ensure current mega-trends are always included
    hashtags_freq["#naofloppa"] = max(hashtags_freq.get("#naofloppa", 0), 10)
    hashtags_freq["#shortsfeed"] = max(hashtags_freq.get("#shortsfeed", 0), 9)
    hashtags_freq["#viral"] = max(hashtags_freq.get("#viral", 0), 8)

    sorted_tags = [t for t, _ in sorted(hashtags_freq.items(), key=lambda x: x[1], reverse=True)[:15]]

    payload = {
        "timestamp": now_ts,
        "date_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trending_hashtags": sorted_tags,
    }
    TAGS_CACHE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return sorted_tags


if __name__ == "__main__":
    tags = harvest_trending_hashtags(force=True)
    print("Live Harvested Trending Hashtags:")
    print(" ".join(tags))
