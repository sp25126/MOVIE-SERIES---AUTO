"""
YouTube Video Analysis & Retention Agent Skills.
Teaches Colab VLM (Qwen2-VL-2B) and Gemini 2.5 Flash how to forensically analyze
YouTube Shorts / Reels / TikTok videos for hook velocity, retention pacing,
beat-sync cut points, framing hygiene, CID/outro risk, and CTR packaging.
"""

from __future__ import annotations

from typing import Dict

YOUTUBE_ANALYSIS_SKILLS: Dict[str, str] = {
    "hook_and_retention": (
        "1. HOOK VELOCITY (0.0s–1.5s): Frame 1 must show immediate character action, high-contrast motion, "
        "or an expressive face. NEVER start on a black fade-in, studio logo, or static text-only title screen. "
        "Advance start_sec past any dead intro."
    ),
    "pacing_and_cut_points": (
        "2. BEAT-SYNC & CLIMAX CUTS: Place start_sec right before the dialogue punchline, beat drop, or action "
        "escalation. Hold end_sec through the full payoff/reaction, and cut BEFORE trailing creator outros, "
        "'Follow/Subscribe' cards, or fade-to-black tails (usually trimming last 1.5s–2.5s if an outro appears)."
    ),
    "framing_and_visual_hygiene": (
        "3. FRAMING & VISUAL HYGIENE: Reject (approved=false) clips that are sideways/rotated, static image "
        "slideshows, heavily watermarked/TikTok-logo-spammed, blurry (<480p), or off-topic (e.g. anime AMV/gaming "
        "clip when topic is live-action cinema/TV)."
    ),
    "audio_and_cid_safety": (
        "4. AUDIO & CONTENT-ID SAFETY: Flag clips with obvious official music-video overlays or lyric-only screens. "
        "Preserve native dialogue and beat-synced edit audio cleanly without mid-sentence cuts."
    ),
    "ctr_labeling_and_ranking": (
        "5. CTR HUD LABELING: Write a punchy, specific 2–3 word scene_label describing the exact visual moment "
        "(e.g. 'Atomic Breath', 'Snap Finale', 'Cho Deadpan', 'Velocity Drop'). NEVER output generic labels like "
        "'Edit #1', 'Viral Moment', or 'Clip 1'."
    ),
}


def get_youtube_analysis_skill_prompt(compact: bool = False) -> str:
    """Returns formatted YouTube video analysis skill instructions for VLM/LLM prompts."""
    if compact:
        return (
            "YOUTUBE ANALYSIS SKILLS:\n"
            "- HOOK: Never start on black fade-in, studio logo, or static text card; set start_sec at first action/face.\n"
            "- CUTS: End before trailing subscribe/follow outro cards or fade-to-black.\n"
            "- REJECT (approved=false): sideways/rotated video, static slideshow, heavy watermark spam, or off-topic gaming/anime.\n"
            "- LABEL: Write a specific 2-3 word scene_label (never 'Edit #1' or 'Viral Moment')."
        )
    return "YOUTUBE VIDEO ANALYSIS AGENT SKILLS:\n" + "\n".join(YOUTUBE_ANALYSIS_SKILLS.values())
