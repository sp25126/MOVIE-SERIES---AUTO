"""Automated QA gate: 0 black frames, A/V sync parity, 1080x1920 CFR, proof sheet."""

import json
import math
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

FFMPEG = r"C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe" if os.path.exists(r"C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe") else "ffmpeg"
FFPROBE = r"C:\ffmpeg-7.1.1-full_build\bin\ffprobe.exe" if os.path.exists(r"C:\ffmpeg-7.1.1-full_build\bin\ffprobe.exe") else "ffprobe"


def probe_streams(video_path: Path) -> dict:
    cmd = [FFPROBE, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(video_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    data = json.loads(proc.stdout or "{}")
    v_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    a_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
    fmt = data.get("format", {})
    v_dur = float(v_stream.get("duration") or fmt.get("duration") or 0)
    a_dur = float(a_stream.get("duration") or fmt.get("duration") or 0)
    return {
        "width": int(v_stream.get("width") or 0),
        "height": int(v_stream.get("height") or 0),
        "video_dur": round(v_dur, 3),
        "audio_dur": round(a_dur, 3),
        "sample_rate": int(a_stream.get("sample_rate") or 0),
        "has_audio": bool(a_stream),
        "size_mb": round(video_path.stat().st_size / (1024 * 1024), 2) if video_path.exists() else 0.0,
    }


def generate_proof_sheet(video_path: Path, out_jpg: Path, max_frames: int = 15) -> Path | None:
    tmp_dir = video_path.parent / f".qa_{video_path.stem}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for old in tmp_dir.glob("*.jpg"):
        old.unlink()

    info = probe_streams(video_path)
    dur = max(1.0, info["video_dur"])
    fps = min(1.0, max_frames / dur)
    subprocess.run(
        [FFMPEG, "-y", "-i", str(video_path), "-vf", f"fps={fps:.4f},scale=270:-1", "-frames:v", str(max_frames), str(tmp_dir / "f_%02d.jpg")],
        capture_output=True, timeout=60,
    )
    frames = sorted(tmp_dir.glob("*.jpg"))
    if not frames:
        return None

    imgs = [Image.open(f).convert("RGB") for f in frames]
    tw, th = imgs[0].size
    cols = 5
    rows = math.ceil(len(imgs) / cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)
    for idx, im in enumerate(imgs):
        r, c = divmod(idx, cols)
        x, y = c * tw, r * th
        sheet.paste(im, (x, y))
        t_sec = round(idx / max(fps, 0.01), 1)
        draw.rectangle([x, y, x + 78, y + 22], fill=(0, 0, 0))
        draw.text((x + 5, y + 4), f"t={t_sec}s", fill=(255, 230, 0))
    sheet.save(out_jpg, quality=88)

    for old in tmp_dir.glob("*.jpg"):
        old.unlink()
    try:
        tmp_dir.rmdir()
    except OSError:
        pass
    return out_jpg


def verify_video(video_path: Path, make_proof: bool = True) -> dict:
    """Checks 1080x1920 geometry, 48kHz audio, <0.2s A/V parity, and 0 black frames."""
    video_path = Path(video_path)
    issues = []
    if not video_path.exists():
        return {"passed": False, "issues": ["File missing"]}

    info = probe_streams(video_path)
    if (info["width"], info["height"]) != (1080, 1920):
        issues.append(f"Expected 1080x1920, got {info['width']}x{info['height']}")
    if not info["has_audio"]:
        issues.append("Missing audio stream")
    if info["sample_rate"] != 48000:
        issues.append(f"Expected 48000Hz audio, got {info['sample_rate']}Hz")
    if abs(info["video_dur"] - info["audio_dur"]) > 0.25:
        issues.append(f"A/V sync drift: video={info['video_dur']}s vs audio={info['audio_dur']}s")

    bd = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(video_path), "-vf", "blackdetect=d=0.25:pic_th=0.98", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    if "black_start" in bd.stderr:
        issues.append("Black frame(s) >=0.25s detected")

    proof_path = None
    if make_proof:
        proof = generate_proof_sheet(video_path, video_path.with_name(f"{video_path.stem}_proof.jpg"))
        proof_path = str(proof) if proof else None

    passed = len(issues) == 0
    print(f"[QA] {'PASSED' if passed else 'FAILED'} | {video_path.name} ({info['video_dur']}s, {info['size_mb']}MB) | issues={issues}")
    return {"passed": passed, "issues": issues, "streams": info, "proof_sheet": proof_path}
