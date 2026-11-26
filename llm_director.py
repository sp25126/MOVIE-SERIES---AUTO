"""
Multimodal LLM Video Director & Editor Agent.
Powered by Google Gemini 2.5 Flash Multimodal Vision Intelligence.

Performs frame-by-frame visual analysis to:
1. Detect visual energy curves, hook frames, and beat drops.
2. Determine frame-accurate optimal cut points (start_sec, end_sec).
3. Detect and reject watermarks, CapCut templates, and low-effort slideshows.
4. Score aesthetic quality (1-10) and rank candidate clips.
5. Generate scene HUD labels, dynamic context emojis, and viral metadata.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


def get_gemini_api_key(api_key: Optional[str] = None) -> str:
    if api_key and api_key.strip():
        return api_key.strip()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    # Try loading from .env
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def extract_sample_frames(
    video_path: Path | str,
    num_samples: int = 6,
    max_dimension: int = 480,
) -> List[Tuple[float, str]]:
    """
    Extracts evenly distributed frames across the video timeline and encodes them to base64 JPEG.
    Returns list of (timestamp_sec, base64_jpeg_string).
    """
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.error(f"[LLM Director] Unable to open video: {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    if duration <= 1.0:
        cap.release()
        return []

    # Sample ratios across the video (skip extreme ends to avoid pure black frames)
    if num_samples <= 4:
        ratios = [0.15, 0.40, 0.70, 0.90]
    elif num_samples <= 6:
        ratios = [0.10, 0.25, 0.45, 0.65, 0.85, 0.95]
    else:
        ratios = [i / (num_samples + 1) for i in range(1, num_samples + 1)]

    frames_b64 = []
    for r in ratios:
        sec = r * duration
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * fps))
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        h, w = frame.shape[:2]
        if w > max_dimension or h > max_dimension:
            scale = max_dimension / max(w, h)
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        frames_b64.append((sec, base64.b64encode(buf).decode("utf-8")))

    cap.release()
    return frames_b64


def analyze_clip_frames(
    video_path: Path | str,
    topic: str = "",
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Inspects sequential frames with Gemini 2.5 Flash to extract:
    - Quality score (1-10)
    - Optimal start & end cut points
    - Watermark / low-effort detection
    - Scene HUD label & action description
    """
    key = get_gemini_api_key(api_key)
    video_path = Path(video_path)
    if not key:
        logger.warning("[LLM Director] No GEMINI_API_KEY available. Using fallback heuristics.")
        return _fallback_heuristic_analysis(video_path)

    frames = extract_sample_frames(video_path, num_samples=6)
    if not frames:
        return _fallback_heuristic_analysis(video_path)

    dur = frames[-1][0] / 0.95 if frames else 20.0
    frame_list_text = "\n".join([f"- Frame {i+1}: at {sec:.1f}s" for i, (sec, _) in enumerate(frames)])

    prompt = f"""You are an elite Hollywood & viral short-form video editor for YouTube Shorts and TikTok.
Analyze these {len(frames)} sequential frames sampled across a {dur:.1f}-second candidate video for topic '{topic}':
{frame_list_text}

Perform forensic editorial analysis and respond with ONLY a single JSON object with these exact keys:
{{
  "approved": bool,                 // False if low-effort static slideshow, off-topic, or heavy watermark spam
  "quality_score": float,            // 1.0 to 10.0 (cinematography, lighting, motion, professional grade)
  "has_watermark_spam": bool,        // True if intrusive CapCut, TikTok username watermark, or screen recorder UI
  "scene_label": string,             // 2-3 words punchy title for on-screen HUD (e.g. "Miles Leap", "Cold Stare", "Neil Inversion")
  "optimal_cut": {{
    "start_sec": float,             // Optimal cut start (skip black intros, boring silence, or slow logos)
    "end_sec": float,               // Optimal cut end (cut before trailing outro cards, subscribe logos, or end cards)
    "reason": string
  }},
  "hook_description": string,        // What visual hook captures attention at the start
  "climax_description": string,      // The peak action shot, beat drop, or emotional climax
  "vibe_sentiment": string          // e.g. "dark_thriller", "high_energy_action", "emotional_sad", "hype_cool"
}}

Respond ONLY with valid JSON. No markdown code blocks, no other text."""

    parts: List[Dict[str, Any]] = [{"text": prompt}]
    for sec, b64 in frames:
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64
            }
        })

    try:
        url = f"{GEMINI_API_URL}?key={key}"
        req_body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
        req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Strip markdown if present
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
            raw_text = re.sub(r"\s*```$", "", raw_text).strip()
            res = json.loads(raw_text)

            # Sanitize cut range
            opt = res.get("optimal_cut", {})
            start = max(0.0, float(opt.get("start_sec", 0.0)))
            end = min(dur, float(opt.get("end_sec", dur)))
            if end <= start + 3.0:
                end = dur
            res["optimal_cut"]["start_sec"] = round(start, 2)
            res["optimal_cut"]["end_sec"] = round(end, 2)
            res["optimal_cut"]["duration"] = round(end - start, 2)
            return res
    except Exception as e:
        logger.warning(f"[LLM Director] Gemini analysis failed for {video_path.name}: {e}")
        return _fallback_heuristic_analysis(video_path)


def _fallback_heuristic_analysis(video_path: Path) -> Dict[str, Any]:
    """Heuristic fallback when LLM is unavailable."""
    import cv2
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = total / fps if fps else 20.0
    cap.release()

    start = 1.0 if dur > 12.0 else 0.0
    end = max(dur - 2.0, 5.0) if dur > 12.0 else dur
    return {
        "approved": True,
        "quality_score": 7.5,
        "has_watermark_spam": False,
        "scene_label": "Viral Edit",
        "optimal_cut": {
            "start_sec": round(start, 2),
            "end_sec": round(end, 2),
            "duration": round(end - start, 2),
            "reason": "Default heuristic fallback cut",
        },
        "hook_description": "Opening moment",
        "climax_description": "Core action segment",
        "vibe_sentiment": "hype_cool",
    }


def curate_and_rank_clips(
    candidates: List[Dict[str, Any]],
    topic: str = "",
    target_count: int = 3,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Runs multimodal LLM inspection on all candidate clips.
    Filters out unapproved/spam clips, scores them, and assigns rank #1, #2, #3
    with precision cut ranges and scene labels for the renderer.
    """
    analyzed = []
    for c in candidates:
        local_path = c.get("local_path")
        if not local_path or not Path(local_path).exists():
            continue
        analysis = analyze_clip_frames(local_path, topic=topic, api_key=api_key)
        if not analysis.get("approved", True):
            logger.info(f"[LLM Director] Clip rejected by AI: {c.get('title')}")
            continue

        c_copy = dict(c)
        c_copy["ai_analysis"] = analysis
        c_copy["quality_score"] = analysis.get("quality_score", 7.0)
        c_copy["short_label"] = analysis.get("scene_label") or c.get("short_label") or "Viral Moment"
        c_copy["optimal_cut"] = analysis.get("optimal_cut", {})
        analyzed.append(c_copy)

    # Sort primarily by AI quality score + view count weight
    def score_fn(item: dict) -> float:
        ai_score = item.get("quality_score", 7.0) * 10_000
        views = float(item.get("views") or 1000)
        return ai_score + min(views, 100_000)

    analyzed.sort(key=score_fn, reverse=True)
    curated = analyzed[:target_count]

    # Assign ranks: Rank 1 is top winner
    for i, item in enumerate(curated, 1):
        item["rank"] = i
        logger.info(
            f"[LLM Director] Rank #{i}: {item.get('title')[:35]} | "
            f"Score: {item.get('quality_score')} | "
            f"Label: {item.get('short_label')} | "
            f"Cut: {item.get('optimal_cut', {}).get('start_sec')}s -> {item.get('optimal_cut', {}).get('end_sec')}s"
        )

    return curated
