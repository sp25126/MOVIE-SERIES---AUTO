"""
Autonomous 8-Step Virality & Self-Healing Pipeline.
Enforces the Strict 4-Day Rotating Category Pillar Rule:
  Day 1: Cinema Group (12 Genres, dynamic virality score + format routing + LLM preemption)
  Day 2: TV & Web Series Group (Dynamic Series Discovery + multi-candidate cascade)
  Day 3: The Mentalist Flagship Pillar (STRICTLY LOCKED FOREVER — patrick_jane_series.json)
  Day 4: Song Trend Edits (3 rotating subcategories via song_ranking_renderer)

8-Step Execution Flow:
  1. Category Choosing (Preserving 4-Day Wheel)
  2. Viral Trend Identification (360° Virality Engine + LLM Cultural Brain)
  3. Candidate Scoring, Format Selection & Multi-Candidate Cascade
  4. Multi-Platform Clip Harvesting (YouTube + TikTok + Instagram + Reddit fallback)
  5. Multimodal Model Frame Analysis & Cut-Point Scoring (Local VLM or Gemini)
  6. DSP Precision Editing (Format-routed: edit_ranking / release_hype / trivia / song_ranking)
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
import re
import sys
import time
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
CADENCE_STATE_FILE = STATE_DIR / "pipeline_cadence_state.json"
USED_TOPICS_FILE = STATE_DIR / "used_topics.json"
PATRICK_JANE_FILE = ROOT / "patrick_jane_series.json"

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

CINEMA_FALLBACK_POOL = [
    {"topic": "Dune", "genre": "superhero_scifi", "recommended_format": "edit_ranking", "query_suffix": "edit shorts"},
    {"topic": "Oppenheimer", "genre": "drama_prestige", "recommended_format": "scene_commentary", "query_suffix": "edit shorts"},
    {"topic": "Interstellar", "genre": "superhero_scifi", "recommended_format": "edit_ranking", "query_suffix": "edit shorts"},
    {"topic": "John Wick", "genre": "action_thriller", "recommended_format": "edit_ranking", "query_suffix": "fight scene edit shorts"},
    {"topic": "Spider-Verse", "genre": "animated_cinema", "recommended_format": "edit_ranking", "query_suffix": "edit shorts"},
]

TV_FALLBACK_POOL = [
    "Breaking Bad",
    "Suits",
    "Peaky Blinders",
    "Stranger Things",
    "Squid Game",
    "Yellowstone",
    "Dexter",
]

SONG_FALLBACK_POOL = [
    "Starboy",
    "Paparazzi",
    "Memory Reboot",
    "Timeless",
    "Montagem",
    "Softcore",
    "Love Me",
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
    used = {"cinema": [], "tv_series": [], "song_trends": []}
    if USED_TOPICS_FILE.exists():
        try:
            data = json.loads(USED_TOPICS_FILE.read_text(encoding="utf-8"))
            used.update(data)
        except Exception:
            pass
    try:
        from channel_intelligence import extract_recent_channel_topics
        ch_topics = extract_recent_channel_topics()
        for t in ch_topics:
            if t not in used["cinema"]:
                used["cinema"].append(t)
            if t not in used["tv_series"]:
                used["tv_series"].append(t)
    except Exception:
        pass
    return used


def _record_used_topic(cat_key: str, topic: str):
    if not topic or cat_key == "mentalist":
        return
    data = _load_used_topics()
    arr = data.setdefault(cat_key, [])
    if topic not in arr:
        arr.append(topic)
    data[cat_key] = arr[-25:]
    USED_TOPICS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean_series_name(raw_show: str) -> str:
    s = re.sub(r"\s*[-–—|:]\s*(?:Season|Part|Vol\.?|Episode|Ep)\s*\d+.*$", "", raw_show, flags=re.I).strip()
    s = re.sub(r"\s+\b(?:Ep|Episode|Season|Part|Vol)\.?\s*\d+\b.*$", "", s, flags=re.I).strip()
    return s or raw_show.strip()


def _get_virality_digest(force_fresh: bool = False) -> dict:
    """Loads fresh (<4h) daily_virality_digest.json or executes the 360° Virality Engine once."""
    import virality_engine
    digest_path = virality_engine.DAILY_DIGEST_PATH
    if not force_fresh and digest_path.exists():
        try:
            age = time.time() - digest_path.stat().st_mtime
            if age < 4 * 3600:
                data = json.loads(digest_path.read_text(encoding="utf-8"))
                if data.get("categories"):
                    logging.info(f"[Virality Engine] Using fresh 360° digest ({age / 60:.0f}m old).")
                    return data
        except Exception:
            pass
    logging.info("🔥 [Virality Engine] Executing live 360° virality scan across all 4 pillars + LLM Brain...")
    try:
        return virality_engine.run_all_category_virality_scan(force_fresh_yt=True)
    except Exception as e:
        logging.warning(f"Live virality scan exception ({e}); reading cached daily digest...")
        if digest_path.exists():
            return json.loads(digest_path.read_text(encoding="utf-8"))
        return {}


def _build_cinema_candidates(digest: dict, topic_override: str, used_set: set[str]) -> list[dict]:
    if topic_override:
        return [{"topic": topic_override, "genre": "action_thriller", "recommended_format": "edit_ranking", "query_suffix": "edit shorts"}]

    candidates: list[dict] = []
    seen: set[str] = set()

    def _push(item: dict):
        t = (item.get("topic") or "").strip()
        if not t or len(t) < 4:
            return
        tl = t.lower()
        if tl in seen or tl in ("lifetime", "producer regrets splitting", "movie", "series", "cinema", "becomes", "there"):
            return
        seen.add(tl)
        candidates.append(item)

    # 1. Check LLM Cultural Brain for breaking event preemption
    llm_brain = digest.get("llm_brain") or {}
    if llm_brain.get("breaking_event_detected"):
        bw = llm_brain.get("breaking_winner") or {}
        bt = (bw.get("topic") or "").strip()
        if bt and bt.lower() not in used_set:
            logging.info(f"🚨 [LLM Brain Preemption] Fast-tracking Breaking Event: '{bt}' (Hype: {bw.get('hype_score')})")
            _push({
                "topic": bt,
                "genre": bw.get("genre", "superhero_scifi"),
                "recommended_format": bw.get("recommended_format", "release_hype"),
                "query_suffix": "trailer edit shorts",
                "preempt": True,
            })

    # 2. Fresh dynamic radar candidates (not recently used)
    raw_cands = digest.get("categories", {}).get("cinema", {}).get("top_candidates", [])
    fresh = [c for c in raw_cands if (c.get("topic") or "").strip().lower() not in used_set]
    stale = [c for c in raw_cands if (c.get("topic") or "").strip().lower() in used_set]
    for c in fresh + stale:
        _push(c)

    # 3. Curated fallback pool
    for fb in CINEMA_FALLBACK_POOL:
        if fb["topic"].lower() not in used_set:
            _push(fb)
    for fb in CINEMA_FALLBACK_POOL:
        _push(fb)

    return candidates[:6]


def _build_tv_candidates(digest: dict, topic_override: str, used_set: set[str]) -> list[dict]:
    if topic_override:
        return [{"topic": _clean_series_name(topic_override), "genre": "tv_thriller", "recommended_format": "edit_ranking", "query_suffix": "edit shorts"}]

    candidates: list[dict] = []
    seen: set[str] = set()

    def _push(name: str, fmt: str = "edit_ranking"):
        clean = _clean_series_name(name)
        if not clean or len(clean) < 3:
            return
        cl = clean.lower()
        if cl in seen:
            return
        seen.add(cl)
        candidates.append({"topic": clean, "genre": "tv_thriller", "recommended_format": fmt, "query_suffix": "edit shorts"})

    raw_shows = digest.get("categories", {}).get("tv_series", {}).get("top_candidates", [])
    fresh = [s for s in raw_shows if _clean_series_name(s.get("series_name") or "").lower() not in used_set]
    stale = [s for s in raw_shows if _clean_series_name(s.get("series_name") or "").lower() in used_set]
    for idx, s in enumerate(fresh + stale):
        # Alternate formats occasionally between edit_ranking and scene_commentary for variety
        fmt = "edit_ranking" if idx % 3 != 2 else "scene_commentary"
        _push(s.get("series_name") or "", fmt=fmt)

    for fb in TV_FALLBACK_POOL:
        if fb.lower() not in used_set:
            _push(fb)
    for fb in TV_FALLBACK_POOL:
        _push(fb)

    return candidates[:6]


def _build_song_candidates(digest: dict, topic_override: str, used_set: set[str]) -> list[str]:
    if topic_override:
        return [topic_override]
    songs: list[str] = []
    seen: set[str] = set()

    def _push(name: str):
        n = (name or "").strip()
        if n and len(n) >= 3 and n.lower() not in seen:
            seen.add(n.lower())
            songs.append(n)

    raw_songs = digest.get("categories", {}).get("song_trends", {}).get("top_candidates", [])
    for s in raw_songs:
        sn = s.get("song_name") if isinstance(s, dict) else str(s)
        if sn and sn.lower() not in used_set:
            _push(sn)
    for fb in SONG_FALLBACK_POOL:
        if fb.lower() not in used_set:
            _push(fb)
    for s in raw_songs:
        sn = s.get("song_name") if isinstance(s, dict) else str(s)
        _push(sn)
    for fb in SONG_FALLBACK_POOL:
        _push(fb)
    return songs[:6]


def _harvest_for_topic(
    topic: str,
    curr_day: int,
    fmt: str,
    q_suffix: str,
    use_mentalist_cfg: dict | None = None,
) -> list[dict]:
    """Multi-platform clip harvester (YouTube + Instagram + TikTok + Reddit fallback)."""
    from clip_harvester import scout_youtube, scout_instagram_reels, scout_tiktok_videos, download_clip

    is_mentalist = (curr_day == 3) or ("mentalist" in topic.lower()) or ("patrick jane" in topic.lower())
    input_dir = ROOT / "input"
    input_dir.mkdir(exist_ok=True)
    need = 1 if fmt == "scene_commentary" else 3

    queries: list[str] = []
    if is_mentalist and use_mentalist_cfg:
        done = int(use_mentalist_cfg.get("completed_episodes", 0))
        themes = use_mentalist_cfg.get("query_themes") or [f"{topic} edit shorts"]
        for offset in range(min(4, len(themes))):
            queries.append(themes[(done + offset) % len(themes)])
    elif curr_day == 4:
        queries = [f"{topic} trend edit shorts", f"{topic} audio edit shorts"]
    else:
        queries = [f"{topic} {q_suffix}", f"{topic} edit shorts", f"{topic} viral edit shorts"]

    raw_candidates: list[dict] = []
    seen_ids: set[str] = set()

    def _extend_unique(items: list[dict]):
        for it in items:
            if it["id"] not in seen_ids:
                seen_ids.add(it["id"])
                raw_candidates.append(it)

    for q in queries[:2]:
        _extend_unique(scout_youtube(q, count=4, ignore_history=False, strict_edit_filter=not is_mentalist))
        if len(raw_candidates) >= 6:
            break

    ig_query = "Patrick Jane" if is_mentalist else topic
    try:
        ig_cands = scout_instagram_reels(ig_query, count=3, ignore_history=False)
        logging.info(f"  📸 Instagram Reels scouted: {len(ig_cands)}")
        _extend_unique(ig_cands)
    except Exception as e:
        logging.warning(f"  Instagram scout skipped: {e}")

    try:
        tt_cands = scout_tiktok_videos(ig_query, count=3, ignore_history=False)
        logging.info(f"  🎵 TikTok scouted: {len(tt_cands)}")
        _extend_unique(tt_cands)
    except Exception as e:
        logging.warning(f"  TikTok scout skipped: {e}")

    by_plat = {"youtube": [], "tiktok": [], "instagram": []}
    for c in raw_candidates:
        by_plat.setdefault(c.get("platform", "youtube"), []).append(c)

    interleaved: list[dict] = []
    for i in range(max((len(v) for v in by_plat.values()), default=0)):
        for p_name in ("youtube", "tiktok", "instagram"):
            if i < len(by_plat.get(p_name, [])):
                interleaved.append(by_plat[p_name][i])

    logging.info(f"Scouted {len(interleaved)} multi-platform candidates (YT={len(by_plat['youtube'])}, TT={len(by_plat['tiktok'])}, IG={len(by_plat['instagram'])}). Downloading...")
    downloaded: list[dict] = []
    for cand in interleaved[:12]:
        p = download_clip(cand, out_dir=input_dir)
        if p and p.exists() and p.stat().st_size > 20_000:
            cand["local_path"] = str(p)
            downloaded.append(cand)
            logging.info(f"  ✓ Downloaded ({cand.get('platform')}): {cand['title'][:40]} ({p.stat().st_size / 1e6:.1f}MB)")
        else:
            logging.warning(f"  ✗ Failed ({cand.get('platform')}): {cand.get('title', '')[:40]} ({cand.get('url')})")
        if len(downloaded) >= max(need + 2, 5):
            break

    if len(downloaded) < need:
        logging.warning(f"Primary harvest yielded {len(downloaded)}/{need} clips; trying Reddit fallback for '{topic}'...")
        try:
            from clip_harvester import scout_reddit_memes_and_clips
            reddit_cands = scout_reddit_memes_and_clips(topic=topic, count=6, video_only=True)
            for cand in reddit_cands:
                p = download_clip(cand, out_dir=input_dir)
                if p and p.exists() and p.stat().st_size > 20_000:
                    cand["local_path"] = str(p)
                    downloaded.append(cand)
                    logging.info(f"  ✓ Downloaded (Reddit): {cand['title'][:40]} ({p.stat().st_size / 1e6:.1f}MB)")
                if len(downloaded) >= max(need + 1, 3):
                    break
        except Exception as re_err:
            logging.warning(f"Reddit fallback failed: {re_err}")

    return downloaded


def run_autonomous_workflow(
    day_override: int = 0,
    topic_override: str = "",
    use_local_vlm: bool = False,
    upload: bool = False,
    clip_dur: float = 16.0,
    digest: dict | None = None,
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
    # STEP 2 & 3: VIRAL TREND IDENTIFICATION & CANDIDATE CASCADE
    # =========================================================================
    logging.info("🔎 STEP 2 & 3: Identifying & Scoring Live Virality Candidates...")
    used_topics = _load_used_topics()
    is_mentalist = (curr_day == 3)
    pj_cfg = None
    chosen_topic = ""
    chosen_genre = "action_thriller"
    chosen_fmt = "edit_ranking"
    chosen_banner = ""
    current_subcat = ""
    downloaded: list[dict] = []

    if is_mentalist:
        chosen_topic = "The Mentalist"
        chosen_genre = "crime_mystery"
        chosen_fmt = "edit_ranking"
        if PATRICK_JANE_FILE.exists():
            pj_cfg = json.loads(PATRICK_JANE_FILE.read_text(encoding="utf-8"))
            os.environ["CLIP_HISTORY_PATH"] = str(PATRICK_JANE_FILE.resolve())
        try:
            downloaded = _harvest_for_topic(chosen_topic, curr_day, chosen_fmt, "edit shorts", use_mentalist_cfg=pj_cfg)
        finally:
            os.environ.pop("CLIP_HISTORY_PATH", None)
        if len(downloaded) < 2:
            raise RuntimeError(f"Starvation: Not enough valid clips downloaded for '{chosen_topic}'.")
    else:
        if digest is None:
            digest = _get_virality_digest(force_fresh=False)

        if curr_day == 1:
            used_set = {t.lower() for t in used_topics.get("cinema", [])}
            cand_list = _build_cinema_candidates(digest, topic_override.strip(), used_set)
            for cand in cand_list:
                t_name = cand["topic"]
                c_fmt = cand.get("recommended_format", "edit_ranking")
                c_sfx = cand.get("query_suffix", "edit shorts")
                logging.info(f"🎬 Trying Cinema Candidate: '{t_name}' | Format={c_fmt} | Genre={cand.get('genre')}")
                dl = _harvest_for_topic(t_name, curr_day, c_fmt, c_sfx)
                min_need = 1 if c_fmt == "scene_commentary" else 2
                if len(dl) >= min_need:
                    chosen_topic = t_name
                    chosen_genre = cand.get("genre", "action_thriller")
                    chosen_fmt = c_fmt
                    downloaded = dl
                    break
                logging.warning(f"  ↷ Insufficient clips ({len(dl)}/{min_need}) for '{t_name}', cascading to next viral candidate...")

        elif curr_day == 2:
            used_set = {t.lower() for t in used_topics.get("tv_series", [])}
            cand_list = _build_tv_candidates(digest, topic_override.strip(), used_set)
            for cand in cand_list:
                t_name = cand["topic"]
                c_fmt = cand.get("recommended_format", "edit_ranking")
                logging.info(f"📺 Trying TV Series Candidate: '{t_name}' | Format={c_fmt}")
                dl = _harvest_for_topic(t_name, curr_day, c_fmt, "edit shorts")
                min_need = 1 if c_fmt == "scene_commentary" else 2
                if len(dl) >= min_need:
                    chosen_topic = t_name
                    chosen_genre = "tv_thriller"
                    chosen_fmt = c_fmt
                    downloaded = dl
                    break
                logging.warning(f"  ↷ Insufficient clips ({len(dl)}/{min_need}) for '{t_name}', cascading to next TV show...")

        elif curr_day == 4:
            sub_idx = state.get("song_subcat_index", 0) % len(SONG_SUBCATEGORIES)
            current_subcat = SONG_SUBCATEGORIES[sub_idx]
            used_set = {t.lower() for t in used_topics.get("song_trends", [])}
            song_list = _build_song_candidates(digest, topic_override.strip(), used_set)
            from song_trend_radar import scout_song_subcategories
            from clip_harvester import download_clip
            input_dir = ROOT / "input"
            input_dir.mkdir(exist_ok=True)

            for cand_song in song_list:
                logging.info(f"🎵 Trying Song Trend Candidate: '{cand_song}' | Subcategory={current_subcat}")
                sub_data = scout_song_subcategories(current_subcat, cand_song)
                edits = sub_data.get("edits", [])
                cand_dl: list[dict] = []
                for e in edits:
                    p = download_clip(e, out_dir=input_dir)
                    if p and p.exists() and p.stat().st_size > 20_000:
                        e["local_path"] = str(p)
                        cand_dl.append(e)
                        if len(cand_dl) >= 4:
                            break
                if len(cand_dl) < 2:
                    # Fallback direct multi-platform harvest for this song
                    cand_dl = _harvest_for_topic(cand_song, curr_day, "song_ranking", "trend edit shorts")
                if len(cand_dl) >= 2:
                    chosen_topic = cand_song
                    chosen_genre = "song_trends"
                    chosen_fmt = "song_ranking"
                    chosen_banner = sub_data.get("banner_title", f"RANKING THE BEST {cand_song.upper()} EDITS")
                    downloaded = cand_dl
                    break
                logging.warning(f"  ↷ Insufficient clips ({len(cand_dl)}/2) for '{cand_song}', cascading to next song...")

    if not chosen_topic or not downloaded:
        raise RuntimeError(f"Starvation: Not enough valid clips harvested across candidates for Pillar #{curr_day}.")

    logging.info(f"🏆 Winning Topic: '{chosen_topic}' (Genre={chosen_genre}, Format={chosen_fmt})")

    # =========================================================================
    # STEP 5: MODEL VISUAL INSPECTION, BEAT-DROP & CUT-POINT SCORING
    # =========================================================================
    logging.info("🧠 STEP 5: Model Vision Inspection on Sequential Timeline Frames...")
    import llm_director

    target_cnt = 1 if chosen_fmt == "scene_commentary" else 3
    curated_clips = llm_director.curate_and_rank_clips(
        candidates=downloaded,
        topic=chosen_topic,
        target_count=target_cnt,
        use_local_model=use_local_vlm,
        pillar_day=curr_day,
    )

    if not curated_clips:
        raise RuntimeError("No candidate clips approved by AI vision filter.")

    logging.info("\n--- AI EDITORIAL RANKING REPORT ---")
    for i, c in enumerate(curated_clips, 1):
        cut = c.get("optimal_cut", {})
        logging.info(
            f"Rank #{i}: {c.get('title', '')[:35]} | Score: {c.get('quality_score')}/10 | "
            f"Label: '{c.get('short_label')}' | Cut: {cut.get('start_sec', 0.0)}s -> {cut.get('end_sec', 0.0)}s"
        )

    # =========================================================================
    # STEP 6: DSP PRECISION EDITING (Format-Routed)
    # =========================================================================
    logging.info(f"🎬 STEP 6: DSP Master Rendering (Format={chosen_fmt})...")
    import dsp_renderer
    output_dir = ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    slug = "".join(ch for ch in chosen_topic.lower() if ch.isalnum()) or "short"

    if is_mentalist:
        ep_num = int(pj_cfg.get("completed_episodes", 0)) + 1 if pj_cfg else 1
        out_mp4 = output_dir / f"thementalist_ep{ep_num:02d}_master_short.mp4"
        logging.info("🔒 [Patrick Jane Trimming Rules Enforced] Mode=Full Uncut (Dialogue preserved, dark fade-in skipped, outro trimmed).")
        dsp_renderer.render_edit_ranking(
            topic=chosen_topic,
            clips=curated_clips,
            output_mp4=out_mp4,
            clip_dur=0.0,
            genre=chosen_genre,
            full_uncut=True,
        )
    elif chosen_fmt == "song_ranking":
        from song_ranking_renderer import render_song_edit_ranking
        out_mp4 = output_dir / f"song_ranking_{slug}_{current_subcat}_master.mp4"
        render_song_edit_ranking(
            chosen_banner or f"RANKING THE BEST {chosen_topic.upper()} EDITS",
            curated_clips,
            out_mp4,
            clip_dur=8.0,
        )
    elif chosen_fmt == "release_hype":
        from clip_harvester import harvest_intro_hook
        out_mp4 = output_dir / f"release_hype_{slug}_master_short.mp4"
        hook = harvest_intro_hook(chosen_topic, exclude_ids={c["id"] for c in curated_clips})
        dsp_renderer.render_release_hype(
            f"THIS WEEK CAN'T HOLD THIS MUCH PEAK... ({chosen_topic})",
            curated_clips,
            out_mp4,
            hook_clip=hook,
            genre=chosen_genre,
        )
    elif chosen_fmt in ("movie_trivia", "scene_commentary"):
        out_mp4 = output_dir / f"{chosen_fmt}_{slug}_master_short.mp4"
        for c in curated_clips:
            c.setdefault("fact_or_commentary", c.get("title", "")[:60])
        dsp_renderer.render_movie_trivia_or_commentary(
            chosen_topic,
            curated_clips,
            out_mp4,
            mode=chosen_fmt,
            genre=chosen_genre,
        )
    else:
        out_mp4 = output_dir / f"{slug}_master_short.mp4"
        effective_clip_dur = 0.0 if clip_dur <= 0 else clip_dur
        dsp_renderer.render_edit_ranking(
            topic=chosen_topic,
            clips=curated_clips,
            output_mp4=out_mp4,
            clip_dur=effective_clip_dur,
            genre=chosen_genre,
            full_uncut=False,
        )

    logging.info(f"Render completed: {out_mp4} ({out_mp4.stat().st_size / 1e6:.2f} MB)")

    # =========================================================================
    # STEP 7: QA RECHECKING & MODEL SELF-HEALING LOOP
    # =========================================================================
    logging.info("🔍 STEP 7: QA Verification & Model Self-Healing...")
    import qa_gate
    qa_res = qa_gate.verify_video(out_mp4)
    passed = qa_res.get("passed", False)
    issues = qa_res.get("issues", [])

    if (not passed or issues) and chosen_fmt == "edit_ranking" and not is_mentalist:
        logging.warning(f"⚠️ QA Gate flagged issues: {issues}. Triggering AI Self-Healing Loop...")
        repair = llm_director.diagnose_and_repair_defect(
            qa_issues=issues,
            video_path=out_mp4,
            clips=curated_clips,
            topic=chosen_topic,
        )
        logging.info(f"🔧 Model Repair Decision: {repair['diagnosis_summary']}")
        adjusted_dur = max(10.0, (clip_dur or 16.0) + repair.get("clip_dur_adjustment", 0.0))
        dsp_renderer.render_edit_ranking(
            topic=chosen_topic,
            clips=curated_clips,
            output_mp4=out_mp4,
            clip_dur=adjusted_dur,
            genre=chosen_genre,
        )
        qa_res = qa_gate.verify_video(out_mp4)
        logging.info(f"✅ Post-Repair QA Result: passed={qa_res.get('passed', False)}, issues={qa_res.get('issues', [])}")
    else:
        logging.info(f"✅ QA Gate: passed={passed} | issues={issues}")

    # Record topic & series state ONLY after successful render + QA
    if curr_day == 1:
        _record_used_topic("cinema", chosen_topic)
    elif curr_day == 2:
        _record_used_topic("tv_series", chosen_topic)
    elif curr_day == 4:
        _record_used_topic("song_trends", chosen_topic)
    elif is_mentalist and PATRICK_JANE_FILE.exists():
        fresh_cfg = json.loads(PATRICK_JANE_FILE.read_text(encoding="utf-8"))
        fresh_cfg["used_clip_ids"] = sorted(set(fresh_cfg.get("used_clip_ids", [])) | {c["id"] for c in curated_clips})
        fresh_cfg["completed_episodes"] = int(fresh_cfg.get("completed_episodes", 0)) + 1
        fresh_cfg["last_run_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        PATRICK_JANE_FILE.write_text(json.dumps(fresh_cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    # =========================================================================
    # STEP 8: SEO TITLE + VIRAL HASHTAGS + CREDITS + SCHEDULING
    # =========================================================================
    logging.info("📝 STEP 8: Generating SEO Metadata & Unrelated Trending Hashtags Cloud...")
    import metadata_uploader
    meta = metadata_uploader.build_metadata(
        topic=chosen_topic,
        fmt="edit_ranking" if chosen_fmt == "song_ranking" else chosen_fmt,
        clips=curated_clips,
        genre=chosen_genre,
    )
    if is_mentalist and pj_cfg:
        ep_num = int(pj_cfg.get("completed_episodes", 0)) + 1
        meta["title"] = f"Ranking Best The Mentalist Edits (Part {ep_num})! 🔥💀 #shorts #thementalist #naofloppa #shortsfeed"[:100]
    elif chosen_fmt == "song_ranking":
        meta["title"] = f"Ranking Best {chosen_topic} Edits! 🔥💀 #shorts #naofloppa #shortsfeed"[:100]

    logging.info("\n--- GENERATED PUBLISHING METADATA ---")
    logging.info(f"Title: {meta['title']}")
    logging.info(f"Slot:  {meta['recommended_slot_utc']}")
    logging.info(f"Tags:  {meta['tags']}")

    meta_out = output_dir / f"{slug}_metadata.json"
    meta_out.write_text(json.dumps({
        "pillar_day": curr_day,
        "category": category_name,
        "topic": chosen_topic,
        "genre": chosen_genre,
        "format": chosen_fmt,
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

    # Advance 4-day rotating category wheel upon successful production
    state["current_day_index"] = (curr_day % 4) + 1
    if curr_day == 4:
        state["song_subcat_index"] = (state.get("song_subcat_index", 0) + 1) % len(SONG_SUBCATEGORIES)
        state["cycle_count"] = state.get("cycle_count", 1) + 1
    state["last_run_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state.setdefault("history", []).append({
        "timestamp_utc": state["last_run_utc"],
        "day": curr_day,
        "category": category_name,
        "topic": chosen_topic,
        "format": chosen_fmt,
        "video_id": upload_result.get("video_id"),
        "result": "success",
    })
    state["history"] = state["history"][-30:]
    save_cadence_state(state)
    logging.info(f"🎡 Advanced Rotating Wheel to Pillar #{state['current_day_index']}: {CADENCE_NAMES[state['current_day_index']]}")

    return {
        "status": "success",
        "pillar_day": curr_day,
        "category": category_name,
        "topic": chosen_topic,
        "format": chosen_fmt,
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
    """Runs all 4 Category Pillars sequentially using a single shared 360° Virality Engine scan."""
    day_order = [((start_day - 1 + i) % 4) + 1 for i in range(4)]
    results = []
    logging.info(f"\n🎡 STARTING FULL 4-CATEGORY CYCLE: {day_order}")

    # Run 360° Virality Engine ONCE for the entire cycle
    shared_digest = _get_virality_digest(force_fresh=True)

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
                digest=shared_digest,
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
    parser.add_argument("--local-vlm", action="store_true", help="Use local small VLM (Qwen2-VL-2B) instead of Gemini API")
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
