"""
Reusable Category Editing Skills for the Small Multimodal Model (SML) & LLM Director.
Encodes all production, trimming, framing, font, audio, and QA rules for each of the 4 pillars.
Injected directly into SML/LLM prompts so the model makes category-accurate editorial decisions.
"""

from __future__ import annotations

from typing import Any, Dict

CATEGORY_SKILLS: Dict[str, Dict[str, Any]] = {
    "the_mentalist": {
        "skill_name": "The Mentalist / Patrick Jane Flagship Skill",
        "pillar_day": 3,
        "full_uncut": True,
        "allow_trim": False,
        "trimming_rules": (
            "STRICT ZERO-TRIM RULE: Play every clip 100% FULL & UNCUT from 0.0s to end_sec=duration. "
            "NEVER cut or trim Patrick Jane edits—they rely on psychological dialogue setups, traps, "
            "and deadpan reactions (Jane, Lisbon, Cho, Rigsby, Van Pelt)."
        ),
        "visual_rules": (
            "Auto-crop baked-in black sidebars, 1080x1920 edge-to-edge dual-layer ambient blur, "
            "zero static top banner pills, bold Anton/Impact outlined typography, Krylo countdown ladder."
        ),
        "audio_rules": (
            "100% preserve original dialogue & edit soundtrack (NEVER replace with BGM). "
            "Master with 48kHz +4% anti-CID shield and -14.0 LUFS loudness."
        ),
        "hud_label_examples": ["Jane Mind Trap", "Cho Deadpan", "Red John Reveal", "Jane Cold Smile"],
    },
    "cinema": {
        "skill_name": "Cinema & Blockbuster Edits Skill",
        "pillar_day": 1,
        "full_uncut": False,
        "allow_trim": True,
        "trimming_rules": (
            "AI-DIRECTED PRECISION CUTS: Skip slow studio logos/black fade-ins (start_sec), "
            "capture the full VFX/action climax and beat drop (end_sec), and trim trailing subscribe/outro cards. "
            "No arbitrary 22s cap—let the full climax play out."
        ),
        "visual_rules": (
            "Hook visual must land in first 1.5s. Auto-crop black bars, 1080x1920 edge-to-edge ambient blur, "
            "Rank #3 -> #2 -> #1 escalation."
        ),
        "audio_rules": "Preserve theatrical sound design & bass impact; 48kHz +4% shield, -14.0 LUFS.",
        "hud_label_examples": ["Atomic Breath", "Final Stand", "Hero Entry", "Multiverse Clash"],
    },
    "tv_series": {
        "skill_name": "TV & Web Series Edits Skill",
        "pillar_day": 2,
        "full_uncut": False,
        "allow_trim": True,
        "trimming_rules": (
            "AI-DIRECTED NARRATIVE CUTS: Preserve emotional dialogue build-up, character reaction shots, "
            "and dramatic twist climax. NEVER cut mid-sentence. Trim only dead silence intros and trailing outros."
        ),
        "visual_rules": "1080x1920 edge-to-edge ambient blur, clean Krylo countdown ladder, zero banner boxes.",
        "audio_rules": "Preserve original dialogue and tension score; 48kHz +4% shield, -14.0 LUFS.",
        "hud_label_examples": ["Final Twist", "Cold Betrayal", "Rooftop Save", "Game Over"],
    },
    "song_trends": {
        "skill_name": "Song Trend Edits Skill (Zero Voiceover)",
        "pillar_day": 4,
        "full_uncut": False,
        "allow_trim": True,
        "trimming_rules": (
            "AI-DIRECTED BEAT-SYNC CUTS: Start right before the vocal/bass drop (start_sec), "
            "hold through the full velocity/transition sequence (end_sec), and cut cleanly before silent outros."
        ),
        "visual_rules": "1080x1920 edge-to-edge ambient blur, crisp high-contrast grading, zero banner pills.",
        "audio_rules": "100% preserve the trending song/phonk audio track with 48kHz +4% anti-CID shield and -14.0 LUFS.",
        "hud_label_examples": ["Spider-Verse", "The Weeknd", "Tenet Neil", "Velocity Drop"],
    },
}


def get_skill_for_topic(topic: str, pillar_day: int = 0) -> Dict[str, Any]:
    """Resolves the exact reusable editing skill for the active category or topic."""
    tl = (topic or "").lower()
    if pillar_day == 3 or "mentalist" in tl or "patrick jane" in tl:
        return CATEGORY_SKILLS["the_mentalist"]
    if pillar_day == 4 or any(k in tl for k in ("song", "heartless", "gimme more", "starboy", "audio")):
        return CATEGORY_SKILLS["song_trends"]
    if pillar_day == 2 or any(k in tl for k in ("ep ", "episode", "season", "series", "demon", "squid")):
        return CATEGORY_SKILLS["tv_series"]
    return CATEGORY_SKILLS["cinema"]


def format_skill_prompt_block(topic: str, pillar_day: int = 0) -> str:
    """Formats the category skill into a concise instruction block for the SML / LLM prompt."""
    skill = get_skill_for_topic(topic, pillar_day)
    return (
        f"ACTIVE EDITING SKILL: {skill['skill_name']}\n"
        f"- TRIMMING RULE: {skill['trimming_rules']}\n"
        f"- VISUAL RULE: {skill['visual_rules']}\n"
        f"- AUDIO RULE: {skill['audio_rules']}\n"
        f"- HUD LABEL STYLE (2-3 words, unique per clip): {', '.join(skill['hud_label_examples'])}"
    )
