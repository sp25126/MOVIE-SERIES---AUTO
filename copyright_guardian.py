"""
Copyright Founder & Auto-Remediator for Final Rendered Shorts.
Scans final rendered MP4s + source clips for Content-ID / copyright risks and automatically:
1. Applies minor transformative tweaks (48kHz +5% pitch/tempo shield, 0.94x crop, eq grade) OR
2. Replaces claimed audio with verified royalty-free BGM (fetch_trending_bgm) OR
3. Swaps out a flagged source clip with a clean backup candidate and triggers re-render.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FFMPEG = "ffmpeg"


def scan_final_video_copyright(video_path: Path, source_clips: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Audits both the source clips and final rendered MP4 for copyright / Content-ID risk.
    Returns: {"clean": bool, "risk_level": "low|medium|high", "flagged_clip_ids": list, "reasons": list}
    """
    from clip_harvester import passes_copyright_prefilter, has_youtube_cid_claim

    flagged_ids: List[str] = []
    reasons: List[str] = []

    for c in source_clips:
        cid = str(c.get("id") or "")
        ok_pre, why_pre = passes_copyright_prefilter(c, min_duration=4, check_html=False)
        if not ok_pre:
            flagged_ids.append(cid)
            reasons.append(f"{cid}: {why_pre}")
            continue
        if cid.startswith("yt_") and len(cid) > 3:
            claimed, why_cid = has_youtube_cid_claim(cid[3:])
            if claimed:
                flagged_ids.append(cid)
                reasons.append(f"{cid}: {why_cid}")

    # Verify final MP4 exists & has proper 48kHz audio (Anti-CID shield indicator)
    vp = Path(video_path)
    if not vp.exists():
        reasons.append("Final video file missing")
    else:
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(vp)],
                capture_output=True, text=True, timeout=10,
            )
            sr = int((probe.stdout or "0").strip() or 0)
            if sr != 48000:
                reasons.append(f"Audio sample rate is {sr}Hz (needs 48000Hz Anti-CID shield)")
        except Exception:
            pass

    clean = len(flagged_ids) == 0 and len(reasons) == 0
    risk = "high" if flagged_ids else ("medium" if reasons else "low")
    return {"clean": clean, "risk_level": risk, "flagged_clip_ids": flagged_ids, "reasons": reasons}


def apply_minor_copyright_tweaks(video_path: Path, topic: str = "", genre: str = "action_thriller", replace_audio_with_bgm: bool = False) -> Path:
    """
    Applies transformative Anti-CID tweaks to a rendered MP4 in-place:
    - +5% pitch/tempo audio shield (or replaces audio with verified no-copyright BGM if claimed)
    - 0.94x subtle zoom/crop + mild contrast/saturation shift
    - Preserves 1080x1920 @ 30fps and -14.0 LUFS loudness
    """
    vp = Path(video_path)
    tmp_out = vp.with_name(f"{vp.stem}_shielded.mp4")

    bgm_path: Optional[Path] = None
    if replace_audio_with_bgm:
        try:
            from clip_harvester import fetch_trending_bgm
            bgm_path = fetch_trending_bgm("phonk")
        except Exception:
            bgm_path = None
        if not bgm_path or not bgm_path.exists():
            try:
                from dsp_renderer import ensure_royalty_free_bgm
                bgm_path = ensure_royalty_free_bgm(style="auto", genre=genre, allow_network=False)
            except Exception:
                bgm_path = None

    vf = (
        "[0:v]setpts=PTS/1.03,crop=trunc(iw*0.94/2)*2:trunc(ih*0.94/2)*2,"
        "scale=1080:1920,eq=contrast=1.05:saturation=1.08,format=yuv420p[vout]"
    )

    if bgm_path and bgm_path.exists():
        logger.info(f"[Copyright Guardian] Replacing claimed audio with clean royalty-free BGM: {bgm_path.name}")
        af = (
            "[1:a]aresample=48000,loudnorm=I=-14.0:TP=-1.5:LRA=7.0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )
        cmd = [
            FFMPEG, "-y",
            "-i", str(vp), "-stream_loop", "-1", "-i", str(bgm_path),
            "-filter_complex", f"{vf};{af}",
            "-map", "[vout]", "-map", "[aout]",
            "-shortest",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(tmp_out),
        ]
    else:
        logger.info("[Copyright Guardian] Applying minor transformative Anti-CID tweaks (+5% audio shield + 0.94x crop)...")
        af = (
            "[0:a]aresample=48000,highpass=f=90,asetrate=48000*1.05,atempo=1/1.02,"
            "aresample=48000,loudnorm=I=-14.0:TP=-1.5:LRA=7.0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )
        cmd = [
            FFMPEG, "-y", "-i", str(vp),
            "-filter_complex", f"{vf};{af}",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(tmp_out),
        ]

    subprocess.run(cmd, capture_output=True, check=True, timeout=180)
    if tmp_out.exists() and tmp_out.stat().st_size > 50_000:
        tmp_out.replace(vp)
    return vp


def remediate_copyright_if_needed(
    video_path: Path,
    curated_clips: List[Dict[str, Any]],
    backup_pool: List[Dict[str, Any]],
    topic: str = "",
    genre: str = "action_thriller",
) -> Dict[str, Any]:
    """
    Runs copyright scan on final video + clips. If flagged:
    - Attempts to swap flagged clips with clean backups from backup_pool
    - Applies minor transformative tweaks (or BGM replacement) if needed.
    """
    scan = scan_final_video_copyright(video_path, curated_clips)
    if scan["clean"]:
        return {"remediated": False, "swapped_clips": False, "scan": scan}

    logger.warning(f"🛡️ [Copyright Guardian] Flagged issues: {scan['reasons']}")
    swapped = False
    flagged = set(scan["flagged_clip_ids"])
    used_ids = {c.get("id") for c in curated_clips}
    clean_backups = [b for b in backup_pool if b.get("id") not in used_ids and b.get("id") not in flagged]

    if flagged and clean_backups:
        for idx, c in enumerate(curated_clips):
            if c.get("id") in flagged and clean_backups:
                rep = clean_backups.pop(0)
                logger.info(f"🔄 [Copyright Guardian] Replacing claimed clip {c.get('id')} -> {rep.get('id')}")
                curated_clips[idx] = rep
                swapped = True

    if not swapped:
        apply_minor_copyright_tweaks(video_path, topic=topic, genre=genre, replace_audio_with_bgm=bool(flagged))

    return {"remediated": True, "swapped_clips": swapped, "scan": scan}
