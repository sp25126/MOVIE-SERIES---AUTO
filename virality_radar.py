"""100% dynamic, genre-aware social virality engine (zero static topics)."""

import datetime
import json
import math
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
CATALOG_PATH = ROOT / "niche_catalog.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

# YouTube native protobuf sp filters (Videos sorted by View Count: Today / This Week / This Month)
YT_SP_TODAY_VIEWS = "CAMSBAgCEAE%3D"
YT_SP_WEEK_VIEWS = "CAMSBAgDEAE%3D"
YT_SP_MONTH_VIEWS = "CAMSBAgEEAE%3D"

NON_MOVIE_JUNK = (
    "free fire", "ff edit", "bgmi", "pubg", "gta", "minecraft", "roblox", "valorant",
    "fortnite", "cricket", "football", "ronaldo", "messi", "car edit", "supra", "bmw",
    "tung tung", "skibidi", "cocomelon", "asmr", "slime", "chess", "how to viral",
    "razorbacks", "yankees", "brewers", "basketball", "baseball", "nfl", "nba", "clickeez", "keyboard",
)

STOP_WORDS = {
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where", "how", "why", "which",
    "new", "official", "trailer", "teaser", "clip", "clips", "review", "box", "office", "movie",
    "movies", "series", "show", "shows", "season", "episode", "finale", "watch", "streaming",
    "netflix", "disney", "marvel", "mcu", "hbo", "amazon", "prime", "apple", "release", "date",
    "news", "update", "first", "look", "cast", "star", "director", "part", "one", "two", "three",
    "best", "top", "worst", "full", "hd", "4k", "60fps", "shorts", "short", "edit", "edits",
    "viral", "trending", "ranking", "rank", "scene", "scenes", "worldwide", "post", "credits",
    "beats", "beginner", "audiences", "hollywood", "bollywood", "cinema", "film", "films",
    "theaters", "report", "says", "after", "before", "will", "could", "would", "most", "more",
    "than", "into", "over", "about", "variety", "collider", "deadline", "screenrant", "imdb",
    "history", "sequel", "sequels", "prequel", "reboot", "remake",
    "youtube", "instagram", "facebook", "reels", "tiktok", "fyp", "status", "meme", "memes",
    "funny", "sad", "cold", "coldest", "epic", "insane", "crazy", "moments", "moment", "video",
    "videos", "love", "trend", "whatsapp", "attitudestatus", "attitude", "scenepack", "twixtor",
    "aftereffects", "capcut", "alightmotion", "phonk", "slowed", "reverb", "actress", "actor",
    "bollywoodnews", "hollywoodnews", "movienews", "tvshow", "tvshows", "webseries", "movieclips",
    "spoiler", "spoilers", "discussion", "megathread", "thread", "officialdiscussion", "question",
    "anyone", "else", "just", "watched", "finished", "thought", "thoughts", "opinion", "unpopular",
    "indian", "hindi", "tamil", "telugu", "english", "dubbed", "subbed", "2025", "2026", "2027",
    "complete", "merger", "app", "be", "is", "are", "was", "were", "has", "have", "get", "got",
    "collection", "day", "crore", "mark", "globally", "trying", "here", "addresses", "original", "peacock",
    "heavily", "involved", "because", "he", "she", "they", "them", "his", "her", "their", "my", "your",
    "really", "very", "much", "such", "some", "any", "every", "all", "each", "both", "either", "neither",
    "comedy", "hour", "blooper", "bloopers", "years", "ago", "today", "ever", "made", "premiered", "network",
    "ignore", "it", "ignored", "ignoring", "dont", "do", "not", "cannot", "cant", "wont", "short", "film",
    "shooting", "shoot", "behind", "the", "scenes", "bts", "parrots", "parrot", "paddy", "eating",
    "viralvideo", "shortsfeed", "feed", "explore", "reelsvideo", "foryou", "fypage", "omg", "wow",
    "award", "winning", "awarded", "awards", "oscar", "oscars", "academy", "emmy", "emmys",
    "golden", "globe", "globes", "worst", "ai", "editor", "editors", "battle", "prize",
    "unreleased", "leaked", "behind", "the", "scenes", "making", "of", "explained",
    "darkness", "tv", "spot", "spots", "super", "bowl", "commercial", "ad", "ads",
    "ars", "technica", "crunchyroll", "defector", "rider", "joblo", "rotten", "tomatoes",
    "fans", "sale", "tickets", "final", "stars", "cast", "adds", "crosses", "passes", "sequels", "list",
    "fantasy", "thriller", "horror", "drama", "comedy", "mystery", "action", "romance",
    "everything", "anything", "nothing", "something", "someone", "bites", "bitten",
    "thing", "things", "stuff", "piece", "pieces", "advice", "multifemale", "india",
}

COMMON_HEADLINE_VERBS = {
    "smashes", "returns", "released", "reveals", "says", "shows", "joins", "dominates", "explodes",
    "confirms", "unveils", "debuts", "premieres", "arrives", "slays", "shatters", "tops", "slams",
    "teases", "shares", "opens", "heads", "talks", "meets", "faces", "fights", "costs", "gains",
    "rises", "falls", "starts", "stops", "stays", "sparks", "slips", "beats", "earns", "touches",
    "edges", "claims", "denies", "urges", "eyes", "wows", "shocks", "stuns", "rocks", "crushes",
    "speaks", "takes", "gives", "makes", "tells", "wants", "knows", "finds", "leaves", "leads",
    "becomes", "become", "became", "getting", "making", "being", "having", "going", "coming",
}

GENERIC_SINGLE_WORDS = {
    # Genres & media categories
    "fantasy", "thriller", "horror", "drama", "comedy", "mystery", "action", "romance",
    "scifi", "anime", "manga", "cinema", "movie", "series", "sitcom", "biopic", "crime",
    "history", "sequel", "sequels", "prequel", "reboot", "remake", "which", "podcast",
    # Months, days, pronouns, adverbs & generic places
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "there", "where", "here", "these", "those", "their",
    "street", "turkey", "ghana", "nana", "eyes", "award", "winning",
    # Indefinite & generic nouns/pronouns
    "everything", "anything", "nothing", "something", "someone", "anyone", "everyone",
    "nobody", "somebody", "anybody", "everybody", "bites", "bitten", "thing", "things",
    "stuff", "piece", "pieces", "advice", "multifemale", "multiverse", "character", "characters",
    "people", "person", "actor", "actress", "director", "producer", "writer", "creator",
    "audience", "audiences", "critic", "critics", "story", "stories", "chapter", "scene",
    # Colors & generic adjectives
    "black", "white", "red", "blue", "green", "yellow", "orange", "purple", "grey", "gray",
    "dark", "light", "super", "ultra", "mega", "great", "good", "better", "best", "bad",
    "worst", "epic", "wild", "crazy", "insane", "real", "true", "fake", "dead", "alive",
    "death", "life", "future", "past", "today", "tonight", "tomorrow", "yesterday",
    # Countries & regions (when standalone)
    "india", "indian", "america", "american", "korea", "korean", "japan", "japanese",
    "china", "chinese", "world", "worldwide", "global", "country", "hollywood", "bollywood",
    # Standalone common names & celebrity tags (not franchise titles)
    "robert", "edward", "david", "john", "james", "michael", "hailee", "steinfeld", "richard", "thomas",
    "charles", "daniel", "matthew", "anthony", "mark", "steven", "paul", "andrew", "george",
    # Noise phrases from news headlines
    "lifetime", "producer", "regrets", "splitting", "producer regrets splitting", "interview", "reveal",
    # Common edit/search query tags & buzzwords
    "multifandom", "badass", "mafia", "animation", "animated", "status", "attitude", "fight",
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


def _load_catalog() -> dict:
    if CATALOG_PATH.exists():
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"groups": {}}


def _clean_title(raw: str) -> str:
    s = raw.replace("_", " ").strip()
    s = re.sub(r"\s*\((?:\d{4}\s+)?(?:film|TV series|miniseries|franchise|season\s*\d+)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"\s*[-–—|:]\s*(?:Season|Part|Vol\.?|Episode)\s*\d+.*$", "", s, flags=re.I)
    s = re.sub(r"\s*\(\d{4}\)\s*$", "", s)
    return s.strip(" .,:;-'\"‘’“”#!?")


def extract_social_entities(text: str) -> list[str]:
    """Purely dynamic entity discovery from hashtags, quoted titles, and proper-noun phrases."""
    low = text.lower()
    if any(j in low for j in NON_MOVIE_JUNK):
        return []
    found, seen = [], set()

    def _push(val: str):
        c = _clean_title(val)
        k = re.sub(r"[^a-z0-9]", "", c.lower())
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9]+", c)]
        if not words or len(c) < 4 or len(c) > 36 or k in STOP_WORDS or k in COMMON_HEADLINE_VERBS or all(w in STOP_WORDS or w in GENERIC_SINGLE_WORDS for w in words):
            return
        if len(words) == 1 and (words[0] in GENERIC_SINGLE_WORDS or words[0] in STOP_WORDS):
            return
        if words[0] in STOP_WORDS or (words[-1] in STOP_WORDS and words[-1] not in {"one", "two", "three", "zero"}):
            return
        if words[0] in COMMON_HEADLINE_VERBS:
            return
        if k not in seen:
            seen.add(k)
            found.append(c)

    # 1. Quoted titles (highest precision in Reddit & entertainment news)
    for q in re.findall(r"['\"‘“]([A-Z][A-Za-z0-9:&\-\s]{2,34})['\"’”]", text):
        _push(q)

    # 2. CamelCase or distinctive hashtags (e.g. #VisionQuest, #Ramayana, #AvengersDoomsday, #Godzilla)
    for tag in re.findall(r"#([A-Za-z][A-Za-z0-9]{3,26})", text):
        tk = tag.lower()
        if tk in STOP_WORDS or tk in GENERIC_SINGLE_WORDS or any(tk.endswith(sfx) for sfx in ("edit", "edits", "shorts", "status", "news", "viral")):
            continue
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tag)
        _push(spaced)

    # 3. Multi-word franchise titles with common connectors (e.g. Godzilla x Kong, Hunger Games: Sunrise on the Reaping)
    for ph in re.findall(r"\b([A-Z][a-zA-Z0-9]+(?:\s+(?:x|vs|of|the|and|in|on|to|for|part|a)?\s*[A-Z][a-zA-Z0-9:]+){1,3})\b", text):
        _push(ph)

    # 4. Distinctive 1-word franchise & character proper nouns (e.g. Godzilla, Gladiator, Wicked, Nosferatu, Dune, Spider-Man)
    # Only push if it is not already an individual word inside an already-found multi-word phrase!
    for word in re.findall(r"\b([A-Z][a-z]{3,20}|[A-Z][a-z]+-[A-Z][a-z]+)\b", text):
        wk = word.lower()
        if wk not in COMMON_HEADLINE_VERBS and wk not in STOP_WORDS and wk not in GENERIC_SINGLE_WORDS:
            if not any(wk in [w.lower() for w in re.findall(r"[A-Za-z0-9]+", f)] and len(re.findall(r"[A-Za-z0-9]+", f)) > 1 for f in found):
                _push(word)

    return found[:4]


def classify_genre(topic: str, context_text: str, origin_sub: str, groups: dict) -> str:
    """Dynamically routes any discovered movie/series into the best-matching genre group."""
    sub_l = origin_sub.lower()
    if sub_l:
        for gid, g in groups.items():
            if any(s.lower() == sub_l for s in g.get("subreddits", [])):
                if gid != "action_thriller":  # prefer more specific subreddit matches first
                    return gid

    blob = f"{topic} {context_text}".lower()
    best_gid, best_hits = "action_thriller", 0
    for gid, g in groups.items():
        hits = sum(1 for kw in g.get("keywords", []) if kw in blob)
        if hits > best_hits:
            best_gid, best_hits = gid, hits
    return best_gid


def probe_youtube_window(queries: list[tuple[str, str]], sp: str, label: str, per_query: int = 6) -> list[dict]:
    """Queries YouTube view-sorted search feeds for Today / This Week / This Month using native &sp= filters."""
    results, seen = [], set()
    for gid, q in queries:
        encoded_q = urllib.parse.quote_plus(f"{q} edit shorts")
        search_url = f"https://www.youtube.com/results?search_query={encoded_q}&sp={sp}"
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--flat-playlist", "--dump-json", "--no-warnings",
            "--playlist-end", str(per_query),
            search_url,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
            lines = [l for l in proc.stdout.splitlines() if l.strip()]
            if not lines:
                # Fallback to ytsearch if YouTube results URL returned empty
                fb_cmd = [
                    sys.executable, "-m", "yt_dlp",
                    "--flat-playlist", "--dump-json", "--no-warnings",
                    f"ytsearch{per_query}:{q} edit shorts",
                ]
                proc = subprocess.run(fb_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25)
                lines = [l for l in proc.stdout.splitlines() if l.strip()]
            for line in lines:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                vid = d.get("id")
                title = d.get("title") or ""
                views = int(d.get("view_count") or 0)
                min_views = 2_000 if label == "today" else 15_000
                if not vid or vid in seen or views < min_views or any(j in title.lower() for j in NON_MOVIE_JUNK):
                    continue
                seen.add(vid)
                results.append({
                    "id": vid, "window": label, "genre_hint": gid, "title": title,
                    "channel": d.get("channel") or d.get("uploader") or "",
                    "views": views, "duration": float(d.get("duration") or 0),
                    "url": d.get("url") or f"https://youtube.com/watch?v={vid}",
                })
        except Exception as e:
            print(f"[Radar] YT {label} '{q}' skipped: {e}", file=sys.stderr)
    results.sort(key=lambda x: x["views"], reverse=True)
    return results


def fetch_reddit_arcticshift(subreddits: list[str], days: int = 7, limit_per_sub: int = 25) -> list[dict]:
    """Fetches real Reddit posts across genre subreddits from last N days via ArcticShift API (with Reddit JSON fallback)."""
    after_ts = int(time.time() - days * 86400)
    posts = []
    for sub in subreddits:
        clean_sub = sub.strip().lower()
        data = []
        for url in (
            f"https://arctic-shift.photon-reddit.com/api/posts/search?subreddit={clean_sub}&after={after_ts}&limit=15&sort=desc",
            f"https://www.reddit.com/r/{clean_sub}/hot.json?limit=15",
        ):
            try:
                raw = json.loads(_http_get(url, timeout=5, ua=UA))
                if "data" in raw and isinstance(raw["data"], list):
                    data = raw["data"]
                elif isinstance(raw.get("data"), dict):
                    data = [c.get("data", {}) for c in raw["data"].get("children", [])]
                if data:
                    break
            except Exception:
                continue
        for p in data:
            title = (p.get("title") or "").strip()
            score = int(p.get("score") or 0)
            comms = int(p.get("num_comments") or 0)
            eng = score + 3 * comms
            if title and eng >= 5:
                posts.append({
                    "sub": sub, "title": title, "score": score, "comments": comms,
                    "engagement": eng, "days": days,
                    "url": f"https://www.reddit.com{p.get('permalink', '')}",
                })
    posts.sort(key=lambda x: x["engagement"], reverse=True)
    return posts[:45]


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
    """Captures 100% unbiased global blockbusters & social buzz for Today/7d and 30d (no hardcoded franchises)."""
    q_blockbuster_7d = urllib.parse.quote_plus('("box office" OR blockbuster OR "in theaters" OR "trending movie" OR "viral film" OR sequel) (film OR movie OR trailer) when:7d')
    q_ig_fb_7d = urllib.parse.quote_plus('(instagram OR reels OR facebook OR tiktok OR viral) (movie OR series OR trailer OR finale) when:7d')
    q_ig_fb_30d = urllib.parse.quote_plus('(instagram OR facebook OR viral OR trending) (movie OR "tv series" OR "web series") when:30d')
    q_blockbuster_30d = urllib.parse.quote_plus('(blockbuster OR "box office" OR hollywood OR "trending movie" OR "hit film") (film OR movie) when:30d')
    q_in_7d = urllib.parse.quote_plus('(movie OR bollywood OR kdrama OR "box office" OR "web series") when:7d')

    buzz_7d = (
        fetch_rss(f"https://news.google.com/rss/search?q={q_blockbuster_7d}&hl=en-US&gl=US&ceid=US:en", "Global Blockbuster Buzz", 15)
        + fetch_rss(f"https://news.google.com/rss/search?q={q_ig_fb_7d}&hl=en-US&gl=US&ceid=US:en", "IG/FB Social Buzz", 12)
        + fetch_rss(f"https://news.google.com/rss/search?q={q_in_7d}&hl=en-IN&gl=IN&ceid=IN:en", "Global/India Cinema Buzz", 8)
        + fetch_rss("https://deadline.com/v/film/feed/", "Deadline", 10)
        + fetch_rss("https://www.hollywoodreporter.com/c/movies/movie-news/feed/", "THR", 10)
        + fetch_rss("https://variety.com/v/film/feed/", "Variety", 8)
        + fetch_rss("https://collider.com/feed/", "Collider", 8)
        + fetch_rss("https://www.joblo.com/feed/", "JoBlo", 8)
    )
    buzz_30d = (
        fetch_rss(f"https://news.google.com/rss/search?q={q_blockbuster_30d}&hl=en-US&gl=US&ceid=US:en", "Blockbuster 30d Buzz", 12)
        + fetch_rss(f"https://news.google.com/rss/search?q={q_ig_fb_30d}&hl=en-US&gl=US&ceid=US:en", "Social 30d Buzz", 10)
    )
    return buzz_7d, buzz_30d


def pick_dynamic_subcategory(genre_id: str, yt_hits: int, reddit_hits: int, news_hits: int, groups: dict) -> tuple[str, str, str]:
    """Selects the best pure-video subcategory + format inside the winning genre (no news_slideshow)."""
    subs = groups.get(genre_id, {}).get("subcategories", [])
    if not subs:
        return "dynamic_edit", "edit_ranking", "edit shorts"
    preferred_fmt = (
        "edit_ranking" if yt_hits >= 1
        else ("scene_commentary" if reddit_hits >= 2 else "release_hype")
    )
    for sc in subs:
        if sc["format"] == preferred_fmt:
            return sc["id"], sc["format"], sc.get("query_suffix", "edit shorts")
    sc = subs[0]
    return sc["id"], sc["format"], sc.get("query_suffix", "edit shorts")


def scan_virality(skip_yt: bool = False) -> dict:
    """Runs 100% dynamic multi-genre virality scan (YouTube Week/Month + Reddit 7d/30d + IG/FB/News)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    catalog = _load_catalog()
    groups = catalog.get("groups", {})
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[Radar] 100% Dynamic Scan across {len(groups)} genres (YouTube Today/Week/Month + Reddit 7d/30d + IG/FB/News)...")

    # Build genre-driven probes dynamically from catalog
    yt_today, yt_week, yt_month = [], [], []
    if not skip_yt:
        week_probes = [(gid, g["yt_probe"]) for gid, g in groups.items() if g.get("yt_probe")]
        week_probes.extend([
            ("action_thriller", "blockbuster movie 4k edit shorts"),
            ("superhero_scifi", "trending sci fi movie edit shorts"),
            ("crime_mafia", "coldest cinema character edit #shorts"),
            ("drama_prestige", "viral movie scene transition edit shorts"),
        ])
        today_probes = week_probes[:6]
        month_probes = week_probes[:6]
        yt_today = probe_youtube_window(today_probes, YT_SP_TODAY_VIEWS, "today", per_query=5)
        yt_week = probe_youtube_window(week_probes, YT_SP_WEEK_VIEWS, "week", per_query=5)
        yt_month = probe_youtube_window(month_probes, YT_SP_MONTH_VIEWS, "month", per_query=5)

    all_subs = sorted({s for g in groups.values() for s in g.get("subreddits", [])})
    reddit_7d = fetch_reddit_arcticshift(all_subs, days=7, limit_per_sub=22)
    reddit_30d = fetch_reddit_arcticshift(all_subs[:6], days=30, limit_per_sub=20)
    buzz_7d, buzz_30d = fetch_social_ig_fb_and_news_buzz()

    buckets: dict[str, dict] = {}

    def _add(name: str, h3d: float = 0, h7d: float = 0, h30d: float = 0, h365d: float = 0,
             source: str = "", headline: str = "", yt_v: int = 0, rd_e: int = 0, genre_hint: str = "", origin_sub: str = ""):
        clean = _clean_title(name)
        key = re.sub(r"[^a-z0-9]", "", clean.lower())
        if len(key) < 4 or key in STOP_WORDS or key in GENERIC_SINGLE_WORDS:
            return
        if key not in buckets:
            gid = genre_hint or classify_genre(clean, headline, origin_sub, groups)
            buckets[key] = {
                "topic": clean, "genre": gid, "h3d": 0.0, "h7d": 0.0, "h30d": 0.0, "h365d": 0.0,
                "sources": set(), "headlines": [], "yt_hits": 0, "yt_views": 0,
                "reddit_hits": 0, "reddit_eng": 0, "news_hits": 0,
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

    for v in yt_today:
        pts = min(75.0, math.log1p(v["views"]) * 5.8)
        for ent in extract_social_entities(v["title"]):
            _add(ent, h3d=pts, h7d=pts * 0.7, source="YT-Today", yt_v=v["views"], genre_hint=v["genre_hint"])

    for v in yt_week:
        pts = min(65.0, math.log1p(v["views"]) * 4.8)
        for ent in extract_social_entities(v["title"]):
            _add(ent, h3d=pts * 0.75, h7d=pts, source="YT-Week", yt_v=v["views"], genre_hint=v["genre_hint"])

    for v in yt_month:
        pts = min(60.0, math.log1p(v["views"]) * 4.2)
        for ent in extract_social_entities(v["title"]):
            _add(ent, h30d=pts, source="YT-Month", yt_v=v["views"], genre_hint=v["genre_hint"])

    for p in reddit_7d:
        pts = min(48.0, math.log1p(p["engagement"]) * 6.5)
        for ent in extract_social_entities(p["title"]):
            _add(ent, h3d=pts * 0.8, h7d=pts, source=f"Reddit-7d(r/{p['sub']})", headline=p["title"], rd_e=p["engagement"], origin_sub=p["sub"])

    for p in reddit_30d:
        pts = min(42.0, math.log1p(p["engagement"]) * 5.5)
        for ent in extract_social_entities(p["title"]):
            _add(ent, h30d=pts, source=f"Reddit-30d(r/{p['sub']})", rd_e=p["engagement"], origin_sub=p["sub"])

    news_topic_counts: dict[str, int] = {}
    for n in buzz_7d:
        for ent in extract_social_entities(n["title"]):
            ent_key = re.sub(r"[^a-z0-9]", "", ent.lower())
            c = news_topic_counts.get(ent_key, 0)
            if c < 2:  # Anti-monopoly: cap news headline stacking at 2 hits per topic
                news_topic_counts[ent_key] = c + 1
                _add(ent, h3d=24.0, h7d=18.0, source=n["source"], headline=n["title"])

    for n in buzz_30d:
        for ent in extract_social_entities(n["title"]):
            ent_key = re.sub(r"[^a-z0-9]", "", ent.lower())
            c = news_topic_counts.get(ent_key, 0)
            if c < 3:
                news_topic_counts[ent_key] = c + 1
                _add(ent, h30d=20.0, source=n["source"])

    ranked = []
    genre_totals: dict[str, dict] = {gid: {"genre": gid, "label": g["label"], "total_score": 0.0, "top_topic": "", "count": 0} for gid, g in groups.items()}

    for b in buckets.values():
        # Filter out noisy 1-word headline artifacts that have zero YouTube & Reddit validation
        if len(b["topic"].split()) == 1 and b["yt_hits"] == 0 and b["reddit_hits"] == 0:
            continue
        platforms_hit = {s.split("-")[0].split("(")[0] for s in b["sources"]}
        convergence = min(20.0, max(0, len(platforms_hit) - 1) * 10.0)
        score = round(compute_multi_horizon_score(b["h3d"], b["h7d"], b["h30d"], b["h365d"]) + convergence, 2)
        sc_id, fmt, q_sfx = pick_dynamic_subcategory(b["genre"], b["yt_hits"], b["reddit_hits"], b["news_hits"], groups)
        entry = {
            "topic": b["topic"],
            "genre": b["genre"],
            "subcategory": sc_id,
            "recommended_format": fmt,
            "query_suffix": q_sfx,
            "score": score,
            "horizons": {"3d": round(b["h3d"], 1), "7d": round(b["h7d"], 1), "30d": round(b["h30d"], 1), "1y": round(b["h365d"], 1)},
            "yt_views": b["yt_views"],
            "yt_hits": b["yt_hits"],
            "reddit_hits": b["reddit_hits"],
            "sources": sorted(b["sources"])[:4],
            "headlines": b["headlines"],
        }
        ranked.append(entry)
        if b["genre"] in genre_totals:
            gt = genre_totals[b["genre"]]
            gt["total_score"] = round(gt["total_score"] + score, 1)
            gt["count"] += 1

    ranked.sort(key=lambda x: x["score"], reverse=True)
    for item in ranked:
        gt = genre_totals.get(item["genre"])
        if gt and not gt["top_topic"]:
            gt["top_topic"] = item["topic"]

    genre_board = sorted(genre_totals.values(), key=lambda x: x["total_score"], reverse=True)

    report = {
        "scan_time_utc": now_iso,
        "winner": ranked[0] if ranked else {"topic": "Cinema", "genre": "action_thriller", "subcategory": "action_fight_ranking", "recommended_format": "edit_ranking", "query_suffix": "edit shorts", "score": 0.0, "headlines": []},
        "genre_leaderboard": genre_board,
        "top_topics": ranked[:20],
        "top_yt_today": yt_today[:10],
        "top_yt_week": yt_week[:10],
        "top_yt_month": yt_month[:10],
        "top_reddit_week": reddit_7d[:10],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # Sync 100% live genre leaderboard & top topics into niche_catalog.json
    if CATALOG_PATH.exists():
        catalog["last_3day_sync_utc"] = now_iso
        catalog["live_genre_leaderboard"] = genre_board
        catalog["live_3day_top_topics"] = [
            {"topic": t["topic"], "genre": t["genre"], "subcategory": t["subcategory"], "format": t["recommended_format"], "score": t["score"], "sources": t["sources"]}
            for t in ranked[:15]
        ]
        CATALOG_PATH.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")

    w = report["winner"]
    print(f"[Radar] #1 Dynamic Winner: '{w['topic']}' | Genre={w['genre']} | Score={w['score']} | Format={w['recommended_format']}")
    return report


if __name__ == "__main__":
    rep = scan_virality(skip_yt="--no-yt" in sys.argv)
    print("\nLive 8-Genre Virality Leaderboard:")
    for g in rep["genre_leaderboard"]:
        print(f"  • {g['label']:38s} | TotalScore={g['total_score']:6.1f} | Topics={g['count']:2d} | Lead='{g['top_topic']}'")
    print("\nTop 10 100%-Dynamic Viral Targets:")
    for i, item in enumerate(rep["top_topics"][:10], 1):
        srcs = ", ".join(item["sources"][:3])
        print(f"  {i:2d}. [{item['genre']}] {item['topic']} | Score={item['score']} | YT={item['yt_views']:,} | RD={item['reddit_hits']} | [{srcs}] -> {item['recommended_format']}")
