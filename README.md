# MOVIE-SERIES---AUTO

Virality-first YouTube Shorts automation for the **Movies & Series** niche.

## Pipeline (6 Modules)
1. `virality_radar.py` — Multi-horizon virality scanner (**3-day 40%**, **7-day 30%**, **30-day 20%**, **1-year evergreen 10%**) using Wikimedia Pageviews, Reddit JSON, Google News RSS, live YouTube Shorts VPH velocity (`yt_dlp`), and optional `TMDB_API_KEY`.
2. `clip_harvester.py` — Candidate scout + **Anti-Content-ID pre-filter** (rejects claimed music `track`/`artist`, Vevo/Official Audio, duplicates via `state/used_history.json`) + micro-clip trim + still/poster fetcher.
3. `dsp_renderer.py` — Pure FFmpeg + Pillow 1080×1920 @ 30fps renderer across 4 viral formats (`edit_ranking`, `release_hype`, `movie_trivia` / `scene_commentary`, `news_slideshow`) with 4-layer copyright shield (micro-cuts, dual-layer framing, LUT, two-stage 48 kHz pitch/tempo modulation, royalty-free BGM, EBU R128 `-14 LUFS`).
4. `qa_gate.py` — Automated stream audit (`blackdetect`, video/audio duration parity `<0.15s`, resolution/sample-rate check, 5×3 visual proof sheet).
5. `metadata_uploader.py` — High-CTR title, pinned debate comment, trending tags, Section 107 fair-use credits, and optional `private`-first YouTube Data API v3 canary scheduler (`7:30 PM IST / 14:00 UTC`).
6. `run_pipeline.py` — Single CLI entrypoint.

## Quick Start
```powershell
# Run self-checks
py run_pipeline.py --self-test

# Live multi-horizon virality scan
py virality_radar.py

# End-to-end local dry-run (auto-picks winning trending movie/series & format)
py run_pipeline.py --format auto --dry-run

# Force a specific format
py run_pipeline.py --format edit_ranking --topic "Patrick Jane" --dry-run
py run_pipeline.py --format news_slideshow --dry-run
py run_pipeline.py --format release_hype --dry-run
py run_pipeline.py --format movie_trivia --dry-run
```
