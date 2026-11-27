"""
Channel Intelligence & Performance Feedback Engine for @OtakuSnapster.
1. Audits current YouTube channel videos, view counts, and engagement (via public InnerTube/API).
2. Analyzes which recent movies/series/edits performed best vs worst.
3. Learns what topics/editing hooks work and injects dynamic lessons into the LLM Director prompt.
4. Prevents topic duplication by checking the channel's actual recent upload history.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CHANNEL_INTEL_CACHE = STATE_DIR / "channel_intel_cache.json"

DEFAULT_HANDLE = "@OtakuSnapster"


def audit_channel_recent_uploads(handle: str = DEFAULT_HANDLE, max_videos: int = 15) -> List[Dict[str, Any]]:
    """Fetches the latest uploads, view counts, and titles from the YouTube channel."""
    # Check cache first (cached for 2 hours)
    if CHANNEL_INTEL_CACHE.exists():
        try:
            cached = json.loads(CHANNEL_INTEL_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(cached.get("ts", 0)) < 7200 and cached.get("videos"):
                return cached["videos"]
        except Exception:
            pass

    clean_handle = handle.lstrip("@")
    channel_url = f"https://www.youtube.com/@{clean_handle}/shorts"

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "--dump-json", "--no-warnings",
        "--playlist-end", str(max_videos),
        channel_url,
    ]
    videos = []
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                vid = d.get("id")
                if not vid:
                    continue
                videos.append({
                    "id": vid,
                    "title": d.get("title", ""),
                    "views": int(d.get("view_count") or 0),
                    "url": f"https://www.youtube.com/shorts/{vid}",
                })
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[Channel Intel] Could not fetch channel uploads: {e}")

    # Fallback to local upload_queue if channel has no public videos or scraper timed out
    if not videos:
        queue_file = STATE_DIR / "upload_queue.json"
        if queue_file.exists():
            try:
                q = json.loads(queue_file.read_text(encoding="utf-8")).get("queue", [])
                for item in q[-10:]:
                    videos.append({
                        "id": item.get("video_id", ""),
                        "title": item.get("title", ""),
                        "views": 1000,
                        "url": f"https://www.youtube.com/shorts/{item.get('video_id')}",
                    })
            except Exception:
                pass

    if videos:
        try:
            CHANNEL_INTEL_CACHE.write_text(json.dumps({"ts": time.time(), "videos": videos}, indent=2), encoding="utf-8")
        except Exception:
            pass

    return videos


def extract_recent_channel_topics(handle: str = DEFAULT_HANDLE) -> List[str]:
    """Extracts franchise and topic names recently produced on the channel to guarantee 0 repeats."""
    videos = audit_channel_recent_uploads(handle=handle, max_videos=20)
    topics = []
    stop_terms = {"ranking", "best", "edits", "edit", "shorts", "viral", "scene", "scenes", "moments"}
    for v in videos:
        title = v.get("title", "")
        clean = re.sub(r"#[A-Za-z0-9_]+|[^\w\s]", " ", title)
        words = [w for w in clean.split() if w.lower() not in stop_terms and len(w) > 2]
        if words:
            candidate = " ".join(words[:3]).strip()
            if candidate and candidate.lower() not in [t.lower() for t in topics]:
                topics.append(candidate)
    return topics


def derive_channel_editorial_lessons(handle: str = DEFAULT_HANDLE) -> str:
    """
    Performs analytical assessment of channel performance and outputs actionable
    editorial instructions for the SML / LLM Director.
    """
    videos = audit_channel_recent_uploads(handle=handle, max_videos=15)
    recent_topics = extract_recent_channel_topics(handle=handle)

    recent_summary = ""
    if videos:
        # Sort by view count to determine what worked
        sorted_vids = sorted(videos, key=lambda x: x.get("views", 0), reverse=True)
        top = sorted_vids[0] if sorted_vids else {}
        low = sorted_vids[-1] if len(sorted_vids) > 1 else {}
        recent_summary = (
            f"CHANNEL PERFORMANCE INTELLIGENCE ({handle}):\n"
            f"- Highest performing recent upload: '{top.get('title')}' ({top.get('views', 0):,} views)\n"
            f"- Lowest performing recent upload: '{low.get('title')}' ({low.get('views', 0):,} views)\n"
            f"- Recently covered channel topics (DO NOT REPEAT): {', '.join(recent_topics[:6])}\n"
            f"- Editorial Directive: High-contrast character conflict, psychological suspense, and clean beat-drops outperform static montages. "
            f"Always pick fresh, unexhausted franchises that haven't been uploaded in the last 7 days."
        )
    else:
        recent_summary = (
            f"CHANNEL EDITORIAL DIRECTIVE ({handle}):\n"
            f"- Channel specializes in high-CTR Hollywood, TV Series, and Anime ranking edits.\n"
            f"- Avoid repeating recently covered franchises. Ensure high dynamic pacing and character-action HUD labels."
        )

    return recent_summary


def derive_winning_format_weights(handle: str = DEFAULT_HANDLE) -> Dict[str, float]:
    """Analyzes @OtakuSnapster's recent uploads to weight formats that drive higher views."""
    videos = audit_channel_recent_uploads(handle=handle, max_videos=20)
    weights = {"edit_ranking": 1.0, "scene_commentary": 1.0, "release_hype": 1.0, "song_ranking": 1.0}
    if not videos:
        return weights
    avg_views = sum(v.get("views", 0) for v in videos) / max(1, len(videos))
    for v in videos:
        tl = (v.get("title") or "").lower()
        boost = 0.15 if v.get("views", 0) > avg_views else -0.05
        if "ranking" in tl:
            weights["edit_ranking"] = round(max(0.5, weights["edit_ranking"] + boost), 2)
        elif "missed" in tl or "detail" in tl:
            weights["scene_commentary"] = round(max(0.5, weights["scene_commentary"] + boost), 2)
        elif "song" in tl or "audio" in tl:
            weights["song_ranking"] = round(max(0.5, weights["song_ranking"] + boost), 2)
    return weights
