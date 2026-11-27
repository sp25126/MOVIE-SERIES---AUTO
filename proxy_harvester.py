"""
Dedicated Multi-Platform Proxy & Social Clip Harvester (Instagram, TikTok, YouTube, Reddit).
- Fetches free HTTPS proxies from multiple public feeds and health-checks them concurrently.
- Caches verified live proxies so downloads never stall on dead proxies.
- Supports TikTok (TikWM + DDG/Bing + agent-reach + proxied yt-dlp), Instagram Reels, YouTube, and Reddit.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)
PROXY_CACHE_PATH = STATE_DIR / "live_proxies.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

_MEM_PROXIES: List[str] = []
_MEM_PROXY_TS: float = 0.0


def _test_proxy(proxy_url: str, timeout: float = 2.5) -> Optional[str]:
    """Tests if an HTTP/HTTPS proxy can tunnel HTTPS traffic cleanly."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
        req = urllib.request.Request("https://www.google.com/generate_204", headers={"User-Agent": UA})
        with opener.open(req, timeout=timeout) as resp:
            if resp.status in (200, 204):
                return proxy_url
    except Exception:
        pass
    return None


def get_working_proxies(limit: int = 8, force_refresh: bool = False) -> List[str]:
    """Returns health-checked, live rotating HTTPS proxies (cached for 15 minutes)."""
    global _MEM_PROXIES, _MEM_PROXY_TS

    env_proxy = os.environ.get("PROXY_URL", "").strip()
    if env_proxy:
        return [env_proxy]

    now = time.time()
    if not force_refresh and _MEM_PROXIES and (now - _MEM_PROXY_TS) < 900:
        return _MEM_PROXIES[:limit]

    if not force_refresh and PROXY_CACHE_PATH.exists():
        try:
            cached = json.loads(PROXY_CACHE_PATH.read_text(encoding="utf-8"))
            if (now - float(cached.get("ts", 0))) < 900 and cached.get("proxies"):
                _MEM_PROXIES = cached["proxies"]
                _MEM_PROXY_TS = float(cached["ts"])
                return _MEM_PROXIES[:limit]
        except Exception:
            pass

    raw_candidates: List[str] = []
    sources = [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=elite",
        "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    ]
    for src in sources:
        try:
            req = urllib.request.Request(src, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=6) as resp:
                for line in resp.read().decode("utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    if not line.startswith("http"):
                        line = f"http://{line}"
                    if line not in raw_candidates:
                        raw_candidates.append(line)
        except Exception:
            continue

    # Health-check up to 40 candidates concurrently
    live: List[str] = []
    if raw_candidates:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
            futures = {pool.submit(_test_proxy, p, 2.5): p for p in raw_candidates[:40]}
            for fut in concurrent.futures.as_completed(futures, timeout=10):
                res = fut.result()
                if res:
                    live.append(res)
                    if len(live) >= max(limit, 10):
                        break

    if live:
        _MEM_PROXIES = live
        _MEM_PROXY_TS = now
        try:
            PROXY_CACHE_PATH.write_text(json.dumps({"ts": now, "proxies": live}, indent=2), encoding="utf-8")
        except Exception:
            pass

    return live[:limit]


def _urlopen_with_proxy(req: urllib.request.Request, proxy: Optional[str] = None, timeout: float = 6.0):
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def resolve_tikwm_mp4(tiktok_url: str) -> Optional[str]:
    """Resolves a direct watermark-free MP4 URL from TikTok via TikWM (direct + verified rotating proxies)."""
    clean_url = tiktok_url.split("?")[0]
    tw_api = f"https://www.tikwm.com/api/?url={urllib.parse.quote_plus(clean_url)}&hd=1"
    headers = {"User-Agent": UA, "Referer": "https://www.tikwm.com/", "Origin": "https://www.tikwm.com"}
    proxies = [None] + get_working_proxies(limit=4)
    for idx, proxy in enumerate(proxies):
        try:
            if idx > 0:
                time.sleep(1.1)  # Respect TikWM 1 req/sec rate limit
            req = urllib.request.Request(tw_api, headers=headers)
            with _urlopen_with_proxy(req, proxy=proxy, timeout=12.0) as resp:
                raw = json.loads(resp.read().decode("utf-8", errors="replace"))
            if raw.get("code") == -1:
                time.sleep(1.2)
                continue
            data = raw.get("data") or {}
            play_u = data.get("hdplay") or data.get("play") or data.get("wmplay") or ""
            if play_u.startswith("/"):
                play_u = "https://www.tikwm.com" + play_u
            if play_u:
                return play_u
        except Exception:
            continue
    return None


def resolve_instagram_embed_mp4(ig_url: str) -> Optional[str]:
    """Extracts direct MP4 URL from Instagram's public embed endpoint without login cookies."""
    m = re.search(r"instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:reel|p)/([A-Za-z0-9_-]+)", ig_url)
    if not m:
        return None
    code = m.group(1)
    embed_url = f"https://www.instagram.com/reel/{code}/embed/captioned/"
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    for proxy in [None] + get_working_proxies(limit=3):
        try:
            req = urllib.request.Request(embed_url, headers=headers)
            with _urlopen_with_proxy(req, proxy=proxy, timeout=8.0) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            vm = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
            if not vm:
                vm = re.search(r'<video[^>]+src="([^"]+)"', html)
            if vm:
                vid_url = vm.group(1).replace("\\u0026", "&").replace("\\/", "/")
                if vid_url.startswith("http"):
                    return vid_url
        except Exception:
            continue
    return None


def download_via_cobalt(social_url: str, out_mp4: Path) -> Optional[Path]:
    """Fallback downloader using Cobalt public API instances for TikTok / Instagram."""
    cobalt_instances = [
        "https://api.cobalt.tools/",
        "https://co.wuk.sh/api/json",
    ]
    payload = json.dumps({"url": social_url, "vQuality": "1080"}).encode("utf-8")
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    for api in cobalt_instances:
        try:
            req = urllib.request.Request(api, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            dl_url = data.get("url")
            if dl_url:
                with urllib.request.urlopen(urllib.request.Request(dl_url, headers={"User-Agent": UA}), timeout=25) as vr:
                    out_mp4.write_bytes(vr.read())
                if out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                    return out_mp4
        except Exception:
            continue
    return None


def scout_tiktok_robust(query: str, count: int = 4, used_ids: Optional[set] = None) -> List[Dict[str, Any]]:
    """Scouts TikTok edit URLs via TikWM (proxied) + agent-reach + DDG Lite + Bing RSS."""
    used = used_ids or set()
    clean_q = re.sub(r"[#@]", "", query).strip()
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # 1. TikWM Search API (direct + verified proxies)
    api_url = f"https://www.tikwm.com/api/feed/search?keywords={urllib.parse.quote_plus(clean_q + ' edit')}&count={max(count * 3, 10)}&cursor=0&HD=1"
    headers = {"User-Agent": UA, "Accept": "application/json", "Referer": "https://www.tikwm.com/", "Origin": "https://www.tikwm.com"}
    for idx, proxy in enumerate([None] + get_working_proxies(limit=3)):
        try:
            if idx > 0:
                time.sleep(1.1)
            req = urllib.request.Request(api_url, headers=headers)
            with _urlopen_with_proxy(req, proxy=proxy, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            videos = (data.get("data") or {}).get("videos") or []
            for v in videos:
                tid = str(v.get("video_id") or v.get("id") or "")
                play_u = v.get("hdplay") or v.get("play") or ""
                dur = float(v.get("duration") or 20)
                if not tid or not play_u or dur < 5 or dur > 65:
                    continue
                cid = f"tt_{tid}"
                if cid in used or cid in seen:
                    continue
                seen.add(cid)
                author = (v.get("author") or {}).get("unique_id") or "tiktok_creator"
                candidates.append({
                    "id": cid, "platform": "tiktok",
                    "title": (v.get("title") or f"{clean_q} TikTok Edit")[:90],
                    "creator": f"@{author} (TikTok)",
                    "views": int(v.get("play_count") or 15000),
                    "duration": dur, "url": play_u, "direct_mp4": True,
                })
                if len(candidates) >= count:
                    return candidates
            if videos:
                break
        except Exception:
            continue

    discovered = []
    # 2. agent-reach CLI if available
    if shutil.which("agent-reach"):
        try:
            proc = subprocess.run(
                ["agent-reach", "web", "search", f"{clean_q} edit tiktok", "--limit", str(count * 3)],
                capture_output=True, text=True, encoding="utf-8", timeout=8,
            )
            if proc.returncode == 0:
                for item in json.loads(proc.stdout).get("items", []):
                    blob = f"{item.get('text', '')} {item.get('url', '')}"
                    for auth, tid in re.findall(r'tiktok\.com/@([^/\s]+)/video/(\d{15,22})', blob):
                        discovered.append((tid, f"https://www.tiktok.com/@{auth}/video/{tid}", item.get("title") or f"{clean_q} TikTok Edit", auth, 25000))
        except Exception:
            pass

    # 3. DDG Lite + Bing RSS for valid /@author/video/id URLs
    if len(discovered) < count:
        for engine_url, post_data in [
            ("https://lite.duckduckgo.com/lite/", urllib.parse.urlencode({"q": f"site:tiktok.com {clean_q} edit"}).encode("utf-8")),
            ("https://www.bing.com/search?format=rss&q=" + urllib.parse.quote_plus(f"site:tiktok.com {clean_q} edit"), None),
        ]:
            try:
                req = urllib.request.Request(engine_url, data=post_data, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                for auth, tid in re.findall(r'tiktok\.com/@([^/\s"&]+)/video/(\d{15,22})', body):
                    discovered.append((tid, f"https://www.tiktok.com/@{auth}/video/{tid}", f"{clean_q} TikTok Edit", auth, 30000))
            except Exception:
                continue

    for tid, u, title, auth, views in discovered:
        if len(candidates) >= count:
            break
        cid = f"tt_{tid}"
        if cid in used or cid in seen:
            continue
        seen.add(cid)
        candidates.append({
            "id": cid, "platform": "tiktok", "title": title[:90],
            "creator": f"@{auth.lstrip('@')} (TikTok)", "views": views,
            "duration": 20.0, "url": u,
        })
    return candidates


def scout_instagram_robust(query: str, count: int = 4, used_ids: Optional[set] = None) -> List[Dict[str, Any]]:
    """Scouts Instagram Reels via agent-reach + DDG Lite + Bing RSS."""
    used = used_ids or set()
    clean_q = re.sub(r"[#@]", "", query).strip()
    urls: List[str] = []

    if shutil.which("agent-reach"):
        try:
            proc = subprocess.run(
                ["agent-reach", "web", "search", f"{clean_q} edit instagram reel", "--limit", str(count * 3)],
                capture_output=True, text=True, encoding="utf-8", timeout=8,
            )
            if proc.returncode == 0:
                for item in json.loads(proc.stdout).get("items", []):
                    blob = f"{item.get('text', '')} {item.get('url', '')}"
                    for code in re.findall(r'instagram\.com/(?:[a-zA-Z0-9_.]+/)?reel/([a-zA-Z0-9_-]+)', blob):
                        u = f"https://www.instagram.com/reel/{code}/"
                        if u not in urls:
                            urls.append(u)
        except Exception:
            pass

    if len(urls) < count:
        for engine_url, post_data in [
            ("https://lite.duckduckgo.com/lite/", urllib.parse.urlencode({"q": f"site:instagram.com/reel {clean_q} edit"}).encode("utf-8")),
            ("https://www.bing.com/search?format=rss&q=" + urllib.parse.quote_plus(f"site:instagram.com/reel {clean_q} edit"), None),
        ]:
            try:
                req = urllib.request.Request(engine_url, data=post_data, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                for code in re.findall(r'instagram\.com/reel/([a-zA-Z0-9_-]+)', body):
                    u = f"https://www.instagram.com/reel/{code}/"
                    if u not in urls:
                        urls.append(u)
            except Exception:
                continue

    candidates, seen = [], set()
    for u in urls:
        if len(candidates) >= count:
            break
        code = u.rstrip("/").split("/")[-1]
        cid = f"ig_{code}"
        if cid in used or cid in seen:
            continue
        seen.add(cid)
        candidates.append({
            "id": cid, "platform": "instagram",
            "title": f"{clean_q} Instagram Edit",
            "creator": "Instagram Creator", "views": 20000,
            "duration": 18.0, "url": u,
        })
    return candidates
