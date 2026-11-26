"""Multi-platform clip & meme harvester (YouTube, Reddit, TikTok, IG/FB) with Anti-CID pre-filter."""

import json
import re
import shutil
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
    "tutorial", "how to", "editing pack", "capcut template", "download link", "battle", "prize",
    "worst ai", "editor award", "behind the scenes", "making of", "vlog",
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


CID_DESC_TERMS = (
    "licensed to youtube by", "provided to youtube by", "music in this video",
    "universal music", "warner music", "sony music", "umg", "wmg", "sme",
)
YT_HTML_CID_MARKERS = (
    "videoDescriptionMusicSectionRenderer",
    "Licensed to YouTube by",
    "musicWatchMetadataRenderer",
)


def has_youtube_cid_claim(video_id: str) -> tuple[bool, str]:
    """Probes YouTube watch HTML for active Content-ID music/claim cards before downloading."""
    try:
        req = urllib.request.Request(f"https://www.youtube.com/watch?v={video_id}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=3) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        for m in YT_HTML_CID_MARKERS:
            if m in html:
                return True, f"YouTube CID marker '{m}'"
    except Exception:
        pass
    return False, "clean"


RAW_EPISODE_MARKERS = (
    re.compile(r"\b\d{1,2}x\d{1,2}\b", re.I),           # e.g. 07x01, 1x05
    re.compile(r"\bs(?:eason)?\s*\d{1,2}\b", re.I),     # e.g. season 7, s07
    re.compile(r"\be(?:pisode)?\s*\d{1,2}\b", re.I),    # e.g. episode 1, ep 02, ep6
    re.compile(r"\bpart\s*\d{1,2}\b", re.I),            # e.g. part 05
)

RAW_SCENE_DISQUALIFIERS = (
    "full scene", "deleted scene", "clip from", "scene from", "slapping scene",
    "funny scene", "death scene", "ending scene", "opening scene", "promo",
    "teaser trailer", "official promo", "behind the scenes", "bloopers",
    "interview", "once said", "compilation of", "compilation |", "tv series clip",
    "scene pack", "scenepack", "raw clip", "dialogue scene", "clip compilation",
    "quotes", "thought jane is", "trying to seduce", "threatens", "talks to",
    "confronts", "interrogates", "interrogation", "confession", "arrests",
    "shoots", "kills", "reaction", "review", "recap", "explained", "summary",
    "best lines", "iconic scene", "movie scene", "series scene", "bloopers",
)

FAN_EDIT_TITLE_TERMS = (
    "edit", "edits", "editz", "velocity", "amv", "fmv", "montage", "alight motion",
    "after effects", "capcut", "phonk", "hd60fps", "60fps", "remix", "status",
    "badass edit", "sigma edit", "cold edit", "audio edit", "loop edit",
)

SOCIAL_EDIT_HASHTAGS = (
    "#edit", "#edits", "#velocity", "#capcut", "#alightmotion", "#phonk",
    "#reels", "#tiktok", "#tiktokedit", "#instareels", "#sigma", "#badass",
)

RAW_WORD_PATTERNS = (
    re.compile(r"\bscenes?\b", re.I),
    re.compile(r"\bclips?\b", re.I),
    re.compile(r"\bmoments?\b", re.I),
)


def is_genuine_fan_edit(meta: dict) -> tuple[bool, str]:
    """Automated strict deterministic rule gate: ensures only real creator edits pass (from YouTube, TikTok, Instagram)
    and strictly rejects raw show scenes, TV cutdowns, and quote compilations."""
    title = (meta.get("title") or "").lower()
    desc = (meta.get("description") or "").lower()
    tags = f"{' '.join(meta.get('tags') or [])} {desc}".lower()
    if meta.get("platform") in ("instagram", "tiktok"):
        tags += " #edit #reels #tiktok edit"

    # 1. Reject explicit scene / raw dialogue / review disqualifiers in title
    for dis in RAW_SCENE_DISQUALIFIERS:
        if dis in title:
            return False, f"Disqualified raw scene term: '{dis}'"

    # 2. Check for explicit edit markers in title
    has_edit_in_title = any(re.search(rf"\b{re.escape(term)}\b", title) for term in FAN_EDIT_TITLE_TERMS)

    # 3. Reject raw scene/clip/moment indicators unless explicit edit term is in title
    for pat in RAW_WORD_PATTERNS:
        if pat.search(title) and not has_edit_in_title:
            return False, f"Disqualified: raw scene indicator '{pat.pattern}' without edit in title"

    # 4. Reject raw TV season/episode markers unless explicit edit indicator is in title
    for pat in RAW_EPISODE_MARKERS:
        if pat.search(title) and not has_edit_in_title:
            return False, f"Disqualified: raw episode marker '{pat.pattern}' without edit tag"

    # 5. Mandatory edit signature: title or tags MUST have an edit term or social edit hashtag
    has_social_tag = any(ht in title or ht in tags for ht in SOCIAL_EDIT_HASHTAGS)
    has_edit_in_tags = any(re.search(rf"\b{re.escape(term)}\b", tags) for term in FAN_EDIT_TITLE_TERMS)

    if not (has_edit_in_title or has_social_tag or has_edit_in_tags):
        return False, "Disqualified: missing mandatory fan edit signature (not a creator edit)"

    return True, "ok"


def passes_copyright_prefilter(meta: dict, min_duration: int = 4, check_html: bool = False) -> tuple[bool, str]:
    """Rejects claimed music tracks, active YouTube CID cards, studio music channels, and fake AI trailers."""
    title = (meta.get("title") or "").lower()
    channel = (meta.get("channel") or meta.get("uploader") or "").lower()
    desc = (meta.get("description") or "").lower()
    desc_tags = f"{desc} {' '.join(meta.get('tags') or [])}".lower()

    if meta.get("track") or meta.get("artist") or meta.get("album"):
        return False, f"Content-ID music detected ({meta.get('track')} / {meta.get('artist')})"
    if any(b in channel for b in BLOCKED_CHANNEL_TERMS):
        return False, f"Blocked music/concept channel ({channel})"
    if any(b in title for b in BANNED_TITLE_TERMS):
        return False, f"Blocked title term ({title[:40]})"
    if any(b in desc_tags for b in FAKE_AI_DESC_TERMS):
        return False, "Fake AI / fan-concept footage detected in description/tags"
    if any(c in desc for c in CID_DESC_TERMS):
        return False, "Commercial music / Content-ID credit detected in description"
    dur = meta.get("duration") or 0
    if dur < min_duration or dur > 180:
        return False, f"Duration out of bounds ({dur}s)"
    if check_html and meta.get("id"):
        claimed, why = has_youtube_cid_claim(meta["id"])
        if claimed:
            return False, why
    return True, "ok"


def scout_youtube(query: str, count: int = 5, max_duration: int = 65, min_duration: int = 5, ignore_history: bool = False) -> list[dict]:
    """Scouts YouTube via yt_dlp InnerTube/web extractor + Anti-CID pre-filter."""
    used = set() if ignore_history else _load_history()
    probe_n = max(count * 8, 35)
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json", "--no-playlist", "--no-warnings",
        "--match-filter", f"duration <= {max_duration} & duration >= {min_duration}",
        f"ytsearch{probe_n}:{query}",
    ]
    candidates, seen = [], set()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
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
            views = int(d.get("view_count") or 0)
            # Enforce virality threshold: ranking edits must have meaningful views (at least 500 views)
            if views < 500:
                continue
            ok, _ = passes_copyright_prefilter(d, min_duration=min_duration, check_html=False)
            if not ok:
                continue
            is_edit, why_edit = is_genuine_fan_edit(d)
            if not is_edit:
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
    # Perform final HTML Content-ID check on the top candidates only
    verified = []
    for c in candidates:
        vid_raw = c["id"].replace("yt_", "")
        claimed, _ = has_youtube_cid_claim(vid_raw)
        if not claimed:
            verified.append(c)
        if len(verified) >= count:
            break
    return verified


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


def scout_instagram_reels(query: str, count: int = 3, ignore_history: bool = False) -> list[dict]:
    """Scouts viral Instagram Reels for edits using multi-engine discovery (agent-reach + DDG Lite) + yt-dlp metadata."""
    used = set() if ignore_history else _load_history()
    discovered_urls = []
    clean_q = re.sub(r"[#@]", "", query).strip()

    # 1. Primary Engine: agent-reach web search (Exa index) if CLI is available
    if shutil.which("agent-reach"):
        try:
            cmd = ["agent-reach", "web", "search", f"{clean_q} edit instagram reel", "--limit", str(count * 3)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=8)
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                for item in data.get("items", []):
                    blob = f"{item.get('text', '')} {item.get('url', '')}"
                    found = re.findall(r'https?://(?:www\.)?instagram\.com/(?:[a-zA-Z0-9_\.]+/)?reel/([a-zA-Z0-9_\-]+)', blob)
                    for code in found:
                        u = f"https://www.instagram.com/reel/{code}/"
                        if u not in discovered_urls:
                            discovered_urls.append(u)
        except Exception as e:
            print(f"[Harvester] Instagram scout agent-reach skipped: {e}", file=sys.stderr)

    # 2. Redundant Engine: DuckDuckGo Lite search for instagram.com/reel
    if len(discovered_urls) < count:
        try:
            url = "https://lite.duckduckgo.com/lite/"
            body = urllib.parse.urlencode({"q": f"site:instagram.com/reel {clean_q} edit"}).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=4) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                for code in re.findall(r'instagram\.com/reel/([a-zA-Z0-9_\-]+)', html):
                    u = f"https://www.instagram.com/reel/{code}/"
                    if u not in discovered_urls:
                        discovered_urls.append(u)
        except Exception as e:
            print(f"[Harvester] Instagram DDG Lite skipped: {e}", file=sys.stderr)

    candidates, seen = [], set()
    for u in discovered_urls:
        if len(candidates) >= count:
            break
        code = u.rstrip("/").split("/")[-1]
        cid = f"ig_{code}"
        if cid in used or cid in seen:
            continue
        seen.add(cid)
        meta_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json", "--no-warnings", u
        ]
        try:
            p = subprocess.run(meta_cmd, capture_output=True, text=True, encoding="utf-8", timeout=15)
            if p.returncode == 0 and p.stdout.strip():
                d = json.loads(p.stdout)
                dur = float(d.get("duration") or 15.0)
                if 5.0 <= dur <= 65.0:
                    creator = d.get("uploader") or d.get("channel") or "Instagram Creator"
                    views = int(d.get("view_count") or d.get("like_count") or 1500) * 8
                    candidates.append({
                        "id": cid,
                        "platform": "instagram",
                        "title": d.get("title") or f"{clean_q} Instagram Edit",
                        "creator": f"@{creator.replace(' ', '')} (Insta)" if not creator.startswith("@") else f"{creator} (Insta)",
                        "views": views,
                        "duration": dur,
                        "url": u,
                    })
        except Exception:
            continue

    return candidates


def scout_tiktok_videos(query: str, count: int = 3, ignore_history: bool = False) -> list[dict]:
    """Scouts viral TikTok edits via multi-engine discovery (agent-reach + TikWM mirror) + direct metadata."""
    used = set() if ignore_history else _load_history()
    clean_q = re.sub(r"[#@]", "", query).strip()
    discovered = []

    # 1. Primary Engine: agent-reach web search if CLI is available
    if shutil.which("agent-reach"):
        try:
            cmd = ["agent-reach", "web", "search", f"{clean_q} edit tiktok video", "--limit", str(count * 3)]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=8)
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                for item in data.get("items", []):
                    blob = f"{item.get('text', '')} {item.get('url', '')}"
                    found_ids = re.findall(r'(?:tiktok\.com/@[^/]+/video/|toklytics\.app/video/|/video/)(\d{15,22})', blob)
                    author = item.get("author") or "tiktok_creator"
                    views = 25000
                    vm = re.search(r'([\d\.]+)M\s+Views', blob, re.I)
                    if vm:
                        views = int(float(vm.group(1)) * 1_000_000)
                    vk = re.search(r'([\d\.]+)K\s+Views', blob, re.I)
                    if vk:
                        views = int(float(vk.group(1)) * 1_000)
                    for tid in found_ids:
                        u = f"https://www.tiktok.com/video/{tid}"
                        if tid not in [x[0] for x in discovered]:
                            discovered.append((tid, u, item.get("title") or f"{clean_q} TikTok Edit", author, views))
        except Exception as e:
            print(f"[Harvester] TikTok scout agent-reach skipped: {e}", file=sys.stderr)

    candidates, seen = [], set()
    for tid, u, title, author, views in discovered:
        if len(candidates) >= count:
            break
        cid = f"tt_{tid}"
        if cid in used or cid in seen:
            continue
        seen.add(cid)
        candidates.append({
            "id": cid,
            "platform": "tiktok",
            "title": title[:90],
            "creator": f"@{author.replace(' ', '')} (TikTok)" if not author.startswith("@") else f"{author} (TikTok)",
            "views": views,
            "duration": 20.0,
            "url": u,
        })

    return candidates


def scout_tiktok_public(query: str, count: int = 3) -> list[dict]:
    """Compatibility wrapper dispatching to scout_tiktok_videos."""
    return scout_tiktok_videos(query, count=count)


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
        "--retries", "1",
        "--fragment-retries", "1",
        "--socket-timeout", "5",
        "-o", str(target_dir / f"{safe_id}.%(ext)s"),
    ]
    if browser_cookies:
        cmd.extend(["--cookies-from-browser", browser_cookies])
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
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


def _matches_topic(candidate: dict, required_topic: str, allowed_entities: list[str] | None = None) -> bool:
    if not required_topic and not allowed_entities:
        return True
    hay = f"{candidate.get('title', '')} {candidate.get('creator', '')} {candidate.get('description', '')}".lower()
    if candidate.get("platform") in ("instagram", "tiktok") and any(t in hay for t in [ent.lower() for ent in (allowed_entities or [required_topic])]):
        return True

    # Check ensemble / allowed character entities first (e.g. Kimball Cho, Teresa Lisbon, Patrick Jane)
    if allowed_entities:
        for ent in allowed_entities:
            ent_tokens = [t for t in re.findall(r"[a-z0-9]+", ent.lower()) if len(t) >= 3]
            if ent_tokens and all(t in hay for t in ent_tokens):
                return True

    clean_req = re.sub(r"\b(?:Ep|Episode|Season|Part|Vol)\.?\s*\d+\b", "", required_topic, flags=re.I).strip()
    tokens = [t for t in re.findall(r"[a-z0-9]+", (clean_req or required_topic).lower()) if len(t) >= 3]
    if not tokens:
        return True
    # Require at least 1 primary franchise token to match
    return any(t in hay for t in tokens)


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
    niche_context: str = "Live-Action Movies, Series & Cinema",
    allowed_entities: list[str] | None = None,
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
            pool.extend(scout_youtube(q, count=target_count, max_duration=max_duration, min_duration=min_duration))
        if len(pool) >= target_count * 2:
            break
        if "instagram" in platforms:
            pool.extend(scout_instagram_reels(q, count=2))
        if "tiktok" in platforms:
            pool.extend(scout_tiktok_videos(q, count=2))
        if len(pool) >= target_count * 3:
            break

    # Multi-Platform interleaving: balance candidates across Instagram, TikTok, and YouTube
    by_platform: dict[str, list[dict]] = {}
    for c in pool:
        plat = c.get("platform", "youtube")
        by_platform.setdefault(plat, []).append(c)
    for plat in by_platform:
        by_platform[plat].sort(key=lambda x: x.get("views", 0), reverse=True)

    interleaved = []
    max_len = max((len(v) for v in by_platform.values()), default=0)
    for i in range(max_len):
        for plat in ("youtube", "instagram", "reddit", "facebook", "tiktok"):
            if plat in by_platform and i < len(by_platform[plat]):
                interleaved.append(by_platform[plat][i])

    for c in interleaved:
        if len(picked) >= target_count:
            break
        if c["id"] in seen_ids or not _matches_topic(c, required_topic, allowed_entities):
            continue
        is_edit, why_edit = is_genuine_fan_edit(c)
        if not is_edit:
            print(f"[Harvester] Rule Rejected non-edit ({c['id']}): {why_edit}")
            continue
        path = download_clip(c, browser_cookies=browser_cookies)
        if path:
            seen_ids.add(c["id"])
            c["local_path"] = str(path)
            picked.append(c)
            print(f"[Harvester] Ready ({len(picked)}/{target_count}) [{c['platform'].upper()}]: {c['title'][:50]} [{c['views']:,}]")

    # Automatic expansion if we still need clips to hit target_count
    if len(picked) < target_count and required_topic:
        print(f"[Harvester] Target count {target_count} not reached ({len(picked)} picked). Expanding queries...")
        entities = allowed_entities or [required_topic]
        expansion_queries = []
        for ent in entities:
            expansion_queries.extend([
                f"{ent} edit #shorts",
                f"{ent} edit shorts",
                f"{ent} badass edit #shorts",
                f"{ent} cold edit #shorts",
                f"{ent} sigma edit #shorts",
                f"{ent} 4k edit #shorts",
                f"The Mentalist {ent} edit shorts" if "Mentalist" not in ent else f"{ent} edit shorts",
            ])
        exp_pool = []
        for eq in expansion_queries:
            if len(picked) + len(exp_pool) >= target_count * 3:
                break
            if "instagram" in platforms:
                exp_pool.extend(scout_instagram_reels(eq, count=2))
            if "tiktok" in platforms:
                exp_pool.extend(scout_tiktok_videos(eq, count=2))
            if "youtube" in platforms:
                exp_pool.extend(scout_youtube(eq, count=3, max_duration=max_duration, min_duration=min_duration))
        exp_pool.sort(key=lambda x: x.get("views", 0), reverse=True)
        for c in exp_pool:
            if len(picked) >= target_count:
                break
            if c["id"] in seen_ids or not _matches_topic(c, required_topic, allowed_entities):
                continue
            is_edit, why_edit = is_genuine_fan_edit(c)
            if not is_edit:
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
                # Must have NO commercial music metadata AND NO active YouTube Content-ID card
                if d.get("track") or d.get("artist") or d.get("album"):
                    continue
                if any(b in (d.get("channel") or "").lower() for b in BLOCKED_CHANNEL_TERMS):
                    continue
                if d.get("id") and has_youtube_cid_claim(d["id"])[0]:
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
