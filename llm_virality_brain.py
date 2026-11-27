"""
LLM Virality Brain & Real-Time Cultural Zeitgeist Scorer.
Acts as an elite Hollywood & Internet Culture Intelligence Analyst.
Ingests live signals across YouTube Trailers, Reddit Frontpages, Trade RSS, and Wikipedia,
then uses Gemini 2.5 Flash to synthesize cultural urgency, score hype with verifiable proof,
and identify breaking cultural moments (e.g. Avengers Doomsday trailer drops) for immediate pre-emption.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LLM_REPORT_PATH = STATE_DIR / "llm_virality_report.json"
CATALOG_PATH = ROOT / "niche_catalog.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

TRADE_RSS_FEEDS = [
    ("Deadline", "https://deadline.com/feed/"),
    ("Variety", "https://variety.com/feed/"),
    ("THR", "https://www.hollywoodreporter.com/feed/"),
    ("Collider", "https://collider.com/feed/"),
]

REDDIT_SUBREDDITS = ["movies", "boxoffice", "marvelstudios", "television"]


def _get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    return key


def fetch_trade_news_headlines(max_items: int = 15) -> List[Dict[str, str]]:
    """Fetches breaking news headlines from Deadline, Variety, THR, and Collider."""
    items = []
    for source, url in TRADE_RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=5) as resp:
                xml_data = resp.read()
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:max_items]:
                title = item.findtext("title") or ""
                pub_date = item.findtext("pubDate") or ""
                if title:
                    items.append({"source": source, "title": title.strip(), "pubDate": pub_date})
        except Exception as e:
            logging.debug(f"[LLM Brain] RSS error for {source}: {e}")
    return items


def fetch_reddit_hot_discussions(limit_per_sub: int = 8) -> List[Dict[str, Any]]:
    """Fetches high-engagement hot discussions from movie/series subreddits."""
    posts = []
    for sub in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit_per_sub}"
            req = urllib.request.Request(url, headers={"User-Agent": "OtakuVirality/2.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for child in data.get("data", {}).get("children", []):
                d = child.get("data", {})
                title = d.get("title") or ""
                ups = d.get("score") or 0
                comms = d.get("num_comments") or 0
                if ups >= 100 or comms >= 40:
                    posts.append({
                        "subreddit": sub,
                        "title": title,
                        "upvotes": ups,
                        "comments": comms,
                        "created_utc": d.get("created_utc"),
                    })
        except Exception as e:
            logging.debug(f"[LLM Brain] Reddit error for r/{sub}: {e}")
    return posts


def fetch_breaking_trailers_velocity(query: str = "trailer 2026", max_results: int = 8) -> List[Dict[str, Any]]:
    """Probes YouTube via yt_dlp for rapid-fire trailer velocity (views accumulated in short hours)."""
    import subprocess
    import sys
    trailers = []
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--dump-json", "--no-playlist", "--no-warnings",
        f"ytsearch{max_results}:{query}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                title = d.get("title") or ""
                channel = d.get("uploader") or d.get("channel") or ""
                views = int(d.get("view_count") or 0)
                dur = float(d.get("duration") or 0)
                trailers.append({
                    "title": title,
                    "channel": channel,
                    "views": views,
                    "duration": dur,
                    "id": d.get("id"),
                })
            except Exception:
                continue
    except Exception as e:
        logging.debug(f"[LLM Brain] Trailer velocity scan error: {e}")
    return trailers


def collect_internet_verse_signals() -> Dict[str, Any]:
    """Collects multi-platform signals into a unified internet-verse brief."""
    logging.info("[LLM Brain] Ingesting real-time signals across Internet-Verse (News RSS, Reddit, YouTube Trailers)...")
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else {}
    recent_topics = cat.get("recent_topics", [])

    news = fetch_trade_news_headlines(max_items=15)
    reddit = fetch_reddit_hot_discussions(limit_per_sub=8)
    trailers = fetch_breaking_trailers_velocity(query="trailer official 2026", max_results=8)

    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "recent_produced_topics": recent_topics[-10:],
        "trade_news": news[:25],
        "reddit_threads": reddit[:20],
        "trending_trailers": trailers[:10],
    }


def analyze_with_gemini_brain(signals: Dict[str, Any], api_key: str | None = None) -> Dict[str, Any]:
    """
    Sends multi-platform signals to Gemini 2.5 Flash to synthesize cultural urgency,
    provide evidence-backed scores, and detect breaking cultural moments.
    """
    key = api_key or _get_gemini_api_key()
    if not key:
        logging.warning("[LLM Brain] No GEMINI_API_KEY found; falling back to heuristic scoring.")
        return fallback_heuristic_scoring(signals)

    system_instruction = (
        "You are the Chief Intelligence Analyst & Virality Forecaster for '@OtakuSnapster', a top 1% YouTube Shorts channel "
        "specializing in movie & series edits, character ranking shorts, and high-CTR cinematic pop-culture moments. "
        "Your task is to analyze real-time internet signals (trailer releases, Reddit debates, trade news) and determine "
        "the single most explosive cultural topic in the movie/internet verse RIGHT NOW. "
        "You must distinguish between massive breaking events (e.g. Avengers: Doomsday trailer drop, GTA 6 trailer, Nolan's new film, "
        "major MCU/DC casting shock, Stranger Things finale) versus everyday routine film news. "
        "Provide verifiable proof citing view counts, discussion intensity, or publication timing. "
        "Return STRICT JSON only, matching the exact requested schema."
    )

    prompt = f"""
Analyze the following real-time signals from the movie & internet verse:

RECENT TOPICS ALREADY PRODUCED (DO NOT DUPLICATE UNLESS A FRESH BREAKING EVENT OCCURRED):
{json.dumps(signals.get('recent_produced_topics', []), indent=2)}

TRADE NEWS HEADLINES (Deadline, Variety, THR, Collider):
{json.dumps([n['title'] for n in signals.get('trade_news', [])], indent=2)}

HOT REDDIT DISCUSSIONS (r/movies, r/boxoffice, r/marvelstudios, r/television):
{json.dumps([f"[{r['subreddit']}] {r['title']} (Upvotes: {r['upvotes']}, Comments: {r['comments']})" for r in signals.get('reddit_threads', [])], indent=2)}

YOUTUBE TRAILER VELOCITY:
{json.dumps([f"{t['title']} ({t['views']:,} views) by {t['channel']}" for t in signals.get('trending_trailers', [])], indent=2)}

Return a valid JSON object strictly matching this schema:
{{
  "breaking_event_detected": true/false (true if any topic has extreme viral hype >= 90 such as a massive trailer or casting drop),
  "breaking_winner": {{
    "topic": "Clean topic name (e.g. 'Avengers Doomsday' or 'Godzilla' or 'Patrick Jane')",
    "genre": "action_thriller|superhero_scifi|drama_prestige|crime_mafia|etc",
    "hype_score": 0 to 100,
    "urgency_level": "BREAKING_IMMEDIATE" (for >=90) | "TRENDING_HIGH" (75-89) | "ROUTINE" (<75),
    "proof_rationale": "Exact verifiable facts citing why this is dominating (e.g. 'Official trailer dropped with 20M+ views in 6h, dominating r/marvelstudios and r/movies frontpage')",
    "recommended_format": "edit_ranking" | "release_hype",
    "harvest_queries": [
      "query 1 edit #shorts",
      "query 2 edit shorts",
      "query 3 badass edit #shorts"
    ],
    "high_ctr_title": "Ranking Best [Topic] Edits! 🔥💀 #shorts #naofloppa #shortsfeed",
    "pinned_debate_comment": "Discussion question for comment section engagement"
  }},
  "top_ranked_contenders": [
    {{
      "topic": "Topic Name",
      "genre": "Genre",
      "hype_score": 0 to 100,
      "urgency_level": "BREAKING_IMMEDIATE|TRENDING_HIGH|ROUTINE",
      "proof_rationale": "Proof",
      "recommended_format": "edit_ranking",
      "harvest_queries": ["query 1", "query 2"]
    }}
  ],
  "reasoning_summary": "2-3 sentences explaining the cultural pulse and why the winner was chosen."
}}
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": system_instruction + "\n\n" + prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        }
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content_text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(content_text)
            logging.info(f"[LLM Brain] Successfully synthesized zeitgeist! Winner: '{result.get('breaking_winner', {}).get('topic')}' | Hype: {result.get('breaking_winner', {}).get('hype_score')} | Breaking: {result.get('breaking_event_detected')}")
            return result
    except Exception as e:
        logging.error(f"[LLM Brain] Gemini API execution failed: {e}; trying SLM #2 fallback...")
        try:
            from llm_director import run_text_slm
            slm_raw = run_text_slm(
                f"Pick the #1 trending entertainment topic from these signals and return JSON with keys "
                f"breaking_event_detected (false), breaking_winner ({{topic, genre, hype_score}}), top_ranked_contenders ([]). "
                f"Signals: {json.dumps(signals)[:1500]}",
                max_new_tokens=220,
            )
            if slm_raw:
                m = re.search(r"\{.*\}", slm_raw, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
        except Exception:
            pass
        return fallback_heuristic_scoring(signals)


def fallback_heuristic_scoring(signals: Dict[str, Any]) -> Dict[str, Any]:
    """Robust non-preempting fallback when Gemini & SLM #2 are unavailable."""
    return {
        "breaking_event_detected": False,
        "breaking_winner": {},
        "top_ranked_contenders": [],
        "reasoning_summary": "Fallback mode: deferring to live multi-platform Virality Radar scores.",
    }


def execute_virality_brain_scan() -> Dict[str, Any]:
    """End-to-end execution of the LLM Virality Brain with persistence."""
    signals = collect_internet_verse_signals()
    report = analyze_with_gemini_brain(signals)
    report["timestamp_utc"] = signals["timestamp_utc"]

    LLM_REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    logging.info(f"[LLM Brain] Full report saved to: {LLM_REPORT_PATH}")
    return report


if __name__ == "__main__":
    rep = execute_virality_brain_scan()
    print("\n--- LLM VIRALITY BRAIN OUTPUT ---")
    bw = rep.get("breaking_winner", {})
    print(f"Winner: '{bw.get('topic')}' | Hype Score: {bw.get('hype_score')} | Urgency: {bw.get('urgency_level')}")
    print(f"Proof: {bw.get('proof_rationale')}")
    print(f"Breaking Event Detected: {rep.get('breaking_event_detected')}")
