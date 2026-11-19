"""Pure FFmpeg + Pillow 1080x1920 renderer (zero voiceover) with 4-layer Anti-CID shield."""

import math
import os
import struct
import subprocess
import textwrap
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BGM_DIR = ROOT / "assets" / "bgm"
TEMP_DIR = ROOT / "temp"
LOGO_PATH = ROOT / "otakulogo.jpg"

FFMPEG = r"C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe" if os.path.exists(r"C:\ffmpeg-7.1.1-full_build\bin\ffmpeg.exe") else "ffmpeg"


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        [
            "C:/Windows/Fonts/impact.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for fp in candidates:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def ensure_royalty_free_bgm(style: str = "phonk", allow_network: bool = True) -> Path:
    """Prefers real trending no-copyright BGM (assets/bgm/), auto-fetches if missing, falls back to synth."""
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    # 1. Prefer user-provided or cached trending mp3/wav (excluding synth_*)
    for ext in ("*.mp3", "*.wav"):
        for f in sorted(BGM_DIR.glob(ext)):
            if not f.stem.startswith("synth_") and style in f.stem.lower() and f.stat().st_size > 100_000:
                return f

    # 2. Fetch real trending no-copyright BGM dynamically
    if allow_network:
        try:
            from clip_harvester import fetch_trending_bgm
            fetched = fetch_trending_bgm(style=style, out_dir=BGM_DIR)
            if fetched and fetched.exists():
                return fetched
        except Exception:
            pass

    out = BGM_DIR / f"synth_{style}.wav"
    if out.exists() and out.stat().st_size > 30_000:
        return out

    # Procedural original 48kHz stereo WAV stems via stdlib wave (100% copyright-free, zero lavfi quoting bugs)
    sr, dur_s = 48000, 30
    total = sr * dur_s
    buf = bytearray(total * 4)
    for i in range(total):
        t = i / sr
        if style == "phonk":
            v = (
                0.32 * math.sin(2 * math.pi * 55.0 * t) * math.exp(-5.0 * (t % 0.5))
                + 0.16 * math.sin(2 * math.pi * 110.0 * t) * math.exp(-9.0 * (t % 0.25))
                + 0.08 * math.sin(2 * math.pi * 220.0 * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 2.0 * t))
            )
        elif style == "rock":
            v = (
                0.26 * math.sin(2 * math.pi * 82.4 * t) * math.exp(-3.5 * (t % 0.375))
                + 0.18 * math.sin(2 * math.pi * 123.5 * t) * math.exp(-6.0 * (t % 0.75))
                + 0.07 * math.sin(2 * math.pi * 329.6 * t)
            )
        else:
            v = (
                0.20 * math.sin(2 * math.pi * 130.8 * t)
                + 0.14 * math.sin(2 * math.pi * 196.0 * t)
                + 0.10 * math.sin(2 * math.pi * 246.9 * t) * (0.5 + 0.5 * math.sin(2 * math.pi * 0.25 * t))
            )
        sample = max(-32767, min(32767, int(v * 26000)))
        struct.pack_into("<hh", buf, i * 4, sample, sample)

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(buf)
    return out


def _draw_outlined_text(draw: ImageDraw.ImageDraw, pos: tuple[int, int], text: str, font, fill, stroke: int = 5, anchor: str = "mm"):
    draw.text(pos, text, font=font, fill=fill, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def _draw_brand_and_credit(img: Image.Image, draw: ImageDraw.ImageDraw, handle: str, y_brand: int, editor_credit: str = ""):
    """Pastes circular otakulogo.jpg + @OtakuSnapster badge, plus visible on-screen editor credit."""
    f_brand = _font(36, bold=True)
    bbox = draw.textbbox((0, 0), handle, font=f_brand)
    text_w = bbox[2] - bbox[0]
    logo_sz = 64
    gap = 14

    if LOGO_PATH.exists():
        total_w = logo_sz + gap + text_w
        x0 = int((1080 - total_w) / 2)
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA").resize((logo_sz, logo_sz), Image.Resampling.LANCZOS)
            mask = Image.new("L", (logo_sz, logo_sz), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, logo_sz - 1, logo_sz - 1], fill=255)
            img.paste(logo, (x0, int(y_brand - logo_sz / 2)), mask)
            draw.ellipse([x0 - 2, int(y_brand - logo_sz / 2) - 2, x0 + logo_sz + 1, int(y_brand + logo_sz / 2) + 1], outline=(0, 229, 255, 220), width=3)
            _draw_outlined_text(draw, (x0 + logo_sz + gap, y_brand), handle, f_brand, (255, 255, 255, 230), stroke=3, anchor="lm")
        except Exception:
            _draw_outlined_text(draw, (540, y_brand), handle, f_brand, (255, 255, 255, 230), stroke=3)
    else:
        _draw_outlined_text(draw, (540, y_brand), handle, f_brand, (255, 255, 255, 230), stroke=3)

    if editor_credit:
        clean_ed = editor_credit.strip()[:28]
        _draw_outlined_text(draw, (540, y_brand + 56), f"Edit Credit: {clean_ed}", _font(28, bold=False), (220, 235, 255, 215), stroke=3)


def _make_ranking_overlay(topic: str, rank: int, total: int, labels: list[str], handle: str, out_png: Path, editor_credit: str = "", revealed_ranks: set[int] | None = None) -> Path:
    """Krylo Ranks / Silenthaze style: stacked colored top title + persistent left ladder + logo & editor credit."""
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Top title (stacked like Ref #9: "Ranking Best" / "<Topic> Edits")
    f_top = _font(64, bold=True)
    f_sub = _font(72, bold=True)
    _draw_outlined_text(draw, (410, 145), "Ranking", f_top, (255, 255, 255), stroke=6)
    _draw_outlined_text(draw, (650, 145), "Best", f_top, (57, 255, 20), stroke=6)
    short_topic = topic[:18].strip()
    _draw_outlined_text(draw, (540, 232), f"{short_topic} Edits", f_sub, (0, 229, 255), stroke=6)

    # Left-side persistent ladder (1. .. total.) populating as each rank plays (supports shuffled 2->4->5->3->1!)
    f_lad = _font(42, bold=True)
    rank_colors = {1: (255, 65, 85), 2: (0, 229, 255), 3: (255, 230, 0), 4: (255, 255, 255), 5: (220, 220, 220)}
    y0 = 640
    for r in range(1, total + 1):
        y = y0 + (r - 1) * 72
        revealed = (r in revealed_ranks) if revealed_ranks is not None else (r >= rank)
        is_active = r == rank
        lbl = labels[r - 1][:22] if (revealed and r - 1 < len(labels)) else ""
        text = f"{r}. {lbl}" if lbl else f"{r}."
        color = rank_colors.get(r, (255, 255, 255)) if is_active else ((235, 235, 235) if revealed else (160, 160, 160))
        _draw_outlined_text(draw, (44, y), text, f_lad, color, stroke=4, anchor="lm")

    # Channel logo + @OtakuSnapster + on-screen Editor Credit below main video frame
    _draw_brand_and_credit(img, draw, handle, y_brand=1505, editor_credit=editor_credit)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def _make_banner_overlay(headline: str, bottom_label: str, handle: str, out_png: Path, dark_mode: bool = False, impact_emoji: str = "", editor_credit: str = "") -> Path:
    """Top white meme/hype bar (Refs #1, #2, #3, #11) OR black letterbox trivia header (Ref #4)."""
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    wrapped = textwrap.wrap(headline.upper() if not dark_mode else headline, width=26)[:2]
    if dark_mode:
        f_h = _font(58, bold=True)
        for i, line in enumerate(wrapped):
            _draw_outlined_text(draw, (540, 420 + i * 70), line, f_h, (255, 255, 255), stroke=4)
        if bottom_label:
            _draw_outlined_text(draw, (540, 1345), bottom_label, _font(44, bold=False), (235, 235, 235), stroke=3)
    else:
        # Clean top white hook strip (Refs #1, #2, #11)
        draw.rectangle([0, 0, 1080, 320], fill=(250, 250, 250, 255))
        f_h = _font(56, bold=True)
        y_start = 155 if len(wrapped) == 1 else 120
        for i, line in enumerate(wrapped):
            draw.text((540, y_start + i * 74), line, font=f_h, fill=(18, 18, 18), anchor="mm")
        if bottom_label:
            for i, cline in enumerate(textwrap.wrap(bottom_label.upper(), width=34)[:2]):
                _draw_outlined_text(draw, (540, 1510 + i * 52), cline, _font(36, bold=True), (255, 235, 90), stroke=4)

    if impact_emoji:
        _draw_outlined_text(draw, (540, 960), impact_emoji, _font(110, bold=True), (255, 255, 255), stroke=6)

    _draw_brand_and_credit(img, draw, handle, y_brand=1760, editor_credit=editor_credit)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def _has_audio_stream(video_path: Path) -> bool:
    proc = subprocess.run(
        [FFMPEG.replace("ffmpeg.exe", "ffprobe.exe") if FFMPEG.endswith("ffmpeg.exe") else "ffprobe",
         "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=15,
    )
    return "audio" in (proc.stdout or "")


def _safe_start_offset(video_path: Path, src_dur: float, target_dur: float) -> float:
    """Skips dark fade-in intros (>0.2s black frames at start) so renders pass 0-black-frame QA."""
    if src_dur <= target_dur + 2.5:
        return 0.0
    try:
        proc = subprocess.run(
            [FFMPEG, "-hide_banner", "-t", "5", "-i", str(video_path), "-vf", "blackdetect=d=0.15:pic_th=0.96", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        import re as _re
        m = _re.search(r"black_start:([0-9.]+)\s+black_end:([0-9.]+)", proc.stderr)
        if m and float(m.group(1)) < 0.8:
            return min(float(m.group(2)) + 0.25, src_dur - target_dur - 0.5)
    except Exception:
        pass
    return 1.2 if src_dur > target_dur + 3.0 else 0.0


def render_edit_ranking(
    topic: str,
    clips: list[dict],
    output_mp4: Path,
    handle: str = "@OtakuSnapster",
    clip_dur: float = 12.0,
    shuffled_order: bool = False,
) -> Path:
    """Format 1 (Ref #9 / A5qnBoPq7t4): Dual-layer blurred BG + left ladder (countdown or shuffled 2->4->5->3->1) + 48kHz audio shield.
    Pass clip_dur<=0 to play every clip 100% full & uncut."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    bgm = ensure_royalty_free_bgm("phonk")
    total = len(clips)
    # clips[0] is Rank #1 (highest views); standard plays #N->#1, shuffled plays #2->#4->#5->#3->#1 (Silenthaze retention hook)
    labels = [c.get("short_label") or f"Edit #{i}" for i, c in enumerate(clips, 1)]
    play_order = [r for r in (2, 4, 5, 3, 1) if r <= total] if (shuffled_order and total >= 4) else list(range(total, 0, -1))

    segment_paths = []
    revealed: set[int] = set()
    for rank in play_order:
        revealed.add(rank)
        clip = clips[rank - 1]
        src = Path(clip["local_path"])
        ov = _make_ranking_overlay(
            topic, rank, total, labels, handle, TEMP_DIR / f"rank_ov_{rank}.png",
            editor_credit=clip.get("creator", ""),
            revealed_ranks=set(revealed),
        )
        seg = TEMP_DIR / f"rank_seg_{rank}.mp4"
        src_dur = float(clip.get("duration") or 30.0)
        if clip_dur <= 0:
            # Full uncut edit (skip pure black fade-in <=1.5s, trim trailing 2.5s outro logo/cards)
            ss = _safe_start_offset(src, src_dur, max(1.0, src_dur - 2.0))
            ss = min(ss, 1.5)
            # Cut trailing 2.5s where channel end cards / like-subscribe logos appear
            dur = max(5.0, src_dur - ss - (2.5 if src_dur >= 10.0 else 0.0))
        else:
            dur = min(clip_dur, max(5.0, src_dur - 1.0))
            ss = _safe_start_offset(src, src_dur, dur)

        # Two-stage 48kHz +4% pitch/tempo audio shield + 1.04x video speed/crop disrupts both Audio & Video CID
        has_aud = _has_audio_stream(src)
        if has_aud:
            aud_chain = (
                f"[0:a]aresample=48000,highpass=f=130,asetrate=48000*1.04,atempo=1.0,aresample=48000,"
                f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume=0.90[vox];"
                f"[2:a]volume=0.16,aresample=48000,aformat=channel_layouts=stereo[bed];"
                f"[vox][bed]amix=inputs=2:duration=first:dropout_transition=0.2,"
                f"atrim=0:{dur/1.04:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aresample=48000[aout]"
            )
        else:
            aud_chain = (
                f"[2:a]atrim=0:{dur/1.04:.3f},asetpts=PTS-STARTPTS,"
                f"loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aresample=48000,aformat=channel_layouts=stereo[aout]"
            )

        vf = (
            f"[0:v]trim=0:{dur:.3f},setpts=(PTS-STARTPTS)/1.04,fps=30,split=2[bg0][fg0];"
            f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24,eq=brightness=-0.16[bg];"
            f"[fg0]scale=1134:1008:force_original_aspect_ratio=decrease,crop=iw*0.95:ih*0.95,scale=1080:960:force_original_aspect_ratio=decrease,eq=contrast=1.10:saturation=1.18:gamma=1.03[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
            f"[comp][1:v]overlay=0:0,format=yuv420p[vout]"
        )
        cmd = [
            FFMPEG, "-y",
            "-ss", f"{ss:.2f}", "-i", str(src), "-i", str(ov), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", f"{vf};{aud_chain}",
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{dur/1.04:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(seg),
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=240)
        segment_paths.append(seg)

    return _concat_segments(segment_paths, output_mp4)


def render_release_hype(
    headline: str,
    clips: list[dict],
    output_mp4: Path,
    handle: str = "@OtakuSnapster",
    shot_dur: float = 2.4,
    hook_clip: dict | None = None,
) -> Path:
    """Format 2 (Ref #2 & #1/#3): Optional 3.2s IG/viral edit hook + rapid 2.4s hero cuts + trending no-CID phonk."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    bgm = ensure_royalty_free_bgm("phonk")
    ov_hook = _make_banner_overlay("WAIT FOR THIS...", "WATCH TILL THE END", handle, TEMP_DIR / "hype_hook_ov.png", dark_mode=False)
    ov_normal = _make_banner_overlay(headline, "", handle, TEMP_DIR / "hype_ov.png", dark_mode=False)

    segs = []
    # Prepend 3.2s high-retention visual hook edit (from Instagram / assets/hooks / viral edit)
    if hook_clip and Path(hook_clip["local_path"]).exists():
        h_src = Path(hook_clip["local_path"])
        h_dur_src = float(hook_clip.get("duration") or 8.0)
        h_dur = min(3.2, max(2.2, h_dur_src - 0.5))
        h_ss = min(max(1.5, h_dur_src * 0.25), max(0.0, h_dur_src - h_dur - 0.3)) if h_dur_src > h_dur + 2.0 else 0.0
        h_seg = TEMP_DIR / "hype_hook_seg.mp4"
        vf_h = (
            f"[0:v]trim=0:{h_dur:.3f},setpts=PTS-STARTPTS,fps=30,"
            f"scale=1080:1600:force_original_aspect_ratio=increase,crop=1080:1600,"
            f"eq=contrast=1.16:saturation=1.25[vclip];"
            f"color=c=black:s=1080x1920:d={h_dur:.3f}:r=30[base];"
            f"[base][vclip]overlay=0:320[comp];"
            f"[comp][1:v]overlay=0:0,format=yuv420p[vout]"
        )
        subprocess.run(
            [
                FFMPEG, "-y", "-ss", f"{h_ss:.2f}", "-i", str(h_src), "-i", str(ov_hook),
                "-filter_complex", vf_h, "-map", "[vout]", "-an",
                "-t", f"{h_dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
                str(h_seg),
            ],
            capture_output=True, check=True, timeout=90,
        )
        segs.append(h_seg)

    for idx, clip in enumerate(clips):
        src = Path(clip["local_path"])
        seg = TEMP_DIR / f"hype_seg_{idx}.mp4"
        ov_clip = _make_banner_overlay(headline, "", handle, TEMP_DIR / f"hype_ov_{idx}.png", dark_mode=False, editor_credit=clip.get("creator", ""))
        src_dur = float(clip.get("duration") or shot_dur)
        dur = min(shot_dur, max(1.8, src_dur))
        # Skip studio intro logos (first 4-5s of promos/trailers) and land on hero action midpoint
        ss = min(max(4.5, src_dur * 0.48), max(0.0, src_dur - dur - 0.5)) if src_dur > dur + 5.0 else 0.0
        vf = (
            f"[0:v]trim=0:{dur:.3f},setpts=PTS-STARTPTS,fps=30,"
            f"scale=1080:1600:force_original_aspect_ratio=increase,crop=1080:1600,"
            f"eq=contrast=1.12:saturation=1.20[vclip];"
            f"color=c=black:s=1080x1920:d={dur:.3f}:r=30[base];"
            f"[base][vclip]overlay=0:320[comp];"
            f"[comp][1:v]overlay=0:0,format=yuv420p[vout]"
        )
        cmd = [
            FFMPEG, "-y",
            "-ss", f"{ss:.2f}", "-i", str(src), "-i", str(ov_clip),
            "-filter_complex", vf, "-map", "[vout]", "-an",
            "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
            str(seg),
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=90)
        segs.append(seg)

    silent_concat = TEMP_DIR / "hype_silent.mp4"
    _concat_segments(segs, silent_concat, has_audio=False)
    # Mux trending no-copyright phonk with +2% micro-pitch shield & -14 LUFS mastering
    subprocess.run(
        [
            FFMPEG, "-y", "-i", str(silent_concat), "-stream_loop", "-1", "-ss", "12", "-i", str(bgm),
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            "-af", "aresample=48000,asetrate=48000*1.02,atempo=1/1.02,aresample=48000,loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aformat=channel_layouts=stereo",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(output_mp4),
        ],
        capture_output=True, check=True, timeout=90,
    )
    return output_mp4


def render_movie_trivia_or_commentary(
    headline: str,
    clips: list[dict],
    output_mp4: Path,
    handle: str = "@OtakuSnapster",
    mode: str = "movie_trivia",
) -> Path:
    """Format 3: Ref #4 (black letterbox + 4.5s micro-clips + freeze fact) OR Ref #11 (commentary scene)."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    bgm = ensure_royalty_free_bgm("rock" if mode == "movie_trivia" else "ambient")
    dark_mode = mode == "movie_trivia"

    segs = []
    for idx, clip in enumerate(clips):
        src = Path(clip["local_path"])
        bottom = clip.get("fact_or_commentary") or clip.get("title", "")[:45]
        ov = _make_banner_overlay(headline, bottom, handle, TEMP_DIR / f"triv_ov_{idx}.png", dark_mode=dark_mode, editor_credit=clip.get("creator", ""))
        seg = TEMP_DIR / f"triv_seg_{idx}.mp4"
        src_dur = float(clip.get("duration") or 15.0)
        # Cut trailing 2.2s (creator/out-card/studio logos) so the clip ends cleanly on action dialogue
        usable_src_dur = max(5.0, src_dur - 2.2) if src_dur >= 8.0 else src_dur
        dur = 5.0 if dark_mode else min(usable_src_dur, max(15.0, usable_src_dur))

        # Skip leading black frames/dark fades
        ss = _safe_start_offset(src, src_dur, dur)

        has_aud = _has_audio_stream(src) and not dark_mode
        if has_aud:
            aud = (
                f"[0:a]aresample=48000,highpass=f=110,asetrate=48000*1.03,atempo=1/1.03,aresample=48000,"
                f"aformat=channel_layouts=stereo,volume=0.90[vox];"
                f"[2:a]volume=0.22,aresample=48000,aformat=channel_layouts=stereo[bed];"
                f"[vox][bed]amix=inputs=2:duration=first,atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                f"loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aresample=48000[aout]"
            )
        else:
            aud = (
                f"[2:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,"
                f"loudnorm=I=-14.0:TP=-1.5:LRA=7.0,aresample=48000,aformat=channel_layouts=stereo[aout]"
            )

        vf = (
            f"[0:v]trim=0:{dur:.3f},setpts=PTS-STARTPTS,fps=30,split=2[bg0][fg0];"
            f"[bg0]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=28,eq=brightness=-0.22[bg];"
            f"[fg0]scale=1080:1080:force_original_aspect_ratio=decrease,eq=contrast=1.08:saturation=1.14[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[comp];"
            f"[comp][1:v]overlay=0:0,format=yuv420p[vout]"
        )
        subprocess.run(
            [
                FFMPEG, "-y", "-ss", f"{ss:.2f}", "-i", str(src), "-i", str(ov), "-stream_loop", "-1", "-i", str(bgm),
                "-filter_complex", f"{vf};{aud}", "-map", "[vout]", "-map", "[aout]",
                "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", "30",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(seg),
            ],
            capture_output=True, check=True, timeout=120,
        )
        segs.append(seg)

    return _concat_segments(segs, output_mp4)


def _concat_segments(seg_paths: list[Path], out_mp4: Path, has_audio: bool = True) -> Path:
    list_file = TEMP_DIR / f"concat_{out_mp4.stem}.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in seg_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_mp4)]
    if not has_audio:
        cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:v", "copy", "-an", str(out_mp4)]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)
    return out_mp4
