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
    {"topic": "Patrick Jane", "format": "edit_ranking", "evergreen": 95},
    {"topic": "Spider-Man", "format": "edit_ranking", "evergreen": 92},
    {"topic": "Breaking Bad", "format": "edit_ranking", "evergreen": 90},
    {"topic": "Malcolm in the Middle", "format": "scene_commentary", "evergreen": 88},
    {"topic": "Most Expensive Movie Scenes", "format": "movie_trivia", "evergreen": 86},
]

STOP_TITLE_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "how", "why",
    "new", "official", "trailer", "teaser", "clip", "review", "box", "office", "movie", "movies",
    "series", "show", "season", "episode", "finale", "watch", "streaming", "netflix", "disney",
    "marvel", "hbo", "amazon", "prime", "apple", "release", "date", "news", "update", "first",
    "look", "cast", "star", "director", "part", "one", "two", "three", "best", "top", "worst",
    "full", "hd", "4k", "shorts", "short", "edit", "edits", "viral", "trending", "ranking",
    "scene", "scenes", "worldwide", "post", "credits", "beats", "beginner", "audiences",
    "hollywood", "bollywood", "cinema", "film", "films", "theaters", "report", "says", "after",
    "before", "will", "could", "would", "most", "more", "than", "into", "over", "about",
    "variety", "collider", "deadline", "screenrant", "imdb", "youtube", "instagram", "facebook",
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


def _clean_title_name(raw: str) -> str:
    s = raw.replace("_", " ").strip()
    s = re.sub(r"\s*\((?:\d{4}\s+)?(?:film|TV series|miniseries|franchise|character|comics|season\s*\d+)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*[-–—|:]\s*(?:Season|Part|Vol\.?|Episode)\s*\d+.*$", "", s, flags=re.I)
    s = re.sub(r"\s*\(\d{4}\)\s*$", "", s)
    return s.strip(" .,:;-'\"‘’“”")


def _extract_entities(text: str) -> list[str]:
    """Pulls quoted titles first (highest precision), then clean capitalized multi-word titles."""
    found = []
    for m in re.findall(r"['\"‘“]([A-Z][A-Za-z0-9:&\-\s]{2,36})['\"’”]", text):
        cand = _clean_title_name(m)
        if cand and len(cand) >= 4 and cand.lower() not in STOP_TITLE_WORDS:
            found.append(cand)
    if found:
        return found[:2]
    for m in re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9:]+){1,3})\b", text):
        cand = _clean_title_name(m)
        words = [w.lower() for w in cand.split()]
        if len(cand) >= 5 and words[0] not in STOP_TITLE_WORDS and not all(w in STOP_TITLE_WORDS for w in words):
            found.append(cand)
    return found[:2]


def fetch_wikimedia_film_tv_spikes(days_back: int = 2) -> tuple[list[dict], dict[str, int]]:
    """3-Day global search spike via Wikimedia Top Pageviews API (zero key, exact daily views)."""
    film_tv = []
    all_views: dict[str, int] = {}
    for d_off in range(1, days_back + 1):
        day = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=d_off)
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{day:%Y/%m/%d}"
        try:
            arts = json.loads(_http_get(url, timeout=10, ua="MovieSeriesRadar/1.0")).get("items", [{}])[0].get("articles", [])
            for a in arts[:400]:
                art = a.get("article", "")
                views = int(a.get("views") or 0)
                clean = _clean_title_name(art)
                low_art = art.lower()
                if clean and clean.lower() not in all_views:
                    all_views[clean.lower()] = views
                if any(k in low_art for k in ("(film)", "_film)", "(tv_series)", "(miniseries)", "_season_")):
                    if "bigg_boss" in low_art:
                        continue
                    film_tv.append({"topic": clean, "wiki_views": views, "raw": art})
            if film_tv:
                break
        except Exception as e:
            print(f"[Radar] Wikimedia {day:%Y-%m-%d} skipped: {e}", file=sys.stderr)
    return film_tv[:20], all_views


def fetch_itunes_live_charts() -> list[dict]:
    """7-Day live US Top Movies & Top TV Seasons via Apple iTunes public JSON API."""
    out = []
    feeds = [
        ("movie", "https://itunes.apple.com/us/rss/topmovies/limit=15/json"),
        ("tv", "https://itunes.apple.com/us/rss/toptvseasons/limit=15/json"),
    ]
    for kind, url in feeds:
        try:
            entries = json.loads(_http_get(url, timeout=10)).get("feed", {}).get("entry", [])
            for idx, e in enumerate(entries, 1):
                raw_name = (e.get("im:name") or {}).get("label") or ""
                clean = _clean_title_name(raw_name)
                if clean:
                    out.append({"topic": clean, "kind": kind, "rank": idx, "score_7d": max(35.0, 95.0 - idx * 4.0)})
        except Exception as e:
            print(f"[Radar] iTunes {kind} skipped: {e}", file=sys.stderr)
    return out


def fetch_rss_feed(url: str, default_source: str, limit: int = 12) -> list[dict]:
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


def fetch_entertainment_news() -> tuple[list[dict], list[dict]]:
    """3-Day breaking movie/series news (Variety, Collider, Google News US+IN) + 30-Day slate."""
    g_us = "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus('(movie OR "tv series" OR "box office" OR "official trailer") when:3d') + "&hl=en-US&gl=US&ceid=US:en"
    g_in = "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus('(movie OR bollywood OR "box office" OR "web series") when:3d') + "&hl=en-IN&gl=IN&ceid=IN:en"
    g_30 = "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus('("in theaters" OR "new series" OR "box office hit") when:30d') + "&hl=en-US&gl=US&ceid=US:en"

    news_3d = (
        fetch_rss_feed("https://variety.com/v/film/feed/", "Variety", 10)
        + fetch_rss_feed("https://collider.com/feed/", "Collider", 10)
        + fetch_rss_feed(g_us, "Google News US", 10)
        + fetch_rss_feed(g_in, "Google News IN", 8)
    )
    news_30d = fetch_rss_feed(g_30, "Monthly Slate", 12)
    return news_3d, news_30d


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
                    out.append({"topic": _clean_title_name(name), "endpoint": ep, "popularity": float(r.get("popularity") or 0)})
        except Exception as e:
            print(f"[Radar] TMDB {ep} skipped: {e}", file=sys.stderr)
    return out


def probe_youtube_shorts_velocity(queries: list[str], per_query: int = 5) -> list[dict]:
    """Live 7-day YouTube Shorts velocity scan via yt_dlp (zero API keys)."""
    results, seen = [], set()
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
                results.append({
                    "id": vid,
                    "title": d.get("title", ""),
                    "channel": d.get("channel") or d.get("uploader", ""),
                    "views": int(views),
                    "age_hours": round(age_h, 1),
                    "v_score": compute_vph_score(views, age_h, subs),
                    "url": d.get("webpage_url") or f"https://youtube.com/shorts/{vid}",
                })
        except Exception as e:
            print(f"[Radar] YouTube probe '{q}' skipped: {e}", file=sys.stderr)
    results.sort(key=lambda x: x["v_score"], reverse=True)
    return results


def recommend_format(topic: str, h3d: float, h7d: float, news_hits: int) -> str:
    low = topic.lower()
    if any(k in low for k in ("cost", "budget", "fact", "detail", "trivia", "expensive")):
        return "movie_trivia"
    if h3d >= 70 and h7d >= 40:
        return "edit_ranking"
    if h3d >= 65 and news_hits >= 2:
        return "news_slideshow"
    if h3d >= 55 and h7d < 35:
        return "release_hype"
    return "edit_ranking"


def scan_virality(skip_yt: bool = False) -> dict:
    """Runs the full 4-horizon scan and saves state/virality_report.json."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("[Radar] Scanning 3d (Wikimedia+News), 7d (YouTube+iTunes), 30d (Slate+TMDB) & 1y signals...")

    wiki_spikes, wiki_lookup = fetch_wikimedia_film_tv_spikes(days_back=2)
    itunes_charts = fetch_itunes_live_charts()
    news_3d, news_30d = fetch_entertainment_news()
    tmdb_items = fetch_tmdb_trending()

    yt_vids = []
    if not skip_yt:
        yt_vids = probe_youtube_shorts_velocity([
            "movie edit viral shorts 2026",
            "series edit viral shorts 2026",
            "new movie scene edit shorts 2026",
        ], per_query=5)

    buckets: dict[str, dict] = {}

    def _add(name: str, h3d: float = 0, h7d: float = 0, h30d: float = 0, h365d: float = 0, headline: str = "", source: str = "", fmt: str = ""):
        clean = _clean_title_name(name)
        key = clean.lower()
        if len(key) < 4 or key in STOP_TITLE_WORDS or all(w in STOP_TITLE_WORDS for w in key.split()):
            return
        if key not in buckets:
            buckets[key] = {
                "topic": clean, "h3d": 0.0, "h7d": 0.0, "h30d": 0.0, "h365d": 0.0,
                "news_hits": 0, "headlines": [], "sources": set(), "hint_format": fmt,
            }
        b = buckets[key]
        b["h3d"] = min(100.0, b["h3d"] + h3d)
        b["h7d"] = min(100.0, b["h7d"] + h7d)
        b["h30d"] = min(100.0, b["h30d"] + h30d)
        b["h365d"] = max(b["h365d"], h365d)
        if source:
            b["sources"].add(source)
        if headline:
            b["news_hits"] += 1
            if headline not in b["headlines"] and len(b["headlines"]) < 4:
                b["headlines"].append(headline)

    # 1. Wikimedia verified Film/TV spikes (high precision 3-day global interest)
    max_wv = max((w["wiki_views"] for w in wiki_spikes), default=100_000)
    for w in wiki_spikes:
        score = min(100.0, 35.0 + 65.0 * (w["wiki_views"] / max(1, max_wv)))
        _add(w["topic"], h3d=score, source=f"Wikipedia({w['wiki_views']:,})")

    # 2. iTunes live Top Movies & Top TV Seasons (7-day VOD/streaming demand)
    for it in itunes_charts:
        _add(it["topic"], h7d=it["score_7d"], h30d=45.0, source=f"iTunes-{it['kind']}#{it['rank']}")

    # 3. Entertainment News (Variety, Collider, Google News US+IN) + cross-boost if also in Wiki top 400
    for n in news_3d:
        for ent in _extract_entities(n["title"]):
            wiki_bonus = 40.0 if ent.lower() in wiki_lookup else 0.0
            _add(ent, h3d=28.0 + wiki_bonus, headline=n["title"], source=n["source"])

    for n in news_30d:
        for ent in _extract_entities(n["title"]):
            _add(ent, h30d=35.0, source="30d-Slate")

    # 4. Optional TMDB
    for t in tmdb_items:
        pop = min(100.0, t["popularity"] / 5.0)
        _add(t["topic"], h3d=pop if "day" in t["endpoint"] or "now_playing" in t["endpoint"] else 0, h30d=pop, source="TMDB")

    # 5. Live YouTube Shorts Velocity
    for v in yt_vids:
        v_norm = min(100.0, math.log1p(v["v_score"]) * 11.0)
        for ent in _extract_entities(v["title"]):
            _add(ent, h7d=v_norm, source="YouTubeShorts")

    # 6. 1-Year Evergreen pool
    for eg in EVERGREEN_POOL:
        _add(eg["topic"], h365d=eg["evergreen"], source="Evergreen", fmt=eg["format"])

    ranked = []
    for b in buckets.values():
        # Multi-source convergence bonus: titles trending across 2+ independent sources beat single-source noise
        multi_bonus = min(15.0, max(0, len(b["sources"]) - 1) * 7.5)
        score = round(compute_multi_horizon_score(b["h3d"], b["h7d"], b["h30d"], b["h365d"]) + multi_bonus, 2)
        fmt = b["hint_format"] or recommend_format(b["topic"], b["h3d"], b["h7d"], b["news_hits"])
        ranked.append({
            "topic": b["topic"],
            "score": score,
            "horizons": {"3d": round(b["h3d"], 1), "7d": round(b["h7d"], 1), "30d": round(b["h30d"], 1), "1y": round(b["h365d"], 1)},
            "sources": sorted(b["sources"]),
            "recommended_format": fmt,
            "headlines": b["headlines"],
        })

    ranked.sort(key=lambda x: x["score"], reverse=True)
    report = {
        "scan_time_utc": now_iso,
        "winner": ranked[0] if ranked else {"topic": "Patrick Jane", "score": 50.0, "recommended_format": "edit_ranking", "headlines": []},
        "top_topics": ranked[:15],
        "breaking_news_feed": news_3d[:12],
        "top_yt_shorts": yt_vids[:10],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[Radar] Winner: '{report['winner']['topic']}' (Score {report['winner']['score']}, Sources={report['winner'].get('sources', [])}, Format={report['winner']['recommended_format']})")
    return report


if __name__ == "__main__":
    rep = scan_virality(skip_yt="--no-yt" in sys.argv)
    print("\nTop 10 Multi-Horizon Viral Movie/Series Targets:")
    for i, item in enumerate(rep["top_topics"][:10], 1):
        h = item["horizons"]
        srcs = ", ".join(item["sources"][:3])
        print(f"  {i:2d}. {item['topic']} | Score={item['score']} (3d:{h['3d']} 7d:{h['7d']} 30d:{h['30d']} 1y:{h['1y']}) [{srcs}] -> {item['recommended_format']}")
