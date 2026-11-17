"""Multi-horizon Movies & Series virality engine (3d / 7d / 30d / 1y)."""

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

EVERGREEN_POOL = [
    {"topic": "Patrick Jane", "franchise": "The Mentalist", "format": "edit_ranking", "evergreen": 95, "query": "Patrick Jane edit shorts"},
    {"topic": "Spider-Man", "franchise": "Spider-Man", "format": "edit_ranking", "evergreen": 92, "query": "Spider-Man edit 4k shorts"},
    {"topic": "Breaking Bad", "franchise": "Breaking Bad", "format": "edit_ranking", "evergreen": 90, "query": "Breaking Bad edit shorts"},
    {"topic": "Malcolm in the Middle", "franchise": "Malcolm in the Middle", "format": "scene_commentary", "evergreen": 88, "query": "Malcolm in the Middle funny scene edit shorts"},
    {"topic": "Most Expensive Movie Scenes", "franchise": "Hollywood Cinema", "format": "movie_trivia", "evergreen": 86, "query": "movie scenes that cost millions shorts"},
]

STOP_TITLE_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "how", "why",
    "new", "official", "trailer", "teaser", "clip", "review", "box", "office", "movie", "movies",
    "series", "show", "season", "episode", "finale", "watch", "streaming", "netflix", "disney",
    "marvel", "hbo", "amazon", "prime", "apple", "release", "date", "news", "update", "first",
    "look", "cast", "star", "director", "part", "one", "two", "three", "best", "top", "worst",
    "full", "hd", "4k", "shorts", "short", "edit", "edits", "viral", "trending", "ranking",
    "scene", "scenes", "worldwide", "post", "credits", "beats", "beginner", "official", "teaser",
}


def _http_get(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,application/xml,text/xml,*/*"})
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


def _extract_entities(text: str) -> list[str]:
    """Pulls capitalized multi-word titles or quoted franchise names from headlines."""
    found = []
    # Quoted titles first (highest precision in entertainment headlines)
    for m in re.findall(r"['\"‘“]([A-Z][A-Za-z0-9:&\-\s]{2,36})['\"’”]", text):
        cand = m.strip(" .,:;-")
        if cand and cand.lower() not in STOP_TITLE_WORDS:
            found.append(cand)
    # Capitalized title phrases (1-3 words)
    for m in re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9:]+){0,2})\b", text):
        cand = m.strip(" .,:;-")
        words = [w.lower() for w in cand.split()]
        if len(cand) >= 4 and not all(w in STOP_TITLE_WORDS for w in words):
            if words[0] not in STOP_TITLE_WORDS:
                found.append(cand)
    return found


def fetch_google_news_rss(query: str, gl: str = "US", limit: int = 12) -> list[dict]:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-{gl}&gl={gl}&ceid={gl}:en"
    items = []
    try:
        xml_text = _http_get(url, timeout=10)
        root = ET.fromstring(xml_text)
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            # Strip trailing " - Source Name"
            clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip()
            source = (item.findtext("source") or "Entertainment News").strip()
            pub = (item.findtext("pubDate") or "").strip()
            link = (item.findtext("link") or "").strip()
            if clean_title:
                items.append({"title": clean_title, "source": source, "pub_date": pub, "link": link})
    except Exception as e:
        print(f"[Radar] RSS skipped ({query[:28]}): {e}", file=sys.stderr)
    return items


def fetch_reddit_hot(subreddits: tuple[str, ...] = ("movies", "television", "boxoffice", "bollywood")) -> list[dict]:
    posts = []
    rd_ua = "windows:movie-series-radar:v1.0 (by /u/cinepulse_auto)"
    for sub in subreddits:
        try:
            req = urllib.request.Request(f"https://www.reddit.com/r/{sub}/hot/.rss", headers={"User-Agent": rd_ua})
            with urllib.request.urlopen(req, timeout=8) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for idx, entry in enumerate(root.findall("a:entry", ns)[:10]):
                title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
                if title:
                    # Rank-based score proxy since Atom RSS orders by hotness
                    posts.append({"sub": sub, "title": title, "score": max(200, 2000 - idx * 180), "comments": 40})
        except Exception as e:
            print(f"[Radar] Reddit r/{sub} skipped: {e}", file=sys.stderr)
    return posts


def fetch_tmdb_trending() -> list[dict]:
    api_key = os.environ.get("TMDB_API_KEY", "").strip()
    if not api_key:
        return []
    out = []
    for ep in ("trending/all/day", "trending/all/week", "movie/now_playing", "tv/on_the_air"):
        try:
            raw = _http_get(f"https://api.themoviedb.org/3/{ep}?api_key={api_key}", timeout=8)
            for r in json.loads(raw).get("results", [])[:10]:
                name = r.get("title") or r.get("name")
                if name:
                    out.append({
                        "topic": name,
                        "endpoint": ep,
                        "popularity": float(r.get("popularity") or 0),
                        "poster": f"https://image.tmdb.org/t/p/w780{r['poster_path']}" if r.get("poster_path") else None,
                    })
        except Exception as e:
            print(f"[Radar] TMDB {ep} skipped: {e}", file=sys.stderr)
    return out


def probe_youtube_shorts_velocity(queries: list[str], per_query: int = 5) -> list[dict]:
    """Live 7-day YouTube Shorts velocity scan via yt_dlp (zero API keys)."""
    results = []
    seen = set()
    for q in queries:
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--dump-json", "--no-playlist", "--no-warnings",
            "--match-filter", "duration <= 65 & duration >= 6",
            f"ytsearch{per_query}:{q}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                vid = d.get("id")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                views = float(d.get("view_count") or 0)
                ts = d.get("timestamp")
                if not ts and d.get("upload_date"):
                    try:
                        ts = datetime.datetime.strptime(d["upload_date"], "%Y%m%d").timestamp()
                    except Exception:
                        ts = time.time() - 72 * 3600
                age_h = max(1.0, (time.time() - float(ts or (time.time() - 72 * 3600))) / 3600.0)
                subs = float(d.get("channel_follower_count") or 50000)
                v_score = compute_vph_score(views, age_h, subs)
                results.append({
                    "id": vid,
                    "title": d.get("title", ""),
                    "channel": d.get("channel") or d.get("uploader", ""),
                    "views": int(views),
                    "age_hours": round(age_h, 1),
                    "v_score": v_score,
                    "url": d.get("webpage_url") or f"https://youtube.com/shorts/{vid}",
                    "query": q,
                })
        except Exception as e:
            print(f"[Radar] YouTube probe '{q}' skipped: {e}", file=sys.stderr)
    results.sort(key=lambda x: x["v_score"], reverse=True)
    return results


def recommend_format(topic: str, h3d: float, h7d: float, news_hits: int) -> str:
    low = topic.lower()
    if any(k in low for k in ("cost", "budget", "fact", "detail", "trivia", "expensive")):
        return "movie_trivia"
    if h3d >= 65 and news_hits >= 2:
        return "news_slideshow"
    if h3d >= 50 and h7d < 40:
        return "release_hype"
    return "edit_ranking"


def scan_virality(skip_yt: bool = False) -> dict:
    """Runs the full 4-horizon scan and saves state/virality_report.json."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("[Radar] Scanning 3-day, 7-day, 30-day & evergreen movie/series signals...")

    # 1. 3-Day & 30-Day Breaking Signals (Google News US + IN + Reddit + optional TMDB)
    news_3d = (
        fetch_google_news_rss('(movie OR "tv series" OR "box office" OR "official trailer") when:3d', "US", 12)
        + fetch_google_news_rss('(movie OR bollywood OR "box office" OR "web series") when:3d', "IN", 8)
    )
    news_30d = fetch_google_news_rss("(new movies in theaters OR trending series) when:30d", "US", 10)
    reddit_posts = fetch_reddit_hot()
    tmdb_items = fetch_tmdb_trending()

    # 2. 7-Day Live YouTube Shorts Velocity
    yt_vids = []
    if not skip_yt:
        yt_queries = [
            "movie edit viral shorts 2026",
            "series finale edit shorts 2026",
            "ranking best movie edits shorts",
        ]
        yt_vids = probe_youtube_shorts_velocity(yt_queries, per_query=5)

    # 3. Aggregate entities across all 4 horizons
    buckets: dict[str, dict] = {}

    def _add(name: str, h3d: float = 0, h7d: float = 0, h30d: float = 0, h365d: float = 0, headline: str = "", fmt: str = ""):
        key = name.strip().lower()
        if len(key) < 4 or key in STOP_TITLE_WORDS:
            return
        if key not in buckets:
            buckets[key] = {
                "topic": name.strip(),
                "h3d": 0.0,
                "h7d": 0.0,
                "h30d": 0.0,
                "h365d": 0.0,
                "news_hits": 0,
                "headlines": [],
                "hint_format": fmt,
            }
        b = buckets[key]
        b["h3d"] = min(100.0, b["h3d"] + h3d)
        b["h7d"] = min(100.0, b["h7d"] + h7d)
        b["h30d"] = min(100.0, b["h30d"] + h30d)
        b["h365d"] = max(b["h365d"], h365d)
        if headline:
            b["news_hits"] += 1
            if headline not in b["headlines"] and len(b["headlines"]) < 4:
                b["headlines"].append(headline)

    for n in news_3d:
        for ent in _extract_entities(n["title"])[:2]:
            _add(ent, h3d=35.0, headline=n["title"])

    for n in news_30d:
        for ent in _extract_entities(n["title"])[:2]:
            _add(ent, h30d=30.0)

    for p in reddit_posts:
        weight = min(45.0, (p["score"] / 150.0) + (p["comments"] / 25.0))
        for ent in _extract_entities(p["title"])[:2]:
            _add(ent, h3d=weight, headline=p["title"])

    for t in tmdb_items:
        ep = t["endpoint"]
        pop = min(100.0, t["popularity"] / 5.0)
        _add(t["topic"], h3d=pop if "day" in ep or "now_playing" in ep else 0, h30d=pop)

    for v in yt_vids:
        v_norm = min(100.0, math.log1p(v["v_score"]) * 12.0)
        for ent in _extract_entities(v["title"])[:2]:
            _add(ent, h7d=v_norm)

    for eg in EVERGREEN_POOL:
        _add(eg["topic"], h365d=eg["evergreen"], fmt=eg["format"])

    ranked = []
    for b in buckets.values():
        score = compute_multi_horizon_score(b["h3d"], b["h7d"], b["h30d"], b["h365d"])
        fmt = b["hint_format"] or recommend_format(b["topic"], b["h3d"], b["h7d"], b["news_hits"])
        ranked.append({
            "topic": b["topic"],
            "score": score,
            "horizons": {"3d": round(b["h3d"], 1), "7d": round(b["h7d"], 1), "30d": round(b["h30d"], 1), "1y": round(b["h365d"], 1)},
            "recommended_format": fmt,
            "headlines": b["headlines"],
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    report = {
        "scan_time_utc": now_iso,
        "winner": ranked[0] if ranked else {"topic": "Patrick Jane", "score": 50.0, "recommended_format": "edit_ranking", "headlines": []},
        "top_topics": ranked[:15],
        "breaking_news_feed": news_3d[:10],
        "top_yt_shorts": yt_vids[:10],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Radar] Winner: '{report['winner']['topic']}' (Score {report['winner']['score']}, Format: {report['winner']['recommended_format']})")
    return report


if __name__ == "__main__":
    rep = scan_virality(skip_yt="--no-yt" in sys.argv)
    print("\nTop 8 Multi-Horizon Viral Movie/Series Targets:")
    for i, item in enumerate(rep["top_topics"][:8], 1):
        h = item["horizons"]
        print(f"  {i}. {item['topic']} | Score={item['score']} (3d:{h['3d']} 7d:{h['7d']} 30d:{h['30d']} 1y:{h['1y']}) -> {item['recommended_format']}")
