"""
AI Video Quality and Entity Assurance Verifier.
Empowered with Google Gemini 2.5 Flash multimodal vision intelligence.
Engineered to top 1% prompt engineering and elite automation standards.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"


@dataclass
class AIVerificationResult:
    approved: bool
    confidence: float
    matched_entity: str
    is_live_action: bool
    is_anime_or_cartoon: bool
    is_low_effort_slideshow: bool
    has_watermark_spam: bool
    reasoning: str
    rejection_flags: List[str]


class AIVerifier:
    """
    Multimodal AI quality verification gatekeeper.
    Performs forensic inspection of extracted video frames to eliminate false entities,
    cross-genre contamination (anime in movie edits), static slideshows, and spam.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        if not self.api_key:
            logger.warning("[AI Verifier] GEMINI_API_KEY missing. Verification gatekeeper disabled.")

    @property
    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def extract_temporal_checkpoints(
        self,
        video_path: Path | str,
        duration: float,
        ratios: tuple = (0.15, 0.45, 0.75, 0.95),
    ) -> List[Path]:
        """
        Samples forensic checkpoint frames across the video timeline.
        15% (Hook/Opening), 45% (Mid-action), 75% (Climax), 95% (Outro/Endcard).
        """
        video_path = Path(video_path)
        temp_dir = video_path.parent / "_ai_verification_cache"
        temp_dir.mkdir(parents=True, exist_ok=True)
        frame_paths = []

        dur = max(duration, 3.0)
        for i, ratio in enumerate(ratios):
            target_time = max(0.2, min(dur * ratio, dur - 0.5))
            out_file = temp_dir / f"{video_path.stem}_chk_{i}_{int(target_time * 1000)}ms.jpg"

            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{target_time:.3f}",
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-vf",
                "scale=640:-1",
                "-q:v",
                "3",
                str(out_file),
            ]
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if out_file.exists() and out_file.stat().st_size > 1024:
                    frame_paths.append(out_file)
            except Exception as e:
                logger.debug(f"[AI Verifier] Frame extraction failed at {target_time:.2f}s: {e}")

        return frame_paths

    def verify_clip(
        self,
        video_path: Path,
        expected_topic: str,
        niche_context: str = "Live-Action Movies, Series & Cinema",
        duration: float = 30.0,
    ) -> AIVerificationResult:
        """
        Executes zero-tolerance multimodal validation against senior editorial prompt rubrics.
        """
        if not self.is_enabled:
            return AIVerificationResult(
                approved=True,
                confidence=1.0,
                matched_entity=expected_topic,
                is_live_action=True,
                is_anime_or_cartoon=False,
                is_low_effort_slideshow=False,
                has_watermark_spam=False,
                reasoning="Bypassed: GEMINI_API_KEY not configured.",
                rejection_flags=[],
            )

        frames = self.extract_temporal_checkpoints(video_path, duration)
        if not frames:
            logger.warning(f"[AI Verifier] Could not extract frames for {video_path.name}; defaulting to reject.")
            return AIVerificationResult(
                approved=False,
                confidence=0.0,
                matched_entity="Unknown",
                is_live_action=False,
                is_anime_or_cartoon=False,
                is_low_effort_slideshow=False,
                has_watermark_spam=False,
                reasoning="Frame extraction failed completely.",
                rejection_flags=["EXTRACTION_FAILED"],
            )

        try:
            # Build Multimodal Gemini Payload
            parts: List[Dict[str, Any]] = []

            # 1. System Prompt & Instruction
            system_instruction = f"""
You are the Executive Lead Quality Gatekeeper and Senior Content Strategist for @OtakuSnapster, a premier YouTube Shorts channel delivering elite, high-octane 9:16 edits in the '{niche_context}' niche.

CRITICAL ASSIGNMENT:
Verify whether the inspected video frames legitimately belong to the expected topic: '{expected_topic}'.

STRICT QA RUBRIC & REJECTION CRITERIA:
1. ENTITY ACCURACY:
   - Must authentically portray or feature: '{expected_topic}'.
   - Disqualify false-positives, lyrical music videos with unrelated celebrities, or unrelated movie clips mislabeled as this topic.

2. GENRE CONSTRAINTS (ZERO TOLERANCE FOR CROSS-GENRE POLLUTION):
   - If expected topic is Live-Action Cinema / Series (e.g. John Wick, Robert Downey Jr, Chris Pratt, Peaky Blinders, Breaking Bad, James Bond):
     * REJECT IMMEDIATELY if frames depict 2D/3D Anime (e.g. Jujutsu Kaisen, Dragon Ball, Naruto, Attack on Titan).
     * REJECT IMMEDIATELY if frames depict cartoon or animated characters unless the topic explicitly specifies animated cinema.

3. EDITORIAL INTEGRITY:
   - REJECT low-effort static picture slideshows with simple pan/zoom effects.
   - REJECT videos covered with massive spam watermarks, channel promos covering >40% screen, or full-screen lyrical karaoke bars.
   - Genuine high-effort cinema fan edits, velocity cuts, colour-graded scenes, and cinematographic montages MUST PASS.

OUTPUT FORMAT REQUIREMENTS:
You MUST respond with pure JSON only matching this schema (no markdown formatting, no backticks, no markdown fence):
{{
  "approved": boolean,
  "confidence": float (0.0 to 1.0),
  "detected_entities": ["string", "string"],
  "is_live_action": boolean,
  "is_anime_or_cartoon": boolean,
  "is_low_effort_slideshow": boolean,
  "has_watermark_spam": boolean,
  "rejection_flags": ["string"],
  "brief_reasoning": "string"
}}
"""
            parts.append({"text": system_instruction.strip()})

            # 2. Attach Base64 Frames
            for i, fp in enumerate(frames):
                with open(fp, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                parts.append({"text": f"--- INSPECTION FRAME {i + 1} (Checkpoint {fp.stem}) ---"})
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": b64_data,
                    }
                })

            req_body = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            }

            url = f"{GEMINI_API_URL}?key={self.api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(req_body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:
                raw_json = json.loads(resp.read().decode("utf-8"))

            candidates = raw_json.get("candidates", [])
            if not candidates:
                raise ValueError("Empty candidate list returned by Gemini.")

            text_resp = candidates[0]["content"]["parts"][0]["text"].strip()
            # Clean possible markdown wrapper if model injected it
            clean_json = re.sub(r"^```json\s*", "", text_resp)
            clean_json = re.sub(r"\s*```$", "", clean_json).strip()

            parsed = json.loads(clean_json)

            approved = bool(parsed.get("approved", False))
            confidence = float(parsed.get("confidence", 0.0))
            is_anime = bool(parsed.get("is_anime_or_cartoon", False))
            is_slideshow = bool(parsed.get("is_low_effort_slideshow", False))
            rejection_flags = parsed.get("rejection_flags", [])

            # Hard safety override: If anime detected when live action expected, force rejection
            if "Live-Action" in niche_context and is_anime:
                approved = False
                if "CROSS_GENRE_ANIME" not in rejection_flags:
                    rejection_flags.append("CROSS_GENRE_ANIME")

            # Hard safety override: Confidence threshold < 0.70
            if confidence < 0.70:
                approved = False
                if "LOW_CONFIDENCE" not in rejection_flags:
                    rejection_flags.append("LOW_CONFIDENCE")

            detected_entities = ", ".join(parsed.get("detected_entities", [])) or "None"

            return AIVerificationResult(
                approved=approved,
                confidence=confidence,
                matched_entity=detected_entities,
                is_live_action=bool(parsed.get("is_live_action", True)),
                is_anime_or_cartoon=is_anime,
                is_low_effort_slideshow=is_slideshow,
                has_watermark_spam=bool(parsed.get("has_watermark_spam", False)),
                reasoning=parsed.get("brief_reasoning", "No detail provided."),
                rejection_flags=rejection_flags,
            )

        except Exception as e:
            logger.error(f"[AI Verifier] Gemini verification failed: {e}")
            # Resilient fallback: approve if network error to avoid freezing headless automation, but flag warning
            return AIVerificationResult(
                approved=True,
                confidence=0.5,
                matched_entity=expected_topic,
                is_live_action=True,
                is_anime_or_cartoon=False,
                is_low_effort_slideshow=False,
                has_watermark_spam=False,
                reasoning=f"Fallback bypassed due to API error: {str(e)}",
                rejection_flags=["API_ERROR_FALLBACK"],
            )
        finally:
            # Clean up frame cache to preserve disk space
            for fp in frames:
                try:
                    if fp.exists():
                        fp.unlink()
                except Exception:
                    pass


# Singleton instance for pipeline integration
ai_verifier = AIVerifier()


def verify_clip_with_gemini(
    video_path: Path | str,
    required_topic: str,
    duration: float = 30.0,
    niche_context: str = "Live-Action Movies, Series & Cinema",
) -> tuple[bool, str]:
    """
    Standard entrypoint helper for clip harvesting and QA pipelines.
    Returns (is_approved, explanation).
    """
    res = ai_verifier.verify_clip(
        video_path=Path(video_path),
        expected_topic=required_topic,
        niche_context=niche_context,
        duration=duration,
    )
    if not res.approved:
        return False, f"Flags={res.rejection_flags} | {res.reasoning}"
    return True, res.reasoning
