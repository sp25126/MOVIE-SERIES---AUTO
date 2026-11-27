"""
Autonomous 8-Step Virality & Self-Healing Pipeline.
Enforces the Strict 4-Day Rotating Category Pillar Rule:
  Day 1: Cinema Group (12 Genres, dynamic virality score)
  Day 2: TV & Web Series Group (Dynamic Series Discovery)
  Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED FOREVER)
  Day 4: Song Trend Edits (3 rotating subcategories)

8-Step Execution Flow:
  1. Category Choosing (Preserving 4-Day Wheel)
  2. Viral Trend Identification
  3. Candidate Scoring & Topic Selection
  4. Clip Harvesting (Anti-Bot Android Player Extractor)
  5. Multimodal Model Frame Analysis & Cut-Point Scoring (Local VLM or Gemini)
  6. DSP Precision Editing (1080x1920, Dual-Layer Blur, Krylo Ladder, 48kHz Audio)
  7. QA Verification & Model Self-Healing Loop (Diagnose & Auto-Repair Defects)
  8. SEO Title + Viral Trending Hashtags + Credits & Disclaimer + YouTube Canary Scheduling
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CADENCE_STATE_FILE = STATE_DIR / "pipeline_cadence_state.json"
USED_TOPICS_FILE = STATE_DIR / "used_topics.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

CADENCE_NAMES = {
    1: "Cinema Group",
    2: "TV & Web Series Group",
    3: "The Mentalist Series (Locked Pillar)",
    4: "Song Trend Edits (Zero Voiceover)",
}

SONG_SUBCATEGORIES = [
    "one_song_multi_franchise",
    "one_song_single_franchise_multi_edits",
    "one_franchise_multi_song_edits",
]


def load_cadence_state() -> dict:
    if CADENCE_STATE_FILE.exists():
        try:
            return json.loads(CADENCE_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "current_day_index": 1,
        "song_subcat_index": 0,
        "cycle_count": 1,
        "last_run_utc": None,
        "history": [],
    }


def save_cadence_state(state: dict):
    CADENCE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_used_topics() -> dict:
    if USED_TOPICS_FILE.exists():
        try:
            return json.loads(USED_TOPICS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"cinema": [], "tv_series": [], "song_trends": []}


def _pick_fresh_topic(cat_key: str, candidates: list, default_topic: str) -> str:
    """Picks the highest-ranked trending topic not recently used in prior 8h cycles."""
    used = set(t.lower() for t in _load_used_topics().get(cat_key, []))
    for c in candidates:
        name = (c.get("topic") or c.get("series_name") or c.get("song_name") or "").strip()
        if name and name.lower() not in used:
            return name
    return default_topic


def _record_used_topic(cat_key: str, topic: str):
    if not topic or cat_key == "mentalist":
        return
    data = _load_used_topics()
    arr = data.setdefault(cat_key, [])
    if topic not in arr:
        arr.append(topic)
    data[cat_key] = arr[-20:]
    USED_TOPICS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def run_autonomous_workflow(
    day_override: int = 0,
    topic_override: str = "",
    use_local_vlm: bool = False,
    upload: bool = False,
    clip_dur: float = 16.0,
) -> dict:
    state = load_cadence_state()

    # =========================================================================
    # STEP 1: CATEGORY CHOOSING (Enforcing the 4-Day Rotating Wheel)
    # =========================================================================
    curr_day = day_override if day_override in (1, 2, 3, 4) else state.get("current_day_index", 1)
    category_name = CADENCE_NAMES[curr_day]
    logging.info(f"\n=======================================================")
    logging.info(f"📍 STEP 1: CATEGORY SELECTION -> Pillar #{curr_day}: {category_name}")
    logging.info(f"=======================================================")

    # =========================================================================
    # STEP 2 & 3: IDENTIFYING WHAT IS GOING VIRAL & SCORING CANDIDATES
    # =========================================================================
    logging.info(f"🔎 STEP 2 & 3: Identifying & Scoring Live Virality Candidates...")
    chosen_topic = topic_override.strip()
    chosen_genre = "action_thriller"

    if not chosen_topic:
        if curr_day == 3:
            # Strictly locked flagship pillar: The Mentalist
            chosen_topic = "The Mentalist"
            chosen_genre = "crime_mystery"
            logging.info(f"🔒 [Pillar 3 Locked] Topic: '{chosen_topic}'")
        else:
            logging.info("🔥 [Virality Engine] Executing live 360° virality scan across Reddit, YouTube, and news...")
            try:
                import virality_engine
                digest = virality_engine.run_all_category_virality_scan(force_fresh_yt=True)
            except Exception as e:
                logging.warning(f"Live virality scan exception ({e}); reading cached daily digest...")
                digest_file = STATE_DIR / "daily_virality_digest.json"
                digest = json.loads(digest_file.read_text(encoding="utf-8")) if digest_file.exists() else {}

            cats = digest.get("categories", {})
            if curr_day == 1:
                cinema_cat = cats.get("cinema", {})
                chosen_topic = _pick_fresh_topic("cinema", cinema_cat.get("top_candidates", []), cinema_cat.get("lead_winner"))
                chosen_genre = cinema_cat.get("lead_genre", "action_thriller")
                _record_used_topic("cinema", chosen_topic)
                logging.info(f"🎬 Dynamic Cinema Winner (Fresh): '{chosen_topic}' (Score: {cinema_cat.get('lead_score')})")
            elif curr_day == 2:
                tv_cat = cats.get("tv_series", {})
                chosen_topic = _pick_fresh_topic("tv_series", tv_cat.get("top_candidates", []), tv_cat.get("lead_winner"))
                chosen_genre = "tv_thriller"
                _record_used_topic("tv_series", chosen_topic)
                logging.info(f"📺 Dynamic TV Series Winner (Fresh): '{chosen_topic}' ({tv_cat.get('lead_views', 0):,} views)")
            elif curr_day == 4:
                sub_idx = state.get("song_subcat_index", 0) % len(SONG_SUBCATEGORIES)
                current_subcat = SONG_SUBCATEGORIES[sub_idx]
                song_cat = cats.get("song_trends", {})
                chosen_topic = _pick_fresh_topic("song_trends", song_cat.get("top_candidates", []), song_cat.get("lead_winner"))
                chosen_genre = "song_trends"
                _record_used_topic("song_trends", chosen_topic)
                logging.info(f"🎵 Dynamic Song Trends Winner (Fresh): '{chosen_topic}' (Subcategory: {current_subcat})")

    if not chosen_topic:
        raise RuntimeError("Virality Engine failed to discover a live winner. Ensure network access is available.")

    logging.info(f"🏆 Winning Topic: '{chosen_topic}' (Genre: {chosen_genre})")

    # =========================================================================
    # STEP 4: MULTI-PLATFORM CLIP HARVESTING (YouTube + Instagram + TikTok)
    # =========================================================================
    logging.info(f"📥 STEP 4: Harvesting Clips across YouTube, Instagram & TikTok for '{chosen_topic}'...")
    from clip_harvester import scout_youtube, scout_instagram_reels, scout_tiktok_videos, download_clip

    query = f"{chosen_topic} edit shorts" if curr_day != 4 else f"{chosen_topic} audio edit shorts"
    raw_candidates = []

    # 1. Scout YouTube (keep ignore_history=False so clips are NEVER duplicated across 8h cycles)
    is_mentalist = (curr_day == 3) or ("mentalist" in chosen_topic.lower()) or ("patrick jane" in chosen_topic.lower())
    yt_cands = scout_youtube(query, count=4, ignore_history=False, strict_edit_filter=not is_mentalist)
    if len(yt_cands) < 2:
        alt_query = "Patrick Jane edit #shorts" if is_mentalist else f"{chosen_topic} viral edit shorts"
        yt_cands.extend(scout_youtube(alt_query, count=4, ignore_history=False, strict_edit_filter=not is_mentalist))
    raw_candidates.extend(yt_cands)

    # 2. Scout Instagram Reels
    ig_query = "Patrick Jane" if is_mentalist else chosen_topic
    try:
        ig_cands = scout_instagram_reels(ig_query, count=3, ignore_history=False)
        logging.info(f"  📸 Instagram Reels scouted: {len(ig_cands)}")
        raw_candidates.extend(ig_cands)
    except Exception as e:
        logging.warning(f"  Instagram scout skipped: {e}")

    # 3. Scout TikTok
    try:
        tt_cands = scout_tiktok_videos(ig_query, count=3, ignore_history=False)
        logging.info(f"  🎵 TikTok scouted: {len(tt_cands)}")
        raw_candidates.extend(tt_cands)
    except Exception as e:
        logging.warning(f"  TikTok scout skipped: {e}")

    # Interleave platforms so we get diverse edits from IG, TikTok & YouTube
    by_plat = {"instagram": [], "tiktok": [], "youtube": []}
    for c in raw_candidates:
        by_plat.setdefault(c.get("platform", "youtube"), []).append(c)
    interleaved = []
    for i in range(max((len(v) for v in by_plat.values()), default=0)):
        for p_name in ("instagram", "tiktok", "youtube"):
            if i < len(by_plat.get(p_name, [])):
                interleaved.append(by_plat[p_name][i])

    logging.info(f"Scouted {len(interleaved)} multi-platform candidates (IG={len(by_plat['instagram'])}, TT={len(by_plat['tiktok'])}, YT={len(by_plat['youtube'])}). Downloading...")
    input_dir = ROOT / "input"
    input_dir.mkdir(exist_ok=True)
    downloaded = []
    for cand in interleaved[:8]:
        p = download_clip(cand, out_dir=input_dir)
        if p and p.exists() and p.stat().st_size > 20_000:
            cand["local_path"] = str(p)
            downloaded.append(cand)
            logging.info(f"  ✓ Downloaded ({cand.get('platform')}): {cand['title'][:40]} ({p.stat().st_size / 1e6:.1f}MB)")
        else:
            logging.warning(f"  ✗ Failed ({cand.get('platform')}): {cand.get('title', '')[:40]} ({cand.get('url')})")
        if len(downloaded) >= 4:
            break

    if len(downloaded) < 2:
        logging.warning(f"YouTube yielded {len(downloaded)} clips; trying Reddit fallback for '{chosen_topic}'...")
        try:
            from clip_harvester import scout_reddit_memes_and_clips
            reddit_cands = scout_reddit_memes_and_clips(topic=chosen_topic, count=6, video_only=True)
            for cand in reddit_cands:
                p = download_clip(cand, out_dir=input_dir)
                if p and p.exists() and p.stat().st_size > 20_000:
                    cand["local_path"] = str(p)
                    downloaded.append(cand)
                    logging.info(f"  ✓ Downloaded (Reddit): {cand['title'][:40]} ({p.stat().st_size / 1e6:.1f}MB)")
                if len(downloaded) >= 3:
                    break
        except Exception as re_err:
            logging.warning(f"Reddit fallback failed: {re_err}")

    if len(downloaded) < 2:
        raise RuntimeError(f"Starvation: Not enough valid clips downloaded for '{chosen_topic}'.")

    # =========================================================================
    # STEP 5: MODEL VISUAL INSPECTION, BEAT-DROP & CUT-POINT SCORING
    # =========================================================================
    logging.info(f"🧠 STEP 5: Model Vision Inspection on Sequential Timeline Frames...")
    import llm_director

    curated_clips = llm_director.curate_and_rank_clips(
        candidates=downloaded,
        topic=chosen_topic,
        target_count=3,
        use_local_model=use_local_vlm,
        pillar_day=curr_day,
    )

    if not curated_clips:
        raise RuntimeError("No candidate clips approved by AI vision filter.")

    logging.info("\n--- AI EDITORIAL RANKING REPORT ---")
    for i, c in enumerate(curated_clips, 1):
        cut = c.get("optimal_cut", {})
        logging.info(
            f"Rank #{i}: {c.get('title')[:35]} | Score: {c.get('quality_score')}/10 | "
            f"Label: '{c.get('short_label')}' | Cut: {cut.get('start_sec', 0.0)}s -> {cut.get('end_sec', 0.0)}s"
        )

    # =========================================================================
    # STEP 6: DSP PRECISION EDITING (Enforcing Patrick Jane Trimming Rules)
    # =========================================================================
    logging.info(f"🎬 STEP 6: DSP Master Rendering...")
    import dsp_renderer
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    slug = "".join(ch for ch in chosen_topic.lower() if ch.isalnum())
    out_mp4 = output_dir / f"{slug}_master_short.mp4"

    # Enforce Patrick Jane Category Rules:
    # 1. Full Uncut Rule: Never truncate dialogue/mind-games arbitrarily; play full clip.
    # 2. Skip initial black fade-in (<=1.5s) to guarantee zero black frames.
    # 3. Trim trailing 2.5s outro cards/logos.
    # 4. Zero BGM clashing (preserve original dialogue 100%).
    is_patrick_jane = is_mentalist

    if is_patrick_jane:
        logging.info("🔒 [Patrick Jane Trimming Rules Enforced] Mode=Full Uncut (Dialogue preserved, dark fade-in skipped, outro trimmed).")
        effective_clip_dur = 0.0 # Full uncut mode!
        full_uncut_flag = True
    elif clip_dur <= 0:
        logging.info("🧠 [AI Decision Mode] AI Vision Model optimal cut points dictate clip durations.")
        effective_clip_dur = 0.0
        full_uncut_flag = False
    else:
        effective_clip_dur = clip_dur
        full_uncut_flag = False

    dsp_renderer.render_edit_ranking(
        topic=chosen_topic,
        clips=curated_clips,
        output_mp4=out_mp4,
        clip_dur=effective_clip_dur,
        genre=chosen_genre,
        full_uncut=full_uncut_flag,
    )
    logging.info(f"Render completed: {out_mp4} ({out_mp4.stat().st_size / 1e6:.2f} MB)")

    # =========================================================================
    # STEP 7: QA RECHECKING & MODEL SELF-HEALING LOOP
    # =========================================================================
    logging.info(f"🔍 STEP 7: QA Verification & Model Self-Healing...")
    import qa_gate
    qa_res = qa_gate.verify_video(out_mp4)
    passed = qa_res.get("passed", False)
    issues = qa_res.get("issues", [])

    if not passed or issues:
        logging.warning(f"⚠️ QA Gate flagged issues: {issues}. Triggering AI Self-Healing Loop...")
        repair = llm_director.diagnose_and_repair_defect(
            qa_issues=issues,
            video_path=out_mp4,
            clips=curated_clips,
            topic=chosen_topic,
        )
        logging.info(f"🔧 Model Repair Decision: {repair['diagnosis_summary']}")
        adjusted_dur = max(10.0, clip_dur + repair.get("clip_dur_adjustment", 0.0))

        # Re-render with repair parameters
        dsp_renderer.render_edit_ranking(
            topic=chosen_topic,
            clips=curated_clips,
            output_mp4=out_mp4,
            clip_dur=adjusted_dur,
            genre=chosen_genre,
        )
        qa_res_2 = qa_gate.verify_video(out_mp4)
        logging.info(f"✅ Post-Repair QA Result: passed={qa_res_2.get('passed', False)}, issues={qa_res_2.get('issues', [])}")
    else:
        logging.info("✅ QA Gate PASSED on first pass (0 black frames, 1080x1920, 48kHz audio sync).")

    # =========================================================================
    # STEP 8: SEO TITLE + VIRAL HASHTAGS + CREDITS + SCHEDULING
    # =========================================================================
    logging.info(f"📝 STEP 8: Generating SEO Metadata & Unrelated Trending Hashtags Cloud...")
    import metadata_uploader
    meta = metadata_uploader.build_metadata(
        topic=chosen_topic,
        fmt="edit_ranking",
        clips=curated_clips,
        genre=chosen_genre,
    )

    logging.info(f"\n--- GENERATED PUBLISHING METADATA ---")
    logging.info(f"Title: {meta['title']}")
    logging.info(f"Slot:  {meta['recommended_slot_utc']}")
    logging.info(f"Tags:  {meta['tags']}")

    # Persist companion metadata JSON alongside the rendered MP4
    meta_out = output_dir / f"{slug}_metadata.json"
    meta_out.write_text(json.dumps({
        "pillar_day": curr_day,
        "category": category_name,
        "topic": chosen_topic,
        "genre": chosen_genre,
        "video_path": str(out_mp4),
        **meta,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"Saved metadata JSON: {meta_out}")

    upload_result = {}
    if upload:
        logging.info("\n🚀 Uploading private canary & scheduling to YouTube Studio...")
        upload_result = metadata_uploader.upload_private_canary_and_schedule(
            video_path=out_mp4,
            meta=meta,
            canary_wait_sec=90,
        )
        logging.info(f"✅ Live Scheduled Link: https://youtube.com/shorts/{upload_result.get('video_id')}")

        # Advance 4-day rotating category wheel ONLY upon successful production/upload
        state["current_day_index"] = (curr_day % 4) + 1
        if curr_day == 4:
            state["song_subcat_index"] = (state.get("song_subcat_index", 0) + 1) % len(SONG_SUBCATEGORIES)
        state["last_run_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        state["history"].append({
            "timestamp_utc": state["last_run_utc"],
            "day": curr_day,
            "category": category_name,
            "topic": chosen_topic,
            "video_id": upload_result.get("video_id"),
            "result": "success",
        })
        save_cadence_state(state)
        logging.info(f"🎡 Advanced Rotating Wheel to Pillar #{state['current_day_index']}: {CADENCE_NAMES[state['current_day_index']]}")

    return {
        "status": "success",
        "pillar_day": curr_day,
        "category": category_name,
        "topic": chosen_topic,
        "output_mp4": str(out_mp4),
        "metadata_json": str(meta_out),
        "metadata": meta,
        "qa_result": qa_res,
        "upload_result": upload_result,
    }


def run_full_category_cycle(
    use_local_vlm: bool = False,
    upload: bool = False,
    clip_dur: float = 0.0,
    start_day: int = 1,
) -> list[dict]:
    """Runs all 4 Category Pillars sequentially (Cinema -> TV Series -> The Mentalist -> Song Trends)."""
    day_order = [((start_day - 1 + i) % 4) + 1 for i in range(4)]
    results = []
    logging.info(f"\n🎡 STARTING FULL 4-CATEGORY CYCLE: {day_order}")
    for d in day_order:
        cat_name = CADENCE_NAMES[d]
        logging.info(f"\n{'#'*60}\n▶ CYCLE STEP: Pillar #{d} — {cat_name}\n{'#'*60}")
        try:
            res = run_autonomous_workflow(
                day_override=d,
                topic_override="",
                use_local_vlm=use_local_vlm,
                upload=upload,
                clip_dur=clip_dur,
            )
            results.append(res)
        except Exception as e:
            logging.error(f"✗ Pillar #{d} ({cat_name}) failed: {e}")
            results.append({
                "status": "failed",
                "pillar_day": d,
                "category": cat_name,
                "error": str(e),
            })
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous 8-Step Virality & Self-Healing Pipeline")
    parser.add_argument("--day", type=int, default=0, help="Day override (1=Cinema, 2=TV Series, 3=The Mentalist, 4=Song Edits)")
    parser.add_argument("--topic", type=str, default="", help="Topic override (or blank for auto-virality)")
    parser.add_argument("--local-vlm", action="store_true", help="Use local small VLM (Ollama) instead of Gemini API")
    parser.add_argument("--upload", action="store_true", help="Upload private canary & schedule to YouTube")
    parser.add_argument("--clip-dur", type=float, default=0.0, help="Target duration per clip in seconds (0=AI decides)")
    parser.add_argument("--full-cycle", action="store_true", help="Run all 4 categories one after another")
    args = parser.parse_args()

    if args.full_cycle:
        run_full_category_cycle(
            use_local_vlm=args.local_vlm,
            upload=args.upload,
            clip_dur=args.clip_dur,
            start_day=args.day if args.day in (1, 2, 3, 4) else 1,
        )
    else:
        run_autonomous_workflow(
            day_override=args.day,
            topic_override=args.topic,
            use_local_vlm=args.local_vlm,
            upload=args.upload,
            clip_dur=args.clip_dur,
        )
