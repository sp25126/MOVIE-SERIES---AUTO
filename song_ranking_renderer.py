"""
Song Edit Ranking Renderer (Reference: https://youtube.com/shorts/W3iVcOGJLWM).
- One Song / Trend, Multiple Creator Edits Ranked.
- NO VOICEOVER.
- Full uncropped vertical blurred composite.
- Prominent top banner (e.g. 'RANKING THE BEST PAPARAZZI TREND EDITS').
- Left-side ranking countdown badge (#3 -> #2 -> #1) with view count badge.
- On-screen editor credit badge (e.g. 'Edit by @Creator').
- Continuous master song audio with smooth crossfades between clips.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
TEMP_DIR = ROOT / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
FFMPEG = "ffmpeg"


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_paths = [
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _format_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M VIEWS"
    elif n >= 1_000:
        return f"{n / 1_000:.0f}K VIEWS"
    return f"{n} VIEWS"


def create_song_ranking_overlay(
    banner_title: str,
    rank: int,
    total: int,
    views: int,
    creator: str,
    out_png: Path,
    handle: str = "@OtakuSnapster",
) -> Path:
    """
    Renders the exact graphical HUD seen in BlinkRanks (https://youtube.com/shorts/W3iVcOGJLWM):
    1. Top Banner: High-impact black & gold / yellow container with bold uppercase title.
    2. Upper-Left Rank Pill: Gold/Yellow metallic pill badge '#1', '#2', '#3' + Views pill.
    3. Bottom-Left / Center: 'Edit by @Creator' attribution.
    4. Top-Right: Discreet channel watermark '@OtakuSnapster'.
    """
    w, h = 1080, 1920
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    # 1. Top Stacked Header (Clean outlined typography — zero heavy box clutter)
    words = banner_title.upper().split()
    line1 = " ".join(words[:4])
    line2 = " ".join(words[4:]) if len(words) > 4 else ""

    if line2:
        draw.text((w // 2, 110), line1, font=_get_font(48, bold=True), fill=(255, 255, 255), anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
        draw.text((w // 2, 168), line2, font=_get_font(50, bold=True), fill=(255, 215, 0), anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
    else:
        draw.text((w // 2, 140), line1, font=_get_font(52, bold=True), fill=(255, 215, 0), anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))

    # 2. Ranking Badge (Left Side Pill Stack)
    rank_colors = {
        1: ((255, 215, 0), (0, 0, 0)),      # Gold for #1
        2: ((220, 220, 230), (10, 10, 15)), # Silver for #2
        3: ((205, 127, 50), (255, 255, 255)),# Bronze for #3
    }
    bg_col, txt_col = rank_colors.get(rank, ((240, 240, 240), (0, 0, 0)))

    badge_x, badge_y = 70, 270
    badge_w, badge_h = 170, 95
    # Rounded ranking pill
    draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + badge_h)], radius=20, fill=bg_col, outline=(255, 255, 255), width=3)
    draw.text((badge_x + badge_w // 2, badge_y + badge_h // 2), f"#{rank}", font=_get_font(60, bold=True), fill=txt_col, anchor="mm")

    # Views Pill underneath
    if views > 0:
        views_txt = _format_views(views)
        vw_box_w = 230
        draw.rounded_rectangle([(badge_x, badge_y + badge_h + 12), (badge_x + vw_box_w, badge_y + badge_h + 54)], radius=12, fill=(20, 20, 25, 220), outline=(255, 215, 0, 180), width=2)
        draw.text((badge_x + vw_box_w // 2, badge_y + badge_h + 33), views_txt, font=_get_font(24, bold=True), fill=(255, 215, 0), anchor="mm")

    # 3. Creator Attribution Pill (Bottom-Left / Mid)
    if creator:
        clean_cr = creator if creator.startswith("@") else f"@{creator}"
        credit_txt = f"EDIT BY {clean_cr.upper()}"
        font_cr = _get_font(28, bold=True)
        cr_box_y = 1580
        draw.rounded_rectangle([(70, cr_box_y), (520, cr_box_y + 55)], radius=14, fill=(10, 10, 12, 230), outline=(255, 255, 255, 200), width=2)
        draw.text((295, cr_box_y + 28), credit_txt, font=font_cr, fill=(255, 255, 255), anchor="mm")

    # 4. Subtle Top-Right Channel Watermark
    draw.text((w - 80, 270), handle, font=_get_font(26, bold=True), fill=(255, 255, 255, 180), anchor="ra")

    im.save(out_png, "PNG")
    return out_png


def render_song_edit_ranking(
    banner_title: str,
    clips: List[dict],
    output_mp4: Path,
    handle: str = "@OtakuSnapster",
    clip_dur: float = 8.5,
) -> Path:
    """
    Renders the complete Song Edit Ranking Short:
    - Plays ranked edits from #3 -> #2 -> #1 (or #N down to #1).
    - ZERO VOICEOVER. Original music track is extracted or mixed continuously across all clips.
    - Each clip gets 16:9 uncropped blur composition with synchronized HUD.
    """
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)

    total = len(clips)
    play_order = list(range(total, 0, -1)) # E.g. #3 -> #2 -> #1

    segment_paths = []
    for rank in play_order:
        clip = clips[rank - 1]
        src = Path(clip["local_path"])
        views = int(clip.get("views") or 0)
        creator = clip.get("creator") or "@Editor"

        ov_png = TEMP_DIR / f"song_ov_rank_{rank}.png"
        create_song_ranking_overlay(banner_title, rank, total, views, creator, ov_png, handle=handle)

        seg_mp4 = TEMP_DIR / f"song_seg_{rank}.mp4"

        # Clip Duration & AI Optimal Cut resolution
        src_dur = float(clip.get("duration") or clip_dur)
        ai_cut = clip.get("optimal_cut") or {}
        if ai_cut.get("end_sec") and float(ai_cut.get("end_sec")) > float(ai_cut.get("start_sec", 0.0)) + 3.0:
            ss = max(0.0, float(ai_cut.get("start_sec", 0.0)))
            ai_dur = float(ai_cut["end_sec"]) - ss
            dur = min(clip_dur, ai_dur) if clip_dur > 0 else ai_dur
        else:
            dur = clip_dur if clip_dur > 0 else src_dur
            dur = min(dur, src_dur)
            # Land right in the causal climax/drop of the edit (around 18% in)
            ss = 0.0
            if src_dur > dur + 2.0:
                ss = min(max(1.0, src_dur * 0.18), src_dur - dur - 0.5)

        try:
            from dsp_renderer import _detect_black_bar_crop, _safe_start_offset
            if ss < 0.8 and dur > 6.0:
                safe_ss = _safe_start_offset(src, src_dur, dur - 1.0)
                if safe_ss > ss:
                    dur = max(4.0, dur - (safe_ss - ss))
                    ss = safe_ss
            bar_crop = _detect_black_bar_crop(src, ss + min(2.5, dur * 0.35))
        except Exception:
            bar_crop = ""

        # Dual-layer blurred vertical canvas (scales 9:16 up to 1080x1440 and 16:9 crisply)
        vf = (
            f"[0:v]trim=0:{dur:.3f},setpts=(PTS-STARTPTS)/1.03,fps=30,{bar_crop}split=2[bg0][fg0];"
            f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24,eq=brightness=-0.16[bg];"
            f"[fg0]crop=trunc(iw*0.97/2)*2:trunc(ih*0.97/2)*2,scale=1080:1440:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2,eq=contrast=1.08:saturation=1.14[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
            f"[comp][1:v]overlay=0:0,format=yuv420p[vout]"
        )

        # Forensic 48kHz +3% Anti-CID shield + smooth fade transitions + -14.0 LUFS
        out_dur = dur / 1.03
        fade_out_st = max(0.2, out_dur - 0.20)
        try:
            from dsp_renderer import _has_audio_stream
            has_aud = _has_audio_stream(src)
        except Exception:
            has_aud = True

        if has_aud:
            af_cmd = (
                f"[0:a]aresample=48000,highpass=f=80,asetrate=48000*1.03,atempo=1.0,aresample=48000,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                f"atrim=0:{out_dur:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d=0.12,afade=t=out:st={fade_out_st:.3f}:d=0.18,"
                f"loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aresample=48000[aout]"
            )
            cmd = [
                FFMPEG, "-y",
                "-ss", f"{ss:.2f}", "-i", str(src),
                "-i", str(ov_png),
                "-filter_complex", f"{vf};{af_cmd}",
                "-map", "[vout]", "-map", "[aout]",
                "-t", f"{out_dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                str(seg_mp4),
            ]
        else:
            cmd = [
                FFMPEG, "-y",
                "-ss", f"{ss:.2f}", "-i", str(src),
                "-i", str(ov_png),
                "-f", "lavfi", "-t", f"{out_dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
                "-filter_complex", vf,
                "-map", "[vout]", "-map", "2:a",
                "-t", f"{out_dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                str(seg_mp4),
            ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        segment_paths.append(seg_mp4)

    # Concat segments into final master
    concat_txt = TEMP_DIR / "song_concat.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
    concat_txt.write_text("\n".join(lines), encoding="utf-8")

    cmd_concat = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_txt),
        "-c", "copy",
        str(output_mp4),
    ]
    subprocess.run(cmd_concat, capture_output=True, check=True, timeout=120)
    return output_mp4
