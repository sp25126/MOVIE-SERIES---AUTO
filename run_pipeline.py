"""Single CLI entrypoint: 100% dynamic pure-video virality selector across 7 genre groups -> harvest -> DSP -> QA."""

import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

from clip_harvester import harvest_intro_hook, harvest_video_pack, passes_copyright_prefilter
from dsp_renderer import (
    ensure_royalty_free_bgm,
    render_edit_ranking,
    render_movie_trivia_or_commentary,
    render_release_hype,
)
from metadata_uploader import build_metadata, upload_private_canary_and_schedule
from qa_gate import verify_video
from virality_radar import compute_multi_horizon_score, compute_vph_score, scan_virality

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
CATALOG_PATH = ROOT / "niche_catalog.json"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:36] or "short"


def ordered_fresh_targets(report: dict, genre_filter: str | None = None, fmt_override: str = "auto") -> list[dict]:
    """Orders live viral candidates (non-cooldown + fresh genre first) so harvest can cascade if a topic has 0 clips."""
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    recent_topics = {t.lower() for t in cat.get("recent_topics", [])}
    last_genre = (cat.get("recent_genres") or [""])[-1]

    pool = list(report.get("top_topics") or [report["winner"]])
    if genre_filter:
        filtered = [t for t in pool if t.get("genre") == genre_filter]
        pool = filtered or pool

    tier1 = [dict(c) for c in pool if c["topic"].lower() not in recent_topics and c.get("genre") != last_genre]
    tier2 = [dict(c) for c in pool if c["topic"].lower() not in recent_topics and c.get("genre") == last_genre]
    tier3 = [dict(c) for c in pool if c["topic"].lower() in recent_topics]
    ordered = tier1 + tier2 + tier3
    for t in ordered:
        if fmt_override != "auto":
            t["recommended_format"] = fmt_override
    return ordered


def record_run_cooldown(topic: str, genre: str):
    if not CATALOG_PATH.exists():
        return
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    rt = [t for t in cat.get("recent_topics", []) if t.lower() != topic.lower()]
    rt.append(topic)
    cat["recent_topics"] = rt[-12:]
    rg = cat.get("recent_genres", [])
    rg.append(genre)
    cat["recent_genres"] = rg[-8:]
    CATALOG_PATH.write_text(json.dumps(cat, indent=2, ensure_ascii=False), encoding="utf-8")


def run_self_test() -> int:
    """Fast self-check: virality math, Anti-CID filter, 7 zero-static pure-video genre groups, BGM."""
    s_fresh = compute_vph_score(views=120_000, age_hours=6, channel_subs=5_000)
    s_stale = compute_vph_score(views=120_000, age_hours=160, channel_subs=500_000)
    assert s_fresh > s_stale * 5, f"Expected fresh breakout >> stale: {s_fresh} vs {s_stale}"
    assert compute_multi_horizon_score(100, 50, 50, 50) == 70.0

    ok1, _ = passes_copyright_prefilter({"title": "Scene Edit", "channel": "FanEdits", "duration": 22})
    ok2, _ = passes_copyright_prefilter({"title": "Song", "channel": "FanEdits", "duration": 22, "track": "Hit Song"})
    ok3, _ = passes_copyright_prefilter({"title": "Full Movie HD", "channel": "MoviesHub", "duration": 22})
    ok4, _ = passes_copyright_prefilter({"title": "Clip", "channel": "ArtistVEVO", "duration": 22})
    ok5, _ = passes_copyright_prefilter({"title": "Ramayana 2026 Concept Trailer", "channel": "Random", "duration": 22})
    ok6, _ = passes_copyright_prefilter({"title": "Lord Shiva Tandav", "channel": "Random", "duration": 22, "description": "This is a fan-made AI generated concept video"})
    ok7, _ = passes_copyright_prefilter({"title": "Patrick Jane Edit", "channel": "BruCe", "duration": 45, "description": "Song - I Wanna Be Yours X Summertime Sadness"})
    assert ok1 and not ok2 and not ok3 and not ok4 and not ok5 and not ok6 and not ok7, "Copyright/Fake-AI pre-filter failed!"

    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert len(cat["groups"]) == 12, f"Expected 12 video genre groups, got {len(cat['groups'])}"
    for gid, g in cat["groups"].items():
        for sc in g["subcategories"]:
            assert "topics" not in sc, f"Static topics list found in {gid}/{sc['id']}!"
            assert sc["format"] != "news_slideshow", f"Removed news_slideshow found in {gid}/{sc['id']}!"

    bgm = ensure_royalty_free_bgm("phonk", allow_network=False)
    assert bgm.exists() and bgm.stat().st_size > 30_000, "BGM generation failed!"

    print("[SELF-TEST] ALL CHECKS PASSED (virality math, Anti-CID/HTML/Fake-AI, 12 pure-video zero-static genre groups, BGM).")
    return 0


def run_pipeline(
    fmt: str = "auto",
    topic: str | None = None,
    genre: str | None = None,
    handle: str = "@OtakuSnapster",
    dry_run: bool = True,
    count: int = 3,
    clip_dur: float = 0.0,
    extra_urls: list[str] | None = None,
    hook_url: str = "",
    browser_cookies: str = "",
    preempt: bool = False,
) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    from virality_radar import REPORT_PATH
    skip_yt = False
    if REPORT_PATH.exists() and (time.time() - REPORT_PATH.stat().st_mtime) < 3 * 3600:
        skip_yt = True
    report = scan_virality(skip_yt=skip_yt)

    primary = (
        [{"topic": topic, "genre": genre or "action_thriller", "subcategory": "manual_override", "recommended_format": "edit_ranking" if fmt == "auto" else fmt, "query_suffix": "edit shorts"}]
        if topic
        else []
    )
    fallbacks = ordered_fresh_targets(report, genre_filter=genre, fmt_override=fmt)[:6]
    if topic:
        fallbacks = [f for f in fallbacks if f.get("topic", "").lower() != topic.lower()]
    candidates = primary + fallbacks

    chosen_target, clips = None, []
    for cand in candidates:
        c_topic = cand["topic"]
        c_fmt = cand["recommended_format"]
        q_sfx = cand.get("query_suffix", "edit shorts")
        need = 1 if c_fmt == "scene_commentary" else (max(count, 4) if c_fmt == "release_hype" else count)
        queries = [
            f"{c_topic} edit #shorts",
            f"{c_topic} {q_sfx}",
            f"{c_topic} edit shorts",
            f"{c_topic} movie edit shorts",
            f"{c_topic} badass edit #shorts",
        ]
        print(f"\n[Pipeline] Trying viral target -> Genre='{cand.get('genre')}' | Topic='{c_topic}' | Format='{c_fmt}'")
        max_dur = 95 if c_fmt == "scene_commentary" else 65
        min_dur = 25 if c_fmt == "scene_commentary" else 5
        c_genre = cand.get("genre") or genre or "action_thriller"
        niche_ctx = (
            "Animated Cinema & Feature Animation (Pixar, DreamWorks, Spider-Verse)"
            if c_genre == "animated_cinema"
            else "Live-Action Movies, Series & Cinema"
        )
        clips = harvest_video_pack(
            queries, target_count=need, max_duration=max_dur, min_duration=min_dur,
            extra_urls=extra_urls, browser_cookies=browser_cookies, required_topic=c_topic,
            niche_context=niche_ctx,
        )
        if clips:
            chosen_target = cand
            break
        print(f"[Pipeline] 0 clean clips for '{c_topic}', advancing to next viral target...")

    if not chosen_target or not clips:
        raise RuntimeError("No copyright-safe video clips harvested across top viral targets.")

    chosen_topic = chosen_target["topic"]
    chosen_genre = chosen_target.get("genre", "action_thriller")
    chosen_fmt = chosen_target["recommended_format"]
    out_mp4 = OUTPUT_DIR / f"{chosen_fmt}_{_slug(chosen_topic)}_master.mp4"

    if chosen_fmt == "edit_ranking":
        clips.sort(key=lambda x: x.get("views", 0), reverse=True)
        for c in clips:
            c["short_label"] = _clean_rank_label(c["title"], chosen_topic, int(c.get("views", 0)))
        render_edit_ranking(chosen_topic, clips, out_mp4, handle=handle, clip_dur=clip_dur, genre=chosen_genre)
    elif chosen_fmt == "release_hype":
        hook = harvest_intro_hook(chosen_topic, hook_url=hook_url, browser_cookies=browser_cookies, exclude_ids={c["id"] for c in clips})
        render_release_hype(f"THIS WEEK CAN'T HOLD THIS MUCH PEAK... ({chosen_topic})", clips, out_mp4, handle=handle, hook_clip=hook, genre=chosen_genre)
    else:
        for c in clips:
            c["fact_or_commentary"] = c["title"][:60]
        render_movie_trivia_or_commentary(chosen_topic, clips, out_mp4, handle=handle, mode=chosen_fmt, genre=chosen_genre)

    qa = verify_video(out_mp4, make_proof=True)
    meta = build_metadata(chosen_topic, chosen_fmt, clips, handle=handle)
    out_mp4.with_suffix(".meta.json").write_text(json.dumps({"target": chosen_target, "qa": qa, "metadata": meta}, indent=2, ensure_ascii=False), encoding="utf-8")

    record_run_cooldown(chosen_topic, chosen_genre)

    upload_res = None
    if not dry_run:
        if not qa["passed"]:
            raise RuntimeError(f"QA Gate failed ({qa['issues']}); upload aborted.")
        if preempt:
            # Pre-empt earliest upcoming slot and shift existing queue forward
            from queue_manager import preempt_and_reschedule_for_breaking_event
            breaking_entry = {
                "video_path": str(out_mp4),
                "title": meta.get("title", ""),
                "topic": chosen_topic,
                "genre": chosen_genre,
            }
            preempt_and_reschedule_for_breaking_event(breaking_entry, sync_youtube=True)
            meta["recommended_slot_utc"] = breaking_entry.get("publish_at")
        upload_res = upload_private_canary_and_schedule(out_mp4, meta)
    elif preempt:
        from queue_manager import preempt_and_reschedule_for_breaking_event
        breaking_entry = {
            "video_path": str(out_mp4),
            "title": meta.get("title", ""),
            "topic": chosen_topic,
            "genre": chosen_genre,
        }
        preempt_and_reschedule_for_breaking_event(breaking_entry, sync_youtube=False)

    print(f"[Pipeline] Done -> {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'} | Proof={qa.get('proof_sheet')}")
    return {"video": str(out_mp4), "target": chosen_target, "qa": qa, "metadata": meta, "upload": upload_res}


def _fmt_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _clean_rank_label(title: str, topic: str, views: int) -> str:
    skip = {"patrick", "jane", "the", "mentalist", "edit", "edits", "4k", "hd", "shorts", "short", "viral", "best", "cold", "coldest", "moment", "moments"} | set(re.findall(r"[a-z0-9]+", topic.lower()))
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title) if w.lower() not in skip and len(w) >= 2]
    tag = " ".join(words[:2]).title()[:11] or "Climax"
    return f"{tag} ({_fmt_views(views)})" if views >= 1000 else tag


def run_series_episode(series_path: Path, handle: str = "@OtakuSnapster", dry_run: bool = True, browser_cookies: str = "") -> dict | None:
    """Runs one episode of a bounded recurring series (e.g. 60-day Patrick Jane every 3 days) with 0 clip repeats."""
    cfg = json.loads(series_path.read_text(encoding="utf-8"))
    today_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    done = int(cfg.get("completed_episodes", 0))
    max_ep = int(cfg.get("max_episodes", 20))
    end_date = cfg.get("end_date_utc", "2099-12-31")

    if today_utc > end_date or done >= max_ep:
        print(f"[Series] '{cfg['series_name']}' complete ({done}/{max_ep} episodes, end={end_date}). Nothing to run.")
        return None

    ep_num = done + 1
    themes = cfg.get("query_themes") or [f"{cfg['topic']} edit shorts"]
    rotated_queries = [themes[(done + offset) % len(themes)] for offset in range(min(5, len(themes)))]
    # Append guaranteed high-yield fallback queries for The Mentalist
    fallbacks = [
        f"{cfg['topic']} edit #shorts",
        f"The Mentalist Patrick Jane edit shorts",
        f"Kimball Cho badass edit #shorts",
        f"Patrick Jane cold edit #shorts",
    ]
    for fb in fallbacks:
        if fb not in rotated_queries:
            rotated_queries.append(fb)

    os.environ["CLIP_HISTORY_PATH"] = str(series_path.resolve())
    target_cnt = int(cfg.get("clips_per_episode", 3))
    try:
        clips = harvest_video_pack(
            rotated_queries,
            target_count=target_cnt,
            max_duration=int(cfg.get("max_clip_duration", 65)),
            min_duration=int(cfg.get("min_clip_duration", 8)),
            browser_cookies=browser_cookies,
            required_topic=cfg["topic"],
            allowed_entities=cfg.get("ensemble_characters"),
        )
        if len(clips) < target_cnt:
            raise RuntimeError(f"Only harvested {len(clips)}/{target_cnt} fresh unique fan edits for {cfg['series_name']} Ep #{ep_num}. Minimum 3 required for ranking.")

        # Strictly rank by views descending (#1 = highest views, played last as climax)
        clips.sort(key=lambda x: x.get("views", 0), reverse=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_mp4 = OUTPUT_DIR / f"edit_ranking_{_slug(cfg['topic'])}_ep{ep_num:02d}_master.mp4"
        for c in clips:
            c["short_label"] = _clean_rank_label(c["title"], cfg["topic"], int(c.get("views", 0)))

        clip_dur = 0.0 if cfg.get("full_uncut") else 18.0
        render_edit_ranking(cfg["topic"], clips, out_mp4, handle=handle, clip_dur=clip_dur)
        qa = verify_video(out_mp4, make_proof=True)
        meta = build_metadata(cfg["topic"], "edit_ranking", clips, handle=handle)
        meta["title"] = f"Ranking Best {cfg['topic']} Edits (Part {ep_num})! 🔥💀 #shorts #thementalist #naofloppa #shortsfeed"[:100]
        out_mp4.with_suffix(".meta.json").write_text(json.dumps({"episode": ep_num, "qa": qa, "metadata": meta}, indent=2, ensure_ascii=False), encoding="utf-8")

        fresh_cfg = json.loads(series_path.read_text(encoding="utf-8"))
        used_all = set(fresh_cfg.get("used_clip_ids", [])) | {c["id"] for c in clips}
        fresh_cfg["used_clip_ids"] = sorted(used_all)
        fresh_cfg["completed_episodes"] = ep_num
        fresh_cfg["last_run_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        series_path.write_text(json.dumps(fresh_cfg, indent=2, ensure_ascii=False), encoding="utf-8")

        upload_res = None
        if not dry_run:
            if not qa["passed"]:
                raise RuntimeError(f"QA Gate failed ({qa['issues']}); upload aborted.")
            upload_res = upload_private_canary_and_schedule(out_mp4, meta)

        print(f"[Series] {cfg['series_name']} Ep #{ep_num}/{max_ep} Done -> {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'} | UniqueClipsTotal={len(fresh_cfg['used_clip_ids'])}")
        return {"episode": ep_num, "video": str(out_mp4), "qa": qa, "upload": upload_res}
    finally:
        os.environ.pop("CLIP_HISTORY_PATH", None)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="100% Dynamic Pure-Video Virality-First Movies & Series Shorts Automation")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--series-file", default=None, help="Run next unique episode of a recurring series config (e.g. patrick_jane_series.json)")
    p.add_argument("--format", default="auto", choices=["auto", "edit_ranking", "release_hype", "movie_trivia", "scene_commentary"])
    p.add_argument("--genre", default=None, help="Optional genre group ID from niche_catalog.json")
    p.add_argument("--topic", default=None)
    p.add_argument("--handle", default="@OtakuSnapster")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--clip-dur", type=float, default=0.0, help="Seconds per clip in edit ranking (0 or negative = 100%% full uncut)")
    p.add_argument("--urls", nargs="*", default=None, help="Optional IG/FB/TikTok/YT URLs to include")
    p.add_argument("--hook-url", default="", help="Optional Instagram Reel / edit URL to prepend as 3.2s retention hook")
    p.add_argument("--cookies-from-browser", default="", help="Browser for optional IG/FB public session cookies (e.g. chrome)")
    p.add_argument("--upload", action="store_true", help="Upload private canary & schedule (default is local dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Explicit local dry-run (default)")
    p.add_argument("--preempt", action="store_true", help="Fast-track breaking topic and preempt upcoming schedule slot")
    args = p.parse_args()

    if args.self_test:
        sys.exit(run_self_test())

    if args.series_file:
        run_series_episode(Path(args.series_file), handle=args.handle, dry_run=not args.upload, browser_cookies=args.cookies_from_browser)
        sys.exit(0)

    run_pipeline(
        fmt=args.format,
        topic=args.topic,
        genre=args.genre,
        handle=args.handle,
        dry_run=not args.upload,
        count=args.count,
        clip_dur=args.clip_dur,
        extra_urls=args.urls,
        hook_url=args.hook_url,
        browser_cookies=args.cookies_from_browser,
        preempt=args.preempt,
    )
