"""
Reusable Category Editing Skills & Forensic Production Specifications for the Video Editing Model.
Encodes exact pacing curves, cut-point specs, safe zones, audio rules, and rejection criteria
for each of the 4 publishing pillars, injected directly into Qwen2.5-VL-3B / Gemini prompts.
"""

from __future__ import annotations

from typing import Any, Dict

SHORTS_SAFE_ZONES = (
    "SAFE ZONES (1080x1920): Header inside y=60..220; Left countdown ladder inside x=44..340; "
    "Right engagement column x=950..1080 clear; Bottom creator credit above y=1580 (clears Shorts title/audio pill)."
)

CATEGORY_SKILLS: Dict[str, Dict[str, Any]] = {
    "the_mentalist": {
        "skill_name": "The Mentalist / Patrick Jane Flagship Spec (LOCKED)",
        "pillar_day": 3,
        "full_uncut": True,
        "allow_trim": False,
        "pacing_curve": "Full uncut psychological arcs (25-58s per edit, <180s total); highest-view edit plays LAST (#1).",
        "trimming_rules": (
            "STRICT ZERO-TRIM SPEC: Set start_sec=0.0 and end_sec=duration. NEVER cut or trim Patrick Jane edits—"
            "they rely on full dialogue setups, cold-reading traps, and deadpan reactions "
            "(Patrick Jane, Teresa Lisbon, Kimball Cho, Wayne Rigsby, Grace Van Pelt, Red John)."
        ),
        "visual_rules": (
            "True 9:16 full-bleed for vertical clips; dual-layer Gaussian blur for 16:9 with auto-cropped black bars. "
            "Zero static top banner pills; progressive left ladder (#3 -> #2 -> #1)."
        ),
        "audio_rules": (
            "100% preserve original dialogue & edit soundtrack (NEVER override with BGM). "
            "Master with 48kHz +4% Anti-CID shield and -14.0 LUFS loudness."
        ),
        "rejection_criteria": "Reject sideways/rotated clips, heavy watermark spam, raw unedited promo clips, or static quote cards.",
        "text_spec": (
            "HEADER: Stacked Impact/Anton font (6px black stroke), Line 1='Ranking' (White) + 'Best' (Neon Green #39FF14), "
            "Line 2='The Mentalist Edits' (Cyan #00E5FF). LADDER (x=44, y=640): Progressive '3. <2-Word Tag> (<Views>)' -> '1.' "
            "(Active colors: #1 Red, #2 Cyan, #3 Gold). CREDIT (y=1561): 'Edit Credit: <Creator>' below circular @OtakuSnapster badge."
        ),
        "hud_label_examples": ["Jane Mind Trap", "Cho Deadpan", "Red John Reveal", "Jane Cold Smile"],
    },
    "cinema": {
        "skill_name": "Cinema & Blockbuster Edits Spec (12 Genres)",
        "pillar_day": 1,
        "full_uncut": False,
        "allow_trim": True,
        "pacing_curve": "Variable escalating pacing: #3 punchy (8-10s) -> #2 build-up (10-12s) -> #1 full climax (12-16s).",
        "trimming_rules": (
            "PRECISION CLIMAX CUT SPEC: Advance start_sec PAST any black fade-in, studio logo, or static text card "
            "(lock onto first high-motion VFX/character entrance within 0.5s-2.5s). Hold end_sec through the full "
            "climax/beat-drop, and cut BEFORE trailing subscribe/follow/outro cards (trim last 1.5s-2.5s if outro appears)."
        ),
        "visual_rules": (
            "Hook visual must land in <1.0s. True 9:16 full-bleed for vertical edits; dual-layer blur + mid-action "
            "black-bar crop for 16:9. Apply 1.04x speed + subtle contrast/saturation boost."
        ),
        "audio_rules": "Preserve theatrical sound design & bass impact; 48kHz +4% Anti-CID shield, -14.0 LUFS.",
        "rejection_criteria": "Reject fake AI/concept trailers (Sora/Kling/Screen Culture), static slideshows, sideways video, or anime AMVs on live-action topics.",
        "text_spec": (
            "HEADER: Impact/Anton 6px black stroke — for edit_ranking: 'Ranking Best <Topic> Edits' (White/Neon Green/Cyan); "
            "for scene_commentary/trivia: bold 2-4 word hook line (Yellow #FFE600 + White, no boxy pill). "
            "LADDER (x=44): 2-word action/VFX tag + view count. CREDIT (y=1561): 'Edit Credit: <Creator>'."
        ),
        "hud_label_examples": ["Atomic Breath", "Final Stand", "Hero Entry", "Multiverse Clash"],
    },
    "tv_series": {
        "skill_name": "TV & Web Series Edits Spec",
        "pillar_day": 2,
        "full_uncut": False,
        "allow_trim": True,
        "pacing_curve": "Narrative escalation: #3 (9-12s) -> #2 (11-14s) -> #1 (13-18s emotional/twist climax).",
        "trimming_rules": (
            "NARRATIVE ARC CUT SPEC: Preserve emotional dialogue build-up, character reaction shots, and the dramatic "
            "twist climax. NEVER cut mid-sentence. Set start_sec past dead-silence/black intros and end_sec before "
            "trailing creator outro/watermark cards."
        ),
        "visual_rules": (
            "True 9:16 full-bleed for vertical clips; dual-layer blur + black-bar crop for 16:9. "
            "Clean left countdown ladder, zero boxy banner clutter."
        ),
        "audio_rules": "Preserve original dialogue and tension score; 48kHz +4% Anti-CID shield, -14.0 LUFS.",
        "rejection_criteria": "Reject raw unedited episode clips without edit pacing, recap voiceovers, static slides, or sideways video.",
        "text_spec": (
            "HEADER: Impact/Anton 6px black stroke ('Ranking Best <Series> Edits' or 'Everyone Missed This in <Series>'). "
            "LADDER (x=44): 2-word character/twist tag (never generic 'Edit #1'). "
            "CAPTIONS/CREDITS: Keep bottom text above y=1580; 'Edit Credit: <Creator>' cleanly below @OtakuSnapster."
        ),
        "hud_label_examples": ["Final Twist", "Cold Betrayal", "Rooftop Save", "Game Over"],
    },
    "song_trends": {
        "skill_name": "Song Trend Edits Spec (Zero Voiceover, 3 Subcategories)",
        "pillar_day": 4,
        "full_uncut": False,
        "allow_trim": True,
        "pacing_curve": "Fast beat-synced escalation: #3 (6-7s) -> #2 (7-9s) -> #1 (8-11s) with 0.2s loop-bridge fade.",
        "trimming_rules": (
            "BEAT-SYNC CUT SPEC: Skip any black/static intro title or lyric card (start_sec right before the vocal/bass drop "
            "or first velocity cut). Hold through the full velocity/transition sequence, and cut end_sec cleanly before "
            "silent outros or creator end cards."
        ),
        "visual_rules": (
            "True 9:16 full-bleed for vertical edits; 1080x1440 foreground + Gaussian blur for 16:9/1:1. "
            "Clean stroked header typography, metallic #3/#2/#1 rank badges, 1.03x speed."
        ),
        "audio_rules": "ZERO VOICEOVER. 100% preserve trending song/phonk audio with 48kHz +3% Anti-CID shield, smooth afade transitions, and -14.0 LUFS.",
        "rejection_criteria": "Reject Roblox/Free Fire/gaming edits, static lyric-only images, heavy TikTok watermark spam, or low-effort status clips.",
        "text_spec": (
            "HEADER (y=110..168): Clean stroked uppercase Impact/Arial-Bold (NO boxy border), Line 1 White + Line 2 Gold (#FFD700), "
            "matching subcategory ('RANKING THE BEST <SONG> TREND EDITS' or '<FRANCHISE> <SONG> EDITS'). "
            "RANK BADGE (x=70, y=270): Metallic '#1' Gold / '#2' Silver / '#3' Bronze pill + '<Views> VIEWS' sub-pill. "
            "CREDIT (y=1580): 'EDIT BY @CREATOR' pill. ZERO voiceover/lyric captions."
        ),
        "hud_label_examples": ["Spider-Verse", "The Weeknd", "Tenet Neil", "Velocity Drop"],
    },
}


def get_skill_for_topic(topic: str, pillar_day: int = 0) -> Dict[str, Any]:
    """Resolves the exact reusable editing specification for the active category or topic."""
    tl = (topic or "").lower()
    if pillar_day == 3 or "mentalist" in tl or "patrick jane" in tl:
        return CATEGORY_SKILLS["the_mentalist"]
    if pillar_day == 4 or any(k in tl for k in ("song", "heartless", "gimme more", "starboy", "audio")):
        return CATEGORY_SKILLS["song_trends"]
    if pillar_day == 2 or any(k in tl for k in ("ep ", "episode", "season", "series", "demon", "squid")):
        return CATEGORY_SKILLS["tv_series"]
    return CATEGORY_SKILLS["cinema"]


def format_skill_prompt_block(topic: str, pillar_day: int = 0) -> str:
    """Formats the category editing specification into a structured prompt block for the VLM."""
    skill = get_skill_for_topic(topic, pillar_day)
    return (
        f"ACTIVE EDITING SPECIFICATION: {skill['skill_name']}\n"
        f"- PACING CURVE: {skill['pacing_curve']}\n"
        f"- TRIMMING SPEC: {skill['trimming_rules']}\n"
        f"- VISUAL SPEC: {skill['visual_rules']} {SHORTS_SAFE_ZONES}\n"
        f"- AUDIO SPEC: {skill['audio_rules']}\n"
        f"- TEXT & TYPOGRAPHY SPEC: {skill['text_spec']}\n"
        f"- REJECTION CRITERIA: {skill['rejection_criteria']}\n"
        f"- HUD LABEL STYLE (2-3 words, unique per clip): {', '.join(skill['hud_label_examples'])}"
    )
