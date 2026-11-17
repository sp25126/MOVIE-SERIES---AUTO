"""Single CLI entrypoint: 100% dynamic virality selector across 8 genre groups -> harvest -> DSP -> QA."""

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

from clip_harvester import fetch_wikimedia_image, harvest_video_pack, passes_copyright_prefilter
from dsp_renderer import (
    ensure_royalty_free_bgm,
    render_edit_ranking,
    render_movie_trivia_or_commentary,
    render_news_slideshow,
    render_release_hype,
)
from metadata_uploader import build_metadata, upload_private_canary_and_schedule
from qa_gate import verify_video
from virality_radar import compute_multi_horizon_score, compute_vph_score, scan_virality

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
TEMP_DIR = ROOT / "temp"
CATALOG_PATH = ROOT / "niche_catalog.json"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:36] or "short"


def select_fresh_viral_target(report: dict, genre_filter: str | None = None, fmt_override: str = "auto") -> dict:
    """Picks highest-virality live topic not on cooldown, preferring a fresh genre when possible."""
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    recent_topics = {t.lower() for t in cat.get("recent_topics", [])}
    last_genre = (cat.get("recent_genres") or [""])[-1]

    pool = report.get("top_topics") or [report["winner"]]
    if genre_filter:
        filtered = [t for t in pool if t.get("genre") == genre_filter]
        pool = filtered or pool

    # 1. Highest-virality topic not recently used AND from a different genre than last run
    for cand in pool:
        if cand["topic"].lower() not in recent_topics and cand.get("genre") != last_genre:
            target = dict(cand)
            break
    else:
        # 2. Highest-virality topic not recently used (any genre)
        target = dict(next((c for c in pool if c["topic"].lower() not in recent_topics), pool[0]))

    if fmt_override != "auto":
        target["recommended_format"] = fmt_override
    return target


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
    """Fast self-check: virality math, Anti-CID filter, procedural BGM, and 8-genre dynamic catalog."""
    s_fresh = compute_vph_score(views=120_000, age_hours=6, channel_subs=5_000)
    s_stale = compute_vph_score(views=120_000, age_hours=160, channel_subs=500_000)
    assert s_fresh > s_stale * 5, f"Expected fresh breakout >> stale: {s_fresh} vs {s_stale}"
    assert compute_multi_horizon_score(100, 50, 50, 50) == 70.0

    ok1, _ = passes_copyright_prefilter({"title": "Scene Edit", "channel": "FanEdits", "duration": 22})
    ok2, _ = passes_copyright_prefilter({"title": "Song", "channel": "FanEdits", "duration": 22, "track": "Hit Song"})
    ok3, _ = passes_copyright_prefilter({"title": "Full Movie HD", "channel": "MoviesHub", "duration": 22})
    ok4, _ = passes_copyright_prefilter({"title": "Clip", "channel": "ArtistVEVO", "duration": 22})
    assert ok1 and not ok2 and not ok3 and not ok4, "Copyright pre-filter failed!"

    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert len(cat["groups"]) == 8, f"Expected 8 genre groups, got {len(cat['groups'])}"
    for gid, g in cat["groups"].items():
        for sc in g["subcategories"]:
            assert "topics" not in sc, f"Static topics list found in {gid}/{sc['id']}!"

    bgm = ensure_royalty_free_bgm("phonk")
    assert bgm.exists() and bgm.stat().st_size > 30_000, "BGM generation failed!"

    print("[SELF-TEST] ALL CHECKS PASSED (virality math, Anti-CID, 8 zero-static genre groups, royalty-free BGM).")
    return 0


def run_pipeline(
    fmt: str = "auto",
    topic: str | None = None,
    genre: str | None = None,
    handle: str = "@CinePulse",
    dry_run: bool = True,
    count: int = 3,
    extra_urls: list[str] | None = None,
    browser_cookies: str = "",
) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = scan_virality(skip_yt=bool(topic))

    if topic:
        target = {
            "topic": topic,
            "genre": genre or "action_thriller",
            "subcategory": "manual_override",
            "recommended_format": "edit_ranking" if fmt == "auto" else fmt,
            "query_suffix": "edit shorts",
        }
    else:
        target = select_fresh_viral_target(report, genre_filter=genre, fmt_override=fmt)

    chosen_topic = target["topic"]
    chosen_genre = target.get("genre", "cinema_news_trivia")
    chosen_fmt = target["recommended_format"]
    q_sfx = target.get("query_suffix", "edit shorts")
    print(f"\n[Pipeline] Dynamic Pick -> Genre='{chosen_genre}' | Topic='{chosen_topic}' | Format='{chosen_fmt}' | DryRun={dry_run}")

    out_mp4 = OUTPUT_DIR / f"{chosen_fmt}_{_slug(chosen_topic)}_master.mp4"
    clips: list[dict] = []

    if chosen_fmt == "news_slideshow":
        feed = report.get("breaking_news_feed") or []
        if not feed:
            feed = [{"title": f"Breaking {chosen_topic} Update Shakes Fans!", "source": "Cinema Wire"}]
        hook_img = fetch_wikimedia_image(chosen_topic, TEMP_DIR / "still_0.jpg")
        slides = [{
            "headline": f"BIGGEST MOVIE & SERIES NEWS RIGHT NOW! ({chosen_topic})",
            "source": "LIVE RADAR",
            "badge": "BREAKING RADAR",
            "image_path": str(hook_img) if hook_img else None,
        }]
        for idx, item in enumerate(feed[:4], 1):
            clean_q = " ".join(re.findall(r"[A-Za-z0-9]+", item["title"])[:4]) or chosen_topic
            img_p = fetch_wikimedia_image(clean_q, TEMP_DIR / f"still_{idx}.jpg")
            slides.append({
                "headline": item["title"][:95],
                "source": item.get("source", "Entertainment News"),
                "badge": f"UPDATE #{idx}",
                "image_path": str(img_p) if img_p else None,
            })
        render_news_slideshow(slides, out_mp4, handle=handle)
        clips = feed[:4]

    elif chosen_fmt == "edit_ranking":
        queries = [f"{chosen_topic} {q_sfx}", f"{chosen_topic} best scene edit shorts", f"{chosen_topic} moments edit"]
        clips = harvest_video_pack(
            queries, target_count=count, max_duration=65,
            extra_urls=extra_urls, browser_cookies=browser_cookies, required_topic=chosen_topic,
        )
        if not clips:
            print(f"[Pipeline] Video harvest empty for '{chosen_topic}' -> falling back to news_slideshow.")
            return run_pipeline(fmt="news_slideshow", topic=chosen_topic, genre=chosen_genre, handle=handle, dry_run=dry_run, count=count)
        for i, c in enumerate(clips, 1):
            words = re.findall(r"[A-Za-z0-9]+", c["title"])
            c["short_label"] = " ".join(words[:2]).title() if words else f"Clip {i}"
        render_edit_ranking(chosen_topic, clips, out_mp4, handle=handle, clip_dur=10.0)

    elif chosen_fmt == "release_hype":
        queries = [f"{chosen_topic} {q_sfx}", f"{chosen_topic} trailer edit shorts", f"{chosen_topic} movie clip shorts"]
        clips = harvest_video_pack(
            queries, target_count=max(count, 4), max_duration=65,
            extra_urls=extra_urls, browser_cookies=browser_cookies, required_topic=chosen_topic,
        )
        if not clips:
            print(f"[Pipeline] Video harvest empty for '{chosen_topic}' -> falling back to news_slideshow.")
            return run_pipeline(fmt="news_slideshow", topic=chosen_topic, genre=chosen_genre, handle=handle, dry_run=dry_run, count=count)
        render_release_hype(f"THIS WEEK CAN'T HOLD THIS MUCH PEAK... ({chosen_topic})", clips, out_mp4, handle=handle)

    else:  # movie_trivia or scene_commentary
        is_triv = chosen_fmt == "movie_trivia"
        queries = [f"{chosen_topic} {q_sfx}", f"{chosen_topic} scene shorts", f"{chosen_topic} movie clip edit"]
        clips = harvest_video_pack(
            queries, target_count=3 if is_triv else 1, max_duration=65,
            extra_urls=extra_urls, browser_cookies=browser_cookies, required_topic=chosen_topic,
        )
        if not clips:
            print(f"[Pipeline] Video harvest empty for '{chosen_topic}' -> falling back to news_slideshow.")
            return run_pipeline(fmt="news_slideshow", topic=chosen_topic, genre=chosen_genre, handle=handle, dry_run=dry_run, count=count)
        for c in clips:
            c["fact_or_commentary"] = c["title"][:60]
        render_movie_trivia_or_commentary(chosen_topic, clips, out_mp4, handle=handle, mode=chosen_fmt)

    qa = verify_video(out_mp4, make_proof=True)
    meta = build_metadata(chosen_topic, chosen_fmt, clips, handle=handle)
    out_mp4.with_suffix(".meta.json").write_text(json.dumps({"target": target, "qa": qa, "metadata": meta}, indent=2, ensure_ascii=False), encoding="utf-8")

    record_run_cooldown(chosen_topic, chosen_genre)

    upload_res = None
    if not dry_run:
        if not qa["passed"]:
            raise RuntimeError(f"QA Gate failed ({qa['issues']}); upload aborted.")
        upload_res = upload_private_canary_and_schedule(out_mp4, meta)

    print(f"[Pipeline] Done -> {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'} | Proof={qa.get('proof_sheet')}")
    return {"video": str(out_mp4), "target": target, "qa": qa, "metadata": meta, "upload": upload_res}


def run_series_episode(series_path: Path, handle: str = "@CinePulse", dry_run: bool = True, browser_cookies: str = "") -> dict | None:
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
    # Rotate across 4 distinct query themes per episode so 3 fresh unique clips harvest fast without yt_dlp timeouts
    rotated_queries = [themes[(done + offset) % len(themes)] for offset in range(min(4, len(themes)))]

    os.environ["CLIP_HISTORY_PATH"] = str(series_path.resolve())
    try:
        clips = harvest_video_pack(
            rotated_queries,
            target_count=int(cfg.get("clips_per_episode", 3)),
            max_duration=65,
            browser_cookies=browser_cookies,
            required_topic=cfg["topic"],
        )
        if not clips:
            raise RuntimeError(f"No fresh unique clips left for {cfg['series_name']} Ep #{ep_num}")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_mp4 = OUTPUT_DIR / f"edit_ranking_{_slug(cfg['topic'])}_ep{ep_num:02d}_master.mp4"
        for i, c in enumerate(clips, 1):
            words = re.findall(r"[A-Za-z0-9]+", c["title"])
            c["short_label"] = " ".join(words[:2]).title() if words else f"Edit {i}"

        render_edit_ranking(cfg["topic"], clips, out_mp4, handle=handle, clip_dur=10.0)
        qa = verify_video(out_mp4, make_proof=True)
        meta = build_metadata(cfg["topic"], "edit_ranking", clips, handle=handle)
        meta["title"] = f"Ranking Best {cfg['topic']} Edits (Part {ep_num})! 🔥💀 #shorts #thementalist"[:100]
        out_mp4.with_suffix(".meta.json").write_text(json.dumps({"episode": ep_num, "qa": qa, "metadata": meta}, indent=2, ensure_ascii=False), encoding="utf-8")

        # Reload updated used_clip_ids saved by harvester and increment episode counter
        fresh_cfg = json.loads(series_path.read_text(encoding="utf-8"))
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
    p = argparse.ArgumentParser(description="100% Dynamic Virality-First Movies & Series Shorts Automation")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--series-file", default=None, help="Run next unique episode of a recurring series config (e.g. patrick_jane_series.json)")
    p.add_argument("--format", default="auto", choices=["auto", "edit_ranking", "release_hype", "movie_trivia", "scene_commentary", "news_slideshow"])
    p.add_argument("--genre", default=None, help="Optional genre group ID from niche_catalog.json")
    p.add_argument("--topic", default=None)
    p.add_argument("--handle", default="@CinePulse")
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--urls", nargs="*", default=None, help="Optional IG/FB/TikTok/YT URLs to include")
    p.add_argument("--cookies-from-browser", default="", help="Browser for optional IG/FB public session cookies (e.g. chrome)")
    p.add_argument("--upload", action="store_true", help="Upload private canary & schedule (default is local dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Explicit local dry-run (default)")
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
        extra_urls=args.urls,
        browser_cookies=args.cookies_from_browser,
    )
