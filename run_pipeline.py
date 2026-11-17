"""Single CLI entrypoint for MOVIE-SERIES---AUTO (virality -> harvest -> DSP -> QA -> metadata)."""

import argparse
import json
import re
import sys
from pathlib import Path

from clip_harvester import (
    fetch_wikimedia_image,
    harvest_video_pack,
    passes_copyright_prefilter,
    scout_reddit_memes_and_clips,
)
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


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:36] or "short"


def run_self_test() -> int:
    """Fast self-check: virality scoring, copyright pre-filter, and procedural BGM synthesis."""
    # 1. Virality math sanity
    s_fresh = compute_vph_score(views=120_000, age_hours=6, channel_subs=5_000)
    s_stale = compute_vph_score(views=120_000, age_hours=160, channel_subs=500_000)
    assert s_fresh > s_stale * 5, f"Expected fresh breakout >> stale: {s_fresh} vs {s_stale}"

    mh = compute_multi_horizon_score(100, 50, 50, 50)
    assert mh == 70.0, f"Weighted horizon mismatch: {mh}"

    # 2. Anti-CID pre-filter sanity
    ok1, _ = passes_copyright_prefilter({"title": "Patrick Jane Edit", "channel": "FanEdits", "duration": 22})
    ok2, _ = passes_copyright_prefilter({"title": "Song", "channel": "FanEdits", "duration": 22, "track": "Hit Song"})
    ok3, _ = passes_copyright_prefilter({"title": "Full Movie HD", "channel": "MoviesHub", "duration": 22})
    ok4, _ = passes_copyright_prefilter({"title": "Clip", "channel": "ArtistVEVO", "duration": 22})
    assert ok1 and not ok2 and not ok3 and not ok4, "Copyright pre-filter failed!"

    # 3. Royalty-free BGM synthesis check
    bgm = ensure_royalty_free_bgm("phonk")
    assert bgm.exists() and bgm.stat().st_size > 30_000, "BGM generation failed!"

    print("[SELF-TEST] ALL CHECKS PASSED (virality math, Anti-CID filter, royalty-free BGM).")
    return 0


def run_pipeline(
    fmt: str = "auto",
    topic: str | None = None,
    handle: str = "@CinePulse",
    dry_run: bool = True,
    count: int = 3,
    extra_urls: list[str] | None = None,
    browser_cookies: str = "",
) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = scan_virality(skip_yt=bool(topic))
    winner = report["winner"]

    chosen_topic = topic or winner["topic"]
    chosen_fmt = winner["recommended_format"] if fmt == "auto" else fmt
    print(f"\n[Pipeline] Topic='{chosen_topic}' | Format='{chosen_fmt}' | DryRun={dry_run}")

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
            # Extract compact movie/person query for crisp poster/still hit
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
        queries = [f"{chosen_topic} edit shorts", f"{chosen_topic} best scene edit shorts", f"{chosen_topic} moments edit"]
        clips = harvest_video_pack(
            queries, target_count=count, max_duration=65,
            extra_urls=extra_urls, browser_cookies=browser_cookies, required_topic=chosen_topic,
        )
        if not clips:
            raise RuntimeError(f"No clean copyright-safe clips harvested for '{chosen_topic}'")
        # Short punchy rank labels for the left ladder
        for i, c in enumerate(clips, 1):
            words = re.findall(r"[A-Za-z0-9]+", c["title"])
            c["short_label"] = " ".join(words[:2]).title() if words else f"Clip {i}"
        render_edit_ranking(chosen_topic, clips, out_mp4, handle=handle, clip_dur=10.0)

    elif chosen_fmt == "release_hype":
        queries = [f"{chosen_topic} trailer edit shorts", f"{chosen_topic} movie clip shorts"]
        clips = harvest_video_pack(queries, target_count=max(count, 4), max_duration=65, extra_urls=extra_urls, browser_cookies=browser_cookies)
        if not clips:
            raise RuntimeError(f"No clean clips harvested for release_hype '{chosen_topic}'")
        render_release_hype(f"THIS WEEK CAN'T HOLD THIS MUCH PEAK... ({chosen_topic})", clips, out_mp4, handle=handle)

    else:  # movie_trivia or scene_commentary
        is_triv = chosen_fmt == "movie_trivia"
        queries = [f"{chosen_topic} scene shorts", f"{chosen_topic} movie clip edit"]
        clips = harvest_video_pack(queries, target_count=3 if is_triv else 1, max_duration=65, extra_urls=extra_urls, browser_cookies=browser_cookies)
        if not clips:
            raise RuntimeError(f"No clean clips harvested for {chosen_fmt} '{chosen_topic}'")
        for c in clips:
            c["fact_or_commentary"] = c["title"][:60]
        render_movie_trivia_or_commentary(chosen_topic, clips, out_mp4, handle=handle, mode=chosen_fmt)

    qa = verify_video(out_mp4, make_proof=True)
    meta = build_metadata(chosen_topic, chosen_fmt, clips, handle=handle)
    meta_path = out_mp4.with_suffix(".meta.json")
    meta_path.write_text(json.dumps({"qa": qa, "metadata": meta}, indent=2, ensure_ascii=False), encoding="utf-8")

    upload_res = None
    if not dry_run:
        if not qa["passed"]:
            raise RuntimeError(f"QA Gate failed ({qa['issues']}); upload aborted.")
        upload_res = upload_private_canary_and_schedule(out_mp4, meta)

    print(f"[Pipeline] Done -> {out_mp4} | QA={'PASS' if qa['passed'] else 'FAIL'} | Proof={qa.get('proof_sheet')}")
    return {"video": str(out_mp4), "qa": qa, "metadata": meta, "upload": upload_res}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Virality-first Movies & Series Shorts Automation")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--format", default="auto", choices=["auto", "edit_ranking", "release_hype", "movie_trivia", "scene_commentary", "news_slideshow"])
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

    run_pipeline(
        fmt=args.format,
        topic=args.topic,
        handle=args.handle,
        dry_run=not args.upload,
        count=args.count,
        extra_urls=args.urls,
        browser_cookies=args.cookies_from_browser,
    )
