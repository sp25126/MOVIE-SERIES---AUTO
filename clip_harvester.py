"""Multi-platform clip & meme harvester (YouTube, Reddit, TikTok, IG/FB) with Anti-CID pre-filter."""

import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
STATE_DIR = ROOT / "state"
HISTORY_PATH = STATE_DIR / "used_history.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

BLOCKED_CHANNEL_TERMS = (
    "vevo", "official audio", "topic", "records", "music video", "t-series", "sony music",
    "screen culture", "kh studio", "teaserspro", "royal trailer", "dar trailer", "ai studio",
)
BANNED_TITLE_TERMS = (
    "full movie", "full episode", "official audio", "music video", "lyric video",
    "reaction", "live stream", "interview", "press conference", "happy diwali", "greeting",
    "concept", "fan made", "fan-made", "fanmade", "fan trailer", "unofficial",
    "ai trailer", "ai generated", "ai video", "made with ai", "parody", "spoof", "unreal engine",
    "kissing scene", "hot scene", "hot kissing", "sexy", "18+", "nude", "bold scene", "scenepack",
    "amv", "anime", "cyberpunk", "edgerunners",
)
FAKE_AI_DESC_TERMS = (
    "concept trailer", "fan-made", "fan made", "fanmade", "not an official", "unofficial trailer",
    "ai-generated", "ai generated", "made with ai", "created with ai", "generated using ai",
    "kling ai", "sora ai", "runway gen", "midjourney", "veo 2", "veo 3", "hailuo", "parody trailer",
)

MEME_SUBREDDITS = ("movies", "marvelmemes", "MovieDetails", "television", "bollywoodmemes", "PrequelMemes")


def _history_file() -> Path:
    import os
    custom = os.environ.get("CLIP_HISTORY_PATH", "").strip()
    return Path(custom) if custom else HISTORY_PATH


def _load_history() -> set[str]:
    hp = _history_file()
    if hp.exists():
        try:
            data = json.loads(hp.read_text(encoding="utf-8"))
            return set(data.get("used_clip_ids", data) if isinstance(data, dict) else data)
        except Exception:
            pass
    return set()


def _save_history(ids: set[str]):
    hp = _history_file()
    hp.parent.mkdir(parents=True, exist_ok=True)
    if hp.exists():
        try:
            cur = json.loads(hp.read_text(encoding="utf-8"))
            if isinstance(cur, dict) and "used_clip_ids" in cur:
                cur["used_clip_ids"] = sorted(ids)
                hp.write_text(json.dumps(cur, indent=2, ensure_ascii=False), encoding="utf-8")
                return
        except Exception:
            pass
    hp.write_text(json.dumps(sorted(ids)[-500:], indent=2), encoding="utf-8")


def passes_copyright_prefilter(meta: dict, min_duration: int = 4) -> tuple[bool, str]:
    """Rejects claimed music tracks, high-risk studio music channels, and fake AI/fan-concept trailers."""
    title = (meta.get("title") or "").lower()
    channel = (meta.get("channel") or meta.get("uploader") or "").lower()
    desc_tags = f"{meta.get('description') or ''} {' '.join(meta.get('tags') or [])}".lower()

    if meta.get("track") or meta.get("artist"):
        return False, f"Content-ID music detected ({meta.get('track')} / {meta.get('artist')})"
    if any(b in channel for b in BLOCKED_CHANNEL_TERMS):
        return False, f"Blocked music/concept channel ({channel})"
    if any(b in title for b in BANNED_TITLE_TERMS):
        return False, f"Blocked title term ({title[:40]})"
    if any(b in desc_tags for b in FAKE_AI_DESC_TERMS):
        return False, "Fake AI / fan-concept footage detected in description/tags"
    dur = meta.get("duration") or 0
    if dur < min_duration or dur > 180:
        return False, f"Duration out of bounds ({dur}s)"
    return True, "ok"


def scout_youtube(query: str, count: int = 5, max_duration: int = 65, min_duration: int = 5, ignore_history: bool = False) -> list[dict]:
    """Scouts YouTube via yt_dlp InnerTube/web extractor + Anti-CID pre-filter."""
    used = set() if ignore_history else _load_history()
    probe_n = max(count * 3, 12)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json", "--no-playlist", "--no-warnings",
        "--match-filter", f"duration <= {max_duration} & duration >= {min_duration}",
        f"ytsearch{probe_n}:{query}",
    ]
    candidates, seen = [], set()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=50)
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            vid = d.get("id")
            if not vid or vid in seen or vid in used or f"yt_{vid}" in used:
                continue
            seen.add(vid)
            ok, _ = passes_copyright_prefilter(d, min_duration=min_duration)
            if not ok:
                continue
            candidates.append({
                "id": f"yt_{vid}",
                "platform": "youtube",
                "title": d.get("title", ""),
                "creator": d.get("channel") or d.get("uploader") or "Creator",
                "views": int(d.get("view_count") or 0),
                "duration": float(d.get("duration") or 15),
                "url": d.get("webpage_url") or f"https://youtube.com/watch?v={vid}",
            })
    except Exception as e:
        print(f"[Harvester] YouTube scout skipped ({query[:30]}): {e}", file=sys.stderr)

    candidates.sort(key=lambda x: x["views"], reverse=True)
    return candidates[:count]


def scout_reddit_memes_and_clips(topic: str = "", count: int = 5, video_only: bool = False) -> list[dict]:
    """Scouts Reddit movie/series memes & clips from last 7d via ArcticShift public API (no 403/429)."""
    used = _load_history()
    results = []
    import time as _time
    after_ts = int(_time.time() - 7 * 86400)
    subs = MEME_SUBREDDITS[:4]
    for sub in subs:
        q_param = f"&title={urllib.parse.quote_plus(topic)}" if topic else ""
        url = f"https://arctic-shift.photon-reddit.com/api/posts/search?subreddit={sub}&after={after_ts}&limit=25&sort=desc{q_param}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MovieSeriesHarvester/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace")).get("data", [])
            for p in data:
                pid = f"rd_{p.get('id')}"
                if p.get("over_18") or pid in used:
                    continue
                is_vid = bool(p.get("is_video"))
                media_url = p.get("url_overridden_by_dest") or p.get("url") or ""
                is_img = bool(re.search(r"\.(jpg|jpeg|png|webp)$", media_url, re.I))
                if video_only and not is_vid:
                    continue
                if not is_vid and not is_img:
                    continue
                results.append({
                    "id": pid,
                    "platform": "reddit",
                    "media_type": "video" if is_vid else "image",
                    "title": p.get("title", ""),
                    "creator": f"u/{p.get('author', 'redditor')} (r/{p.get('subreddit', sub)})",
                    "views": int(p.get("score") or 0) * 100 + int(p.get("num_comments") or 0) * 300,
                    "duration": float((p.get("media") or {}).get("reddit_video", {}).get("duration") or 12),
                    "url": f"https://www.reddit.com{p.get('permalink', '')}" if is_vid else media_url,
                })
        except Exception as e:
            print(f"[Harvester] ArcticShift r/{sub} skipped: {e}", file=sys.stderr)
    results.sort(key=lambda x: x["views"], reverse=True)
    return results[:count]


def scout_tiktok_public(query: str, count: int = 3) -> list[dict]:
    """Scouts public TikTok edit clips via TikWM public search API (no auth bypass; falls back gracefully)."""
    used = _load_history()
    results = []
    try:
        body = urllib.parse.urlencode({"keywords": query, "count": max(count * 2, 6)}).encode("utf-8")
        req = urllib.request.Request(
            "https://www.tikwm.com/api/feed/search",
            data=body,
            headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        for item in (data.get("data") or {}).get("videos", []):
            vid = f"tt_{item.get('video_id')}"
            dur = float(item.get("duration") or 0)
            if vid in used or dur < 5 or dur > 65:
                continue
            play_url = item.get("play") or item.get("wmplay")
            if not play_url:
                continue
            author = (item.get("author") or {}).get("unique_id") or "tiktok_creator"
            results.append({
                "id": vid,
                "platform": "tiktok",
                "title": (item.get("title") or query)[:90],
                "creator": f"@{author}",
                "views": int(item.get("play_count") or 0),
                "duration": dur,
                "url": play_url,
                "direct_mp4": True,
            })
    except Exception as e:
        print(f"[Harvester] TikTok public API skipped ({query[:24]}): {e}", file=sys.stderr)
    results.sort(key=lambda x: x["views"], reverse=True)
    return results[:count]


def download_social_url(url: str, tag_id: str, out_dir: Path | None = None, browser_cookies: str = "") -> Path | None:
    """Downloads a public YouTube, TikTok, Reddit, Instagram Reel, or Facebook Watch video via yt_dlp."""
    # shortcut: IG/FB public reels sometimes require local browser session cookies (--cookies-from-browser chrome)
    target_dir = out_dir or INPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", tag_id)[:48]
    out_mp4 = target_dir / f"{safe_id}.mp4"
    if out_mp4.exists() and out_mp4.stat().st_size > 20_000:
        return out_mp4

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--no-warnings",
        "-o", str(target_dir / f"{safe_id}.%(ext)s"),
    ]
    if browser_cookies:
        cmd.extend(["--cookies-from-browser", browser_cookies])
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
        if proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
            used = _load_history()
            used.add(tag_id)
            _save_history(used)
            return out_mp4
        print(f"[Harvester] Download failed ({safe_id}): {proc.stderr[:180]}", file=sys.stderr)
    except Exception as e:
        print(f"[Harvester] Download exception ({safe_id}): {e}", file=sys.stderr)
    return None


def download_clip(candidate: dict, out_dir: Path | None = None, browser_cookies: str = "") -> Path | None:
    target_dir = out_dir or INPUT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^A-Za-z0-9_\-]", "_", candidate["id"])[:48]
    out_mp4 = target_dir / f"{safe_id}.mp4"
    if out_mp4.exists() and out_mp4.stat().st_size > 20_000:
        return out_mp4

    if candidate.get("direct_mp4"):
        try:
            req = urllib.request.Request(candidate["url"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                out_mp4.write_bytes(resp.read())
            if out_mp4.stat().st_size > 20_000:
                used = _load_history()
                used.add(candidate["id"])
                _save_history(used)
                return out_mp4
        except Exception as e:
            print(f"[Harvester] Direct MP4 download skipped ({safe_id}): {e}", file=sys.stderr)
            return None

    return download_social_url(candidate["url"], candidate["id"], target_dir, browser_cookies=browser_cookies)


def _matches_topic(candidate: dict, required_topic: str) -> bool:
    if not required_topic:
        return True
    hay = f"{candidate.get('title', '')} {candidate.get('creator', '')}".lower()
    tokens = [t for t in re.findall(r"[a-z0-9]+", required_topic.lower()) if len(t) >= 3]
    if not tokens:
        return True
    # Require all tokens for 1-2 word names (e.g. "Patrick Jane" must match both, not just "Jane")
    return all(t in hay for t in tokens) if len(tokens) <= 2 else (sum(1 for t in tokens if t in hay) >= 2)


def scout_fb_ig_fallback(query: str, count: int = 3) -> list[dict]:
    """Fallback scout discovering public Instagram Reels & Facebook Reels/Watch links via RSS/search index."""
    used = _load_history()
    results = []
    for platform, site_q in (
        ("instagram", f"site:instagram.com/reel {query}"),
        ("facebook", f"(site:facebook.com/reel OR site:facebook.com/watch) {query}"),
    ):
        try:
            url = "https://www.bing.com/search?format=rss&q=" + urllib.parse.quote_plus(site_q)
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            import xml.etree.ElementTree as ET
            for item in ET.fromstring(xml_text).findall(".//item")[:count * 3]:
                link = (item.findtext("link") or "").strip()
                title = (item.findtext("title") or query).strip()
                if f"{platform}.com/" not in link.lower():
                    continue
                cid = f"{platform[:2]}_{abs(hash(link)) % 1000000}"
                if link and cid not in used:
                    results.append({
                        "id": cid, "platform": platform, "title": title[:90],
                        "creator": f"{platform.title()} Creator", "views": 1000,
                        "duration": 15.0, "url": link,
                    })
        except Exception as e:
            print(f"[Harvester] {platform} fallback skipped: {e}", file=sys.stderr)
    return results[:count]


def harvest_video_pack(
    queries: list[str],
    target_count: int = 3,
    max_duration: int = 65,
    min_duration: int = 5,
    platforms: tuple[str, ...] = ("youtube", "tiktok", "reddit", "facebook", "instagram"),
    extra_urls: list[str] | None = None,
    browser_cookies: str = "",
    required_topic: str = "",
) -> list[dict]:
    """Harvests N distinct copyright-screened clips across YouTube, TikTok, Reddit, and optional IG/FB URLs."""
    picked, seen_ids = [], set()

    # Optional explicit Instagram/Facebook/TikTok/YouTube URLs supplied by user or scout
    for idx, u in enumerate(extra_urls or [], 1):
        if len(picked) >= target_count:
            break
        cid = f"url_{idx}_{abs(hash(u)) % 100000}"
        path = download_social_url(u, cid, browser_cookies=browser_cookies)
        if path:
            picked.append({
                "id": cid, "platform": "social_url", "title": f"Clip {idx}",
                "creator": "Social Creator", "views": 0, "duration": 15.0,
                "url": u, "local_path": str(path),
            })
            seen_ids.add(cid)

    pool: list[dict] = []
    for q in queries:
        if "youtube" in platforms:
            pool.extend(scout_youtube(q, count=target_count * 2, max_duration=max_duration, min_duration=min_duration))
        if "tiktok" in platforms and len(pool) < target_count * 2:
            pool.extend(scout_tiktok_public(q, count=target_count))
        if "reddit" in platforms and len(pool) < target_count * 2:
            pool.extend(scout_reddit_memes_and_clips(q, count=target_count, video_only=True))
        if ("facebook" in platforms or "instagram" in platforms) and len(pool) < target_count:
            pool.extend(scout_fb_ig_fallback(q, count=target_count))

    pool.sort(key=lambda x: x.get("views", 0), reverse=True)
    for c in pool:
        if len(picked) >= target_count:
            break
        if c["id"] in seen_ids or not _matches_topic(c, required_topic):
            continue
        path = download_clip(c, browser_cookies=browser_cookies)
        if path:
            seen_ids.add(c["id"])
            c["local_path"] = str(path)
            picked.append(c)
            print(f"[Harvester] Ready ({len(picked)}/{target_count}) [{c['platform']}]: {c['title'][:50]} [{c['views']:,}]")
    return picked


def fetch_trending_bgm(style: str = "phonk", out_dir: Path | None = None) -> Path | None:
    """Downloads a real trending no-copyright BGM track via yt_dlp (verified no CID track/artist tag)."""
    bgm_dir = out_dir or (ROOT / "assets" / "bgm")
    bgm_dir.mkdir(parents=True, exist_ok=True)
    out_wav = bgm_dir / f"trending_{style}.wav"
    if out_wav.exists() and out_wav.stat().st_size > 200_000:
        return out_wav

    queries = {
        "phonk": [
            "no copyright brazilian phonk slowed reverb edit bgm",
            "copyright free phonk montage edit music 2026",
        ],
        "rock": ["no copyright dark cinematic rock trailer music"],
        "ambient": ["no copyright dark ambient slowed reverb edit music"],
    }.get(style, ["no copyright viral edit music"])

    for q in queries:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json", "--no-playlist", "--no-warnings",
            "--match-filter", "duration >= 25 & duration <= 240",
            f"ytsearch8:{q}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
            cands = []
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                # Must have NO detected commercial music track/artist claim metadata
                if d.get("track") or d.get("artist"):
                    continue
                if any(b in (d.get("channel") or "").lower() for b in BLOCKED_CHANNEL_TERMS):
                    continue
                cands.append((int(d.get("view_count") or 0), d.get("webpage_url") or "", d.get("title") or ""))
            cands.sort(reverse=True)
            for views, url, title in cands[:3]:
                if not url:
                    continue
                dl = subprocess.run(
                    [
                        sys.executable, "-m", "yt_dlp", "-f", "bestaudio/best",
                        "-x", "--audio-format", "wav", "--no-warnings",
                        "-o", str(bgm_dir / f"trending_{style}.%(ext)s"), url,
                    ],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                )
                if dl.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 200_000:
                    print(f"[BGM] Ready ({style}): {title[:55]} [{views:,} views] -> {out_wav.name}")
                    return out_wav
        except Exception as e:
            print(f"[BGM] Fetch skipped ({q[:30]}): {e}", file=sys.stderr)
    return None


def harvest_intro_hook(topic: str, hook_url: str = "", browser_cookies: str = "", exclude_ids: set[str] | None = None) -> dict | None:
    """Gets a 3s high-retention intro edit hook (explicit IG Reel URL -> local assets/hooks -> live viral edit)."""
    excluded = exclude_ids or set()
    # 1. Explicit Instagram Reel / TikTok / YouTube hook URL
    if hook_url:
        p = download_social_url(hook_url, f"hook_{abs(hash(hook_url)) % 100000}", browser_cookies=browser_cookies)
        if p:
            return {"id": "custom_hook", "platform": "instagram", "title": f"{topic} Hook Edit", "creator": "IG Creator", "url": hook_url, "local_path": str(p), "duration": 10.0}

    # 2. Local dropped Instagram reels in assets/hooks/ (auto-rotates)
    hooks_dir = ROOT / "assets" / "hooks"
    if hooks_dir.exists():
        local_hooks = sorted(hooks_dir.glob("*.mp4"))
        if local_hooks:
            chosen = local_hooks[abs(hash(topic)) % len(local_hooks)]
            return {"id": chosen.stem, "platform": "local_ig_hook", "title": chosen.stem, "creator": "IG Hook", "url": "", "local_path": str(chosen), "duration": 10.0}

    # 3. Autonomous viral edit hook (distinct from main clips)
    hook_queries = [f"{topic} edit 4k shorts", f"{topic} instagram reel edit", f"{topic} viral edit"]
    found = harvest_video_pack(
        hook_queries, target_count=3, max_duration=45,
        platforms=("instagram", "tiktok", "youtube"),
        browser_cookies=browser_cookies, required_topic=topic,
    )
    for item in found:
        if item["id"] not in excluded:
            print(f"[Hook] Auto-selected distinct viral edit hook: {item['title'][:55]}")
            return item
    return None
