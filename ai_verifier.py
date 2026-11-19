"""Multimodal clip and content verification using Google Gemini Flash."""

import base64
import json
import os
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMP_DIR = ROOT / "temp"

# Load Gemini API Key from .env or environment
def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def sample_clip_frames(video_path: Path, num_frames: int = 3) -> list[Path]:
    """Extracts evenly spaced frames (e.g. 20%, 50%, 85%) from a downloaded clip for AI review."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
    ]
    try:
        dur = float(subprocess.check_output(probe_cmd, text=True).strip() or 10.0)
    except Exception:
        dur = 10.0

    ratios = [0.20, 0.50, 0.85] if num_frames == 3 else [0.25, 0.75]
    frame_paths = []
    base_id = video_path.stem[:32]
    for idx, r in enumerate(ratios):
        t = max(0.5, dur * r)
        out_jpg = TEMP_DIR / f"ai_frame_{base_id}_{idx}.jpg"
        cmd = [
            "ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_path),
            "-vframes", "1", "-q:v", "3", str(out_jpg)
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and out_jpg.exists() and out_jpg.stat().st_size > 5000:
            frame_paths.append(out_jpg)
    return frame_paths


def verify_clip_with_gemini(video_path: Path, expected_topic: str) -> tuple[bool, str]:
    """Calls Gemini 2.5 Flash to verify that the video is authentic footage matching the expected topic."""
    api_key = get_gemini_api_key()
    if not api_key:
        return True, "No Gemini API key configured, bypassing AI gate"

    frames = sample_clip_frames(video_path, num_frames=3)
    if not frames:
        return True, "Could not extract verification frames"

    parts = [{
        "text": (
            f"You are a strict QA director for a movie & series channel (@OtakuSnapster). "
            f"Review these 3 extracted video frames from a candidate clip. Expected Topic: '{expected_topic}'.\n\n"
            f"Answer two questions in JSON format:\n"
            f"1. 'is_authentic_match': true IF the frames depict the actual character, actor, movie, or series '{expected_topic}'. "
            f"CRITICAL RULES:\n"
            f" - Set false if the footage is from Japanese Anime (e.g. Jujutsu Kaisen, Naruto, Demon Slayer) when the topic is a live-action Western/Indian movie or character (e.g. John Wick, Baba Yaga, Batman).\n"
            f" - Set false if it is an unrelated music video, lyric edit, generic vlogger, or completely different movie.\n"
            f"2. 'is_promo_outro': true IF any of the frames show an obvious 'Like / Share / Subscribe' card, social media handle screen, or generic end promo.\n"
            f"3. 'reason': brief 1-sentence explanation.\n\n"
            f"Output strictly JSON: {{\"is_authentic_match\": bool, \"is_promo_outro\": bool, \"reason\": \"...\"}}"
        )
    }]

    for f in frames:
        b64_data = base64.b64encode(f.read_bytes()).decode("utf-8")
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64_data
            }
        })

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ans_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Clean possible markdown ```json formatting
        if "```" in ans_text:
            ans_text = ans_text.split("```")[1]
            if ans_text.startswith("json"):
                ans_text = ans_text[4:]
        ans_json = json.loads(ans_text.strip())
        is_match = ans_json.get("is_authentic_match", True)
        reason = ans_json.get("reason", "OK")
        print(f"[AI Verifier] Topic='{expected_topic}' -> Match={is_match} | Reason='{reason}'")
        return is_match, reason
    except Exception as e:
        print(f"[AI Verifier] Warning: Gemini verification call skipped ({e})")
        return True, f"AI check skipped: {e}"
    finally:
        for f in frames:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
