"""
Universal Self-Contained Multi-Platform Video Downloader (YouTube, TikTok, Instagram, Reddit, Direct MP4).
Zero-dependency direct extractors + yt-dlp + pytubefix + curl_cffi impersonation + proxy fallbacks.
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


def _find_cookies_file() -> Optional[Path]:
    env_ck = os.environ.get("YOUTUBE_COOKIES_PATH", "").strip()
    candidates = [
        Path("config/cookies.txt"),
        ROOT / "config" / "cookies.txt",
        Path("/content/otaku_repo/config/cookies.txt"),
    ]
    if env_ck:
        candidates.append(Path(env_ck))
    return next((p.resolve() for p in candidates if p.is_file() and p.stat().st_size > 50), None)


def _download_stream(url: str, out_mp4: Path, headers: dict | None = None, timeout: int = 35) -> bool:
    hdrs = {"User-Agent": UA, **(headers or {})}
    try:
        req = urllib.request.Request(url, headers=hdrs)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        if len(data) > 20_000 and data[:4] != b"<!DO" and b"<html" not in data[:200].lower():
            out_mp4.write_bytes(data)
            return True
    except Exception:
        pass
    return False


def _extract_yt_id(url: str) -> Optional[str]:
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


def _download_youtube_innertube(url: str, out_mp4: Path) -> bool:
    """Direct YouTube InnerTube player API extractor (ANDROID / IOS / TVHTML5) — no yt-dlp required."""
    vid = _extract_yt_id(url)
    if not vid:
        return False
    clients = [
        {
            "clientName": "IOS",
            "clientVersion": "19.29.1",
            "deviceModel": "iPhone16,2",
            "osName": "iPhone",
            "osVersion": "17.5.1.21F90",
        },
        {
            "clientName": "ANDROID",
            "clientVersion": "19.29.37",
            "androidSdkVersion": 34,
        },
        {
            "clientName": "TVHTML5_SIMPLY_EMBEDDED_PLAYER",
            "clientVersion": "2.0",
        },
    ]
    for client in clients:
        try:
            payload = json.dumps({
                "videoId": vid,
                "context": {"client": client},
                "contentCheckOk": True,
                "racyCheckOk": True,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": UA},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            sd = data.get("streamingData") or {}
            formats = (sd.get("formats") or []) + (sd.get("adaptiveFormats") or [])
            mp4s = [f for f in formats if f.get("url") and "video/mp4" in (f.get("mimeType") or "") and f.get("audioQuality")]
            if not mp4s:
                mp4s = [f for f in (sd.get("formats") or []) if f.get("url")]
            mp4s.sort(key=lambda f: int(f.get("height") or 0), reverse=True)
            for fmt in mp4s[:2]:
                if _download_stream(fmt["url"], out_mp4, headers={"User-Agent": MOBILE_UA}):
                    return True
        except Exception:
            continue
    return False


def _download_tiktok_direct_html(url: str, out_mp4: Path) -> bool:
    """Direct TikTok HTML __UNIVERSAL_DATA_FOR_REHYDRATION__ / SIGI_STATE parser with cookie jar."""
    try:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with opener.open(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Search for playAddr or downloadAddr in embedded JSON
        for pat in (
            r'"playAddr"\s*:\s*"([^"]+)"',
            r'"downloadAddr"\s*:\s*"([^"]+)"',
        ):
            m = re.search(pat, html)
            if m:
                mp4_url = m.group(1).encode("utf-8").decode("unicode_escape").replace("\\/", "/")
                if mp4_url.startswith("http"):
                    req_v = urllib.request.Request(mp4_url, headers={"User-Agent": UA, "Referer": "https://www.tiktok.com/"})
                    with opener.open(req_v, timeout=30) as vr:
                        data = vr.read()
                    if len(data) > 20_000 and b"<html" not in data[:200].lower():
                        out_mp4.write_bytes(data)
                        return True
    except Exception:
        pass
    return False


def _download_instagram_direct(url: str, out_mp4: Path, cookies_file: Optional[Path] = None) -> bool:
    """Direct Instagram Reel extractor: Embed endpoint -> GraphQL ?__a=1 -> webpage video_url/og:video."""
    m = re.search(r"instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:reel|p|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        return False
    code = m.group(1)

    opener_handlers = []
    if cookies_file and cookies_file.exists():
        try:
            cj = http.cookiejar.MozillaCookieJar(str(cookies_file))
            cj.load(ignore_discard=True, ignore_expires=True)
            opener_handlers.append(urllib.request.HTTPCookieProcessor(cj))
        except Exception:
            pass
    opener = urllib.request.build_opener(*opener_handlers)

    endpoints = [
        f"https://www.instagram.com/reel/{code}/embed/captioned/",
        f"https://www.instagram.com/reel/{code}/embed/",
        f"https://www.instagram.com/p/{code}/?__a=1&__d=dis",
        f"https://www.instagram.com/reel/{code}/",
    ]
    headers = {
        "User-Agent": MOBILE_UA,
        "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
    }
    for ep in endpoints:
        try:
            req = urllib.request.Request(ep, headers=headers)
            with opener.open(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            for pat in (
                r'"video_url"\s*:\s*"([^"]+)"',
                r'"contentUrl"\s*:\s*"([^"]+)"',
                r'<meta[^>]+property=["\']og:video["\'][^>]+content=["\']([^"\']+)["\']',
                r'<video[^>]+src=["\']([^"\']+)["\']',
            ):
                vm = re.search(pat, body)
                if vm:
                    vid_u = vm.group(1).replace("\\u0026", "&").replace("\\/", "/").replace("&amp;", "&")
                    if vid_u.startswith("http") and _download_stream(vid_u, out_mp4, headers={"Referer": "https://www.instagram.com/"}):
                        return True
        except Exception:
            continue
    return False


def download_video(url: str, out_mp4: Path, browser_cookies: str = "") -> Optional[Path]:
    """
    Universal resilient downloader for YouTube, TikTok, Instagram, Reddit, and direct MP4s.
    Returns Path on success, None on failure.
    """
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    if out_mp4.exists() and out_mp4.stat().st_size > 20_000:
        return out_mp4

    # 0. Direct MP4 URL
    if re.search(r"\.mp4(?:\?|$)", url, re.I) or "tikwm.com" in url:
        if _download_stream(url, out_mp4):
            return out_mp4

    cookies_file = _find_cookies_file()
    cookie_args = ["--cookies", str(cookies_file)] if cookies_file else (["--cookies-from-browser", browser_cookies] if browser_cookies else [])
    base_cmd = [
        sys.executable, "-m", "yt_dlp",
        "-f", "best[height<=1080][ext=mp4]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--no-warnings", "--retries", "2", "--socket-timeout", "15",
        "-o", str(out_mp4.with_suffix(".%(ext)s")),
    ]

    is_yt = "youtube.com" in url or "youtu.be" in url
    is_tt = "tiktok.com" in url
    is_ig = "instagram.com" in url

    # 1. YOUTUBE
    if is_yt:
        # 1a. yt-dlp clients (mweb/cookies, ios, android_vr, tv_embedded)
        attempts = [
            ["--extractor-args", "youtube:player_client=ios", "--no-cookies"],
            ["--extractor-args", "youtube:player_client=android_vr", "--no-cookies"],
            ["--extractor-args", "youtube:player_client=mweb", "--no-cookies"],
            ["--extractor-args", "youtube:player_client=tv_embedded", "--no-cookies"],
        ]
        if cookie_args:
            attempts.insert(0, ["--extractor-args", "youtube:player_client=mweb"] + cookie_args)
            attempts.append(["--extractor-args", "youtube:player_client=web"] + cookie_args)

        for extra in attempts:
            try:
                proc = subprocess.run(base_cmd + extra + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
                if proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                    return out_mp4
            except Exception:
                continue

        # 1b. Direct InnerTube API
        if _download_youtube_innertube(url, out_mp4):
            return out_mp4

        # 1c. pytubefix
        try:
            from pytubefix import YouTube
            for cl in ("WEB", "ANDROID_VR", "IOS"):
                try:
                    yt = YouTube(url, client=cl)
                    st = yt.streams.filter(progressive=True, file_extension="mp4").order_by("resolution").desc().first()
                    if st:
                        st.download(output_path=str(out_mp4.parent), filename=out_mp4.name)
                        if out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                            return out_mp4
                except Exception:
                    continue
        except ImportError:
            pass

    # 2. TIKTOK
    elif is_tt:
        # 2a. Direct HTML JSON parser
        if _download_tiktok_direct_html(url, out_mp4):
            return out_mp4
        # 2b. TikWM API
        try:
            from proxy_harvester import resolve_tikwm_mp4
            play_u = resolve_tikwm_mp4(url)
            if play_u and _download_stream(play_u, out_mp4, headers={"Referer": "https://www.tikwm.com/"}):
                return out_mp4
        except Exception:
            pass
        # 2c. yt-dlp with curl_cffi impersonation
        imp = []
        try:
            import curl_cffi  # noqa: F401
            imp = ["--impersonate", "chrome"]
        except ImportError:
            pass
        try:
            proc = subprocess.run(base_cmd + imp + cookie_args + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                return out_mp4
        except Exception:
            pass

    # 3. INSTAGRAM
    elif is_ig:
        # 3a. Direct Instagram Embed / GraphQL / Webpage extractor
        if _download_instagram_direct(url, out_mp4, cookies_file=cookies_file):
            return out_mp4
        # 3b. yt-dlp with cookies + impersonation
        try:
            proc = subprocess.run(base_cmd + cookie_args + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                return out_mp4
        except Exception:
            pass

    # 4. REDDIT / FACEBOOK / GENERIC
    else:
        try:
            proc = subprocess.run(base_cmd + cookie_args + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
            if proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                return out_mp4
        except Exception:
            pass

    # 5. Last-resort rotating proxies + Cobalt
    try:
        from proxy_harvester import download_via_cobalt, get_working_proxies
        if (is_tt or is_ig) and download_via_cobalt(url, out_mp4):
            return out_mp4
        for proxy in get_working_proxies(limit=4):
            try:
                proc_px = subprocess.run(
                    base_cmd + ["--no-cookies", "--proxy", proxy, url],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45,
                )
                if proc_px.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 20_000:
                    return out_mp4
            except Exception:
                continue
    except Exception:
        pass

    return None
