"""Social-first Movies & Series virality engine: YouTube (Week/Month by views), Reddit (ArcticShift), IG/FB/News buzz."""

import datetime
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
REPORT_PATH = STATE_DIR / "virality_report.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# YouTube native protobuf sp filters (Videos sorted by View Count)
YT_SP_WEEK_VIEWS = "CAMSBAgDEAE%3D"
YT_SP_MONTH_VIEWS = "CAMSBAgEEAE%3D"

EVERGREEN_POOL = [
    {"topic": "Patrick Jane", "format": "edit_ranking", "evergreen": 95},
    {"topic": "Spider-Man", "format": "edit_ranking", "evergreen": 92},
    {"topic": "Breaking Bad", "format": "edit_ranking", "evergreen": 90},
    {"topic": "Malcolm in the Middle", "format": "scene_commentary", "evergreen": 88},
    {"topic": "Most Expensive Movie Scenes", "format": "movie_trivia", "evergreen": 86},
]

NON_MOVIE_JUNK = (
    "free fire", "ff edit", "bgmi", "pubg", "gta", "minecraft", "roblox", "valorant",
    "fortnite", "cricket", "football", "ronaldo", "messi", "car edit", "supra", "bmw",
    "tung tung", "skibidi", "cocomelon", "asmr", "slime",
)

STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "how", "why",
    "new", "official", "trailer", "teaser", "clip", "clips", "review", "box", "office", "movie",
    "movies", "series", "show", "shows", "season", "episode", "finale", "watch", "streaming",
    "netflix", "disney", "marvel", "mcu", "hbo", "amazon", "prime", "apple", "release", "date",
    "news", "update", "first", "look", "cast", "star", "director", "part", "one", "two", "three",
    "best", "top", "worst", "full", "hd", "4k", "60fps", "shorts", "short", "edit", "edits",
    "viral", "trending", "ranking", "rank", "scene", "scenes", "worldwide", "post", "credits",
    "beats", "beginner", "audiences", "hollywood", "bollywood", "cinema", "film", "films",
    "theaters", "report", "says", "after", "before", "will", "could", "would", "most", "more",
    "than", "into", "over", "about", "variety", "collider", "deadline", "screenrant", "imdb",
    "youtube", "instagram", "facebook", "reels", "tiktok", "fyp", "status", "meme", "memes",
    "funny", "sad", "cold", "coldest", "epic", "insane", "crazy", "moments", "moment", "video",
    "videos", "love", "trend", "whatsapp", "attitudestatus", "attitude", "scenepack", "twixtor",
    "aftereffects", "capcut", "alightmotion", "phonk", "slowed", "reverb", "actress", "actor",
    "bollywoodnews", "hollywoodnews", "movienews", "tvshow", "tvshows", "webseries", "movieclips",
    "spoiler", "spoilers", "discussion", "megathread", "thread", "officialdiscussion", "question",
    "anyone", "else", "just", "watched", "finished", "thought", "thoughts", "opinion", "unpopular",
    "indian", "hindi", "tamil", "telugu", "english", "dubbed", "subbed", "2025", "2026", "2027",
}

# Normalize popular hashtags / shorthands into clean canonical titles
HASHTAG_ALIASES = {
    "visionquest": "VisionQuest",
    "avengersdoomsday": "Avengers: Doomsday",
    "doomsday": "Avengers: Doomsday",
    "doctordoom": "Doctor Doom",
    "drdoom": "Doctor Doom",
    "ramayana": "Ramayana",
    "spidermanbrandnewday": "Spider-Man: Brand New Day",
    "spidermanbnd": "Spider-Man: Brand New Day",
    "spiderman": "Spider-Man",
    "theodyssey": "The Odyssey",
    "jailer2": "Jailer 2",
    "dexterresurrection": "Dexter: Resurrection",
    "dexter": "Dexter",
    "strangerthings": "Stranger Things",
    "supergirl": "Supergirl",
    "superman": "Superman",
    "thebatman": "The Batman",
    "batman": "Batman",
    "breakingbad": "Breaking Bad",
    "thementalist": "The Mentalist",
    "patrickjane": "Patrick Jane",
    "godzillaminuszero": "Godzilla Minus Zero",
    "bladerunner2099": "Blade Runner 2099",
    "percyjackson": "Percy Jackson",
    "salaar": "Salaar",
    "kannappa": "Kannappa",
    "yellowjackets": "Yellowjackets",
    "daredevil": "Daredevil",
    "theboys": "The Boys",
    "peakyblinders": "Peaky Blinders",
    "interstellar": "Interstellar",
    "scarletwitch": "Scarlet Witch",
    "ultron": "Ultron",
    "loki": "Loki",
    "deadpool": "Deadpool",
}


def _http_get(url: str, timeout: int = 10, ua: str = UA) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "application/json,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def compute_vph_score(views: float, age_hours: float, channel_subs: float = 50000.0) -> float:
    """Virality velocity: VPH * recency decay * small-channel leverage."""
    age = max(0.5, float(age_hours))
    vph = float(views) / age
    recency = math.exp(-0.012 * min(age, 168.0))
    baseline = max(1000.0, float(channel_subs or 50000.0) * 0.25)
    leverage = min(5.0, max(1.0, float(views) / baseline))
    return round(vph * recency * leverage, 2)


def compute_multi_horizon_score(h3d: float, h7d: float, h30d: float, h365d: float) -> float:
    """Weighted virality formula: 40% 3-day spike, 30% 7-day, 20% 30-day, 10% 1-year."""
    return round(0.40 * h3d + 0.30 * h7d + 0.20 * h30d + 0.10 * h365d, 2)


def _clean_title(raw: str) -> str:
    s = raw.replace("_", " ").strip()
    s = re.sub(r"\s*\((?:\d{4}\s+)?(?:film|TV series|miniseries|franchise|season\s*\d+)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*[-–—|:]\s*(?:Season|Part|Vol\.?|Episode)\s*\d+.*$", "", s, flags=re.I)
    s = re.sub(r"\s*\(\d{4}\)\s*$", "", s)
    return s.strip(" .,:;-'\"‘’“”#!?")


def extract_social_entities(text: str) -> list[str]:
    """Extracts hashtags, known franchises, quoted titles, and title-case movie/series entities."""
    low = text.lower()
    if any(j in low for j in NON_MOVIE_JUNK):
        return []
    found, seen = [], set()

    def _push(val: str):
        c = _clean_title(val)
        k = re.sub(r"[^a-z0-9]", "", c.lower())
        if k in HASHTAG_ALIASES:
            c = HASHTAG_ALIASES[k]
            k = re.sub(r"[^a-z0-9]", "", c.lower())
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", c)]
        if not words or len(c) < 4 or k in STOP_WORDS or all(w in STOP_WORDS for w in words):
            return
        if words[0] in STOP_WORDS and len(words) <= 2:
            return
        if k not in seen:
            seen.add(k)
            found.append(c)

    # 1. Hashtags (huge signal in YouTube Shorts / Reels / TikTok titles!)
    for tag in re.findall(r"#([A-Za-z0-9_]{3,28})", text):
        tk = tag.lower().replace("_", "")
        if tk in HASHTAG_ALIASES:
            _push(HASHTAG_ALIASES[tk])
        elif tk not in STOP_WORDS and not tk.endswith("edit") and not tk.endswith("edits"):
            # Split CamelCase hashtag like #VisionQuest -> VisionQuest
            _push(tag)

    # 2. Direct alias scan inside title text (catches 1-word hits like VisionQuest, Ramayana, Ultron)
    compact_text = re.sub(r"[^a-z0-9\s:]", " ", low)
    for alias_key, canonical in HASHTAG_ALIASES.items():
        if re.search(rf"\b{re.escape(canonical.lower())}\b", compact_text):
            _push(canonical)

    # 3. Quoted titles (high precision in Reddit/News)
    for q in re.findall(r"['\"‘“]([A-Z][A-Za-z0-9:&\-\s]{2,34})['\"’”]", text):
        _push(q)

    # 4. Capitalized 2-3 word phrases if still < 2 entities
    if len(found) < 2:
        for ph in re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9:]+){1,2})\b", text):
            _push(ph)

    return found[:3]


def probe_youtube_window(queries: list[str], sp: str, label: str, per_query: int = 8) -> list[dict]:
    """Queries YouTube's native Week/Month view-sorted search feed via yt_dlp --flat-playlist."""
    results, seen = [], set()
    for q in queries:
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(q)}&sp={sp}"
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist", "--dump-json", "--playlist-end", str(per_query), "--no-warnings", url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                vid = d.get("id")
                title = d.get("title") or ""
                views = int(d.get("view_count") or 0)
                if not vid or vid in seen or views < 500 or any(j in title.lower() for j in NON_MOVIE_JUNK):
                    continue
                seen.add(vid)
                results.append({
                    "id": vid,
                    "window": label,
                    "title": title,
                    "channel": d.get("channel") or d.get("uploader") or "",
                    "views": views,
                    "duration": float(d.get("duration") or 0),
                    "url": d.get("url") or f"https://youtube.com/watch?v={vid}",
                })
        except Exception as e:
            print(f"[Radar] YT {label} '{q}' skipped: {e}", file=sys.stderr)
    results.sort(key=lambda x: x["views"], reverse=True)
    return results


def fetch_reddit_arcticshift(subreddits: tuple[str, ...], days: int = 7, limit_per_sub: int = 40) -> list[dict]:
    """Fetches real Reddit posts from last N days via ArcticShift public API (no 403/429 blocks)."""
    after_ts = int(time.time() - days * 86400)
    posts = []
    for sub in subreddits:
        url = f"https://arctic-shift.photon-reddit.com/api/posts/search?subreddit={sub}&after={after_ts}&limit={limit_per_sub}&sort=desc"
        try:
            data = json.loads(_http_get(url, timeout=10, ua="MovieSeriesRadar/1.0")).get("data", [])
            for p in data:
                title = (p.get("title") or "").strip()
                score = int(p.get("score") or 0)
                comms = int(p.get("num_comments") or 0)
                eng = score + 3 * comms
                if title and eng >= 5:
                    posts.append({
                        "sub": sub,
                        "title": title,
                        "score": score,
                        "comments": comms,
                        "engagement": eng,
                        "days": days,
                        "url": f"https://www.reddit.com{p.get('permalink', '')}",
                    })
        except Exception as e:
            print(f"[Radar] ArcticShift r/{sub} ({days}d) skipped: {e}", file=sys.stderr)
    posts.sort(key=lambda x: x["engagement"], reverse=True)
    return posts[:30]


def fetch_rss(url: str, default_source: str, limit: int = 10) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(_http_get(url, timeout=10))
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
            source = (item.findtext("source") or default_source).strip()
            link = (item.findtext("link") or "").strip()
            if clean_title:
                items.append({"title": clean_title, "source": source, "link": link})
    except Exception as e:
        print(f"[Radar] RSS skipped ({default_source}): {e}", file=sys.stderr)
    return items


def fetch_social_ig_fb_and_news_buzz() -> tuple[list[dict], list[dict]]:
    """Captures Instagram/Facebook viral movie/series buzz + Entertainment News for 7d and 30d."""
    q_ig_fb_7d = urllib.parse.quote_plus('(instagram OR reels OR facebook OR viral OR meme) (movie OR series OR trailer OR finale) when:7d')
    q_ig_fb_30d = urllib.parse.quote_plus('(instagram OR facebook OR viral OR trending) (movie OR "tv series" OR "web series") when:30d')
    q_in_7d = urllib.parse.quote_plus('(movie OR bollywood OR "box office" OR "web series") when:7d')

    buzz_7d = (
        fetch_rss(f"https://news.google.com/rss/search?q={q_ig_fb_7d}&hl=en-US&gl=US&ceid=US:en", "IG/FB Social Buzz", 12)
        + fetch_rss(f"https://news.google.com/rss/search?q={q_in_7d}&hl=en-IN&gl=IN&ceid=IN:en", "India Cinema Buzz", 10)
        + fetch_rss("https://variety.com/v/film/feed/", "Variety", 8)
        + fetch_rss("https://collider.com/feed/", "Collider", 8)
    )
    buzz_30d = fetch_rss(f"https://news.google.com/rss/search?q={q_ig_fb_30d}&hl=en-US&gl=US&ceid=US:en", "Social 30d Buzz", 12)
    return buzz_7d, buzz_30d


def recommend_format(topic: str, yt_hits: int, reddit_hits: int, news_hits: int) -> str:
    low = topic.lower()
    if any(k in low for k in ("cost", "budget", "fact", "detail", "trivia", "expensive")):
        return "movie_trivia"
    if yt_hits >= 2:
        return "edit_ranking"
    if yt_hits >= 1 and reddit_hits >= 1:
        return "scene_commentary"
    if news_hits >= 2 and yt_hits == 0:
        return "news_slideshow"
    return "release_hype" if news_hits >= 1 else "edit_ranking"


def scan_virality(skip_yt: bool = False) -> dict:
    """Runs the social-first 4-horizon scan (YouTube Week/Month + Reddit Week/Month + IG/FB/News)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("[Radar] Scanning YouTube (Week & Month by views), Reddit (ArcticShift 7d/30d), IG/FB & News...")

    yt_week, yt_month = [], []
    if not skip_yt:
        week_queries = [
            "marvel series edit #shorts",
            "movie edit 4k #shorts",
            "tv show edit viral #shorts",
            "ranking best edits #shorts",
        ]
        month_queries = [
            "movie edit viral #shorts",
            "series finale edit #shorts",
        ]
        yt_week = probe_youtube_window(week_queries, YT_SP_WEEK_VIEWS, "week", per_query=8)
        yt_month = probe_youtube_window(month_queries, YT_SP_MONTH_VIEWS, "month", per_query=8)

    reddit_subs = ("movies", "television", "marvelstudios", "boxoffice", "bollywood", "marvelmemes")
    reddit_7d = fetch_reddit_arcticshift(reddit_subs, days=7, limit_per_sub=35)
    reddit_30d = fetch_reddit_arcticshift(("movies", "television", "marvelmemes"), days=30, limit_per_sub=35)
    buzz_7d, buzz_30d = fetch_social_ig_fb_and_news_buzz()

    buckets: dict[str, dict] = {}

    def _add(name: str, h3d: float = 0, h7d: float = 0, h30d: float = 0, h365d: float = 0,
             source: str = "", headline: str = "", yt_v: int = 0, rd_e: int = 0, fmt: str = ""):
        clean = _clean_title(name)
        key = re.sub(r"[^a-z0-9]", "", clean.lower())
        if len(key) < 4 or key in STOP_WORDS:
            return
        if key not in buckets:
            buckets[key] = {
                "topic": clean, "h3d": 0.0, "h7d": 0.0, "h30d": 0.0, "h365d": 0.0,
                "sources": set(), "headlines": [], "yt_hits": 0, "yt_views": 0,
                "reddit_hits": 0, "reddit_eng": 0, "news_hits": 0, "hint_format": fmt,
            }
        b = buckets[key]
        b["h3d"] = min(100.0, b["h3d"] + h3d)
        b["h7d"] = min(100.0, b["h7d"] + h7d)
        b["h30d"] = min(100.0, b["h30d"] + h30d)
        b["h365d"] = max(b["h365d"], h365d)
        if source:
            b["sources"].add(source)
        if yt_v:
            b["yt_hits"] += 1
            b["yt_views"] += yt_v
        if rd_e:
            b["reddit_hits"] += 1
            b["reddit_eng"] += rd_e
        if headline:
            b["news_hits"] += 1
            if headline not in b["headlines"] and len(b["headlines"]) < 4:
                b["headlines"].append(headline)

    # 1. YouTube THIS WEEK sorted by Views (highest weight for Shorts virality!)
    for v in yt_week:
        pts = min(65.0, math.log1p(v["views"]) * 4.8)
        for ent in extract_social_entities(v["title"]):
            _add(ent, h3d=pts * 0.7, h7d=pts, source="YT-Week", yt_v=v["views"])

    # 2. YouTube THIS MONTH sorted by Views
    for v in yt_month:
        pts = min(60.0, math.log1p(v["views"]) * 4.2)
        for ent in extract_social_entities(v["title"]):
            _add(ent, h30d=pts, source="YT-Month", yt_v=v["views"])

    # 3. Reddit THIS WEEK & THIS MONTH (ArcticShift)
    for p in reddit_7d:
        pts = min(45.0, math.log1p(p["engagement"]) * 6.5)
        for ent in extract_social_entities(p["title"]):
            _add(ent, h3d=pts * 0.8, h7d=pts, source=f"Reddit-7d(r/{p['sub']})", headline=p["title"], rd_e=p["engagement"])

    for p in reddit_30d:
        pts = min(40.0, math.log1p(p["engagement"]) * 5.5)
        for ent in extract_social_entities(p["title"]):
            _add(ent, h30d=pts, source=f"Reddit-30d(r/{p['sub']})", rd_e=p["engagement"])

    # 4. Instagram / Facebook Social Buzz + Breaking Entertainment News
    for n in buzz_7d:
        for ent in extract_social_entities(n["title"]):
            _add(ent, h3d=26.0, h7d=22.0, source=n["source"], headline=n["title"])

    for n in buzz_30d:
        for ent in extract_social_entities(n["title"]):
            _add(ent, h30d=25.0, source=n["source"])

    # 5. Evergreen fallback (10% weight)
    for eg in EVERGREEN_POOL:
        _add(eg["topic"], h365d=eg["evergreen"], source="Evergreen", fmt=eg["format"])

    ranked = []
    for b in buckets.values():
        # Cross-platform convergence bonus (e.g., spiking on BOTH YouTube + Reddit + IG/News)
        platforms_hit = {s.split("-")[0].split("(")[0] for s in b["sources"]}
        convergence = min(20.0, max(0, len(platforms_hit) - 1) * 10.0)
        score = round(compute_multi_horizon_score(b["h3d"], b["h7d"], b["h30d"], b["h365d"]) + convergence, 2)
        fmt = b["hint_format"] or recommend_format(b["topic"], b["yt_hits"], b["reddit_hits"], b["news_hits"])
        ranked.append({
            "topic": b["topic"],
            "score": score,
            "horizons": {"3d": round(b["h3d"], 1), "7d": round(b["h7d"], 1), "30d": round(b["h30d"], 1), "1y": round(b["h365d"], 1)},
            "yt_views": b["yt_views"],
            "yt_hits": b["yt_hits"],
            "reddit_hits": b["reddit_hits"],
            "sources": sorted(b["sources"])[:4],
            "recommended_format": fmt,
            "headlines": b["headlines"],
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    report = {
        "scan_time_utc": now_iso,
        "winner": ranked[0] if ranked else {"topic": "Patrick Jane", "score": 50.0, "recommended_format": "edit_ranking", "headlines": []},
        "top_topics": ranked[:15],
        "top_yt_week": yt_week[:10],
        "top_yt_month": yt_month[:10],
        "top_reddit_week": reddit_7d[:10],
        "breaking_news_feed": buzz_7d[:12],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    w = report["winner"]
    print(f"[Radar] Winner: '{w['topic']}' (Score {w['score']}, YT_views={w.get('yt_views',0):,}, Sources={w.get('sources',[])}, Format={w['recommended_format']})")
    return report


if __name__ == "__main__":
    rep = scan_virality(skip_yt="--no-yt" in sys.argv)
    print("\nTop 10 Social-Viral Movie/Series Targets (YouTube Week/Month + Reddit + IG/FB/News):")
    for i, item in enumerate(rep["top_topics"][:10], 1):
        h = item["horizons"]
        srcs = ", ".join(item["sources"][:3])
        print(f"  {i:2d}. {item['topic']} | Score={item['score']} | YT={item['yt_views']:,} ({item['yt_hits']} vids) | RD={item['reddit_hits']} | [{srcs}] -> {item['recommended_format']}")
    print("\nTop 5 Raw YouTube Videos This Week (Sorted by Views):")
    for v in rep["top_yt_week"][:5]:
        print(f"  - [{v['views']:,} views] {v['title'][:72]}")
    print("\nTop 5 Raw YouTube Videos This Month (Sorted by Views):")
    for v in rep["top_yt_month"][:5]:
        print(f"  - [{v['views']:,} views] {v['title'][:72]}")
