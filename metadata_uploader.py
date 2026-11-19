"""CTR metadata builder, Section 107 Fair-Use credits, and optional Private-Canary YouTube uploader."""

import datetime
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def build_metadata(
    topic: str,
    fmt: str,
    clips: list[dict],
    handle: str = "@OtakuSnapster",
) -> dict:
    slug_tag = "#" + "".join(ch for ch in topic.lower() if ch.isalnum())

    # Dynamically inject live weekly trending hashtags (including #naofloppa, #shortsfeed, etc.)
    try:
        from hashtag_harvester import harvest_trending_hashtags
        dynamic_trending_tags = harvest_trending_hashtags()
    except Exception:
        dynamic_trending_tags = ["#naofloppa", "#shortsfeed", "#viral", "#edits", "#phonk"]

    # Pick top 4 trending tags to append to title and description
    title_tags = " ".join(dynamic_trending_tags[:2])
    cloud_tags = " ".join(dynamic_trending_tags[:8])

    titles = {
        "edit_ranking": f"Ranking Best {topic} Edits! 🔥💀 #shorts {slug_tag} {title_tags}",
        "release_hype": f"This Week Is NOT Holding Back! ({topic}) 🔥🎬 #shorts {slug_tag}",
        "movie_trivia": f"Movie Scenes That Cost an INSANE Amount! 🤯🎬 #shorts #movies {title_tags}",
        "scene_commentary": f"Everyone Missed THIS Detail in {topic}! 💀🎬 #shorts {slug_tag}",
    }
    title = titles.get(fmt, f"{topic} Viral Moments Ranked! 🔥 #shorts {title_tags}")[:100]

    debate_comment = (
        f"👇 Honest take: Did #1 deserve the top spot for {topic}, or who got robbed? Drop your ranking!"
        if fmt == "edit_ranking"
        else f"👇 Which {topic} release or update are you most hyped for? Comment below! 🎬"
    )

    credits_lines = []
    for idx, c in enumerate(clips, 1):
        creator = c.get("creator") or c.get("source") or "Original Creator"
        url = c.get("url") or c.get("link") or ""
        credits_lines.append(f"• Clip {idx}: {creator} {f'({url})' if url else ''}".strip())

    tags = [
        "shorts", "movies", "series", "tvshows", "cinema", "movienews", "edits", "ranking",
        topic.lower(), "viral", "trending", "hollywood", "bollywood", "mcu", "netflix",
        "naofloppa", "shortsfeed",
    ]
    hashtags = f"#shorts #movies #series #cinema {slug_tag} {cloud_tags} #movienews"

    description = "\n".join([
        f"{title}",
        "",
        debate_comment,
        "",
        "Credits & Sources:",
        *(credits_lines or ["• Compiled from public news & cinema press stills."]),
        "",
        "Disclaimer & Copyright Notice (Section 107, Fair Use Act):",
        "This video is a transformative ranking, news reporting, and critical commentary edit.",
        "All visual clips, background scores, and media belong to their respective copyright owners.",
        "No copyright infringement intended. Under Section 107 of the Copyright Act 1976, allowance is made for 'fair use' for purposes such as criticism, comment, news reporting, teaching, scholarship, and research.",
        "",
        f"Channel: {handle}",
        "",
        f"Trending Tags: {hashtags}",
    ])

    return {
        "title": title,
        "description": description,
        "tags": tags[:15],
        "pinned_comment": debate_comment,
        "recommended_slot_utc": next_primetime_slot_utc(),
    }


def next_primetime_slot_utc() -> str:
    """Gets the next guaranteed unique 14:00 UTC (7:30 PM IST) prime-time Shorts slot without conflicts."""
    try:
        from queue_manager import get_next_available_daily_slot_utc
        return get_next_available_daily_slot_utc()
    except Exception:
        now = datetime.datetime.now(datetime.timezone.utc)
        slot = now.replace(hour=14, minute=0, second=0, microsecond=0)
        if slot <= now + datetime.timedelta(minutes=30):
            slot += datetime.timedelta(days=1)
        return slot.strftime("%Y-%m-%dT%H:%M:%SZ")


def upload_private_canary_and_schedule(
    video_path: Path,
    meta: dict,
    token_path: Path = ROOT / "config" / "youtube_token.json",
    canary_wait_sec: int = 120,
) -> dict:
    """Uploads PRIVATE first, checks status/licensedContent canary, schedules public only if clean."""
    # shortcut: YouTube Data API v3 exposes uploadStatus/rejectionReason/licensedContent, not full Studio claim details
    if not token_path.exists():
        raise FileNotFoundError(f"Missing YouTube OAuth token at {token_path}. Run in --dry-run until configured.")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials.from_authorized_user_file(str(token_path))
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta["tags"],
            "categoryId": "24",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=5 * 1024 * 1024, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid_id = resp["id"]
    print(f"[Uploader] Private canary uploaded: https://youtube.com/shorts/{vid_id}. Waiting {canary_wait_sec}s...")
    time.sleep(canary_wait_sec)

    check = youtube.videos().list(part="status,contentDetails", id=vid_id).execute()
    item = (check.get("items") or [{}])[0]
    status = item.get("status", {})
    cd = item.get("contentDetails", {})
    rejected = status.get("uploadStatus") == "rejected" or bool(status.get("rejectionReason"))
    licensed = bool(cd.get("licensedContent"))

    if rejected or licensed:
        print(f"[Uploader] HELD PRIVATE (canary flagged: rejected={rejected}, licensed={licensed})")
        return {"video_id": vid_id, "scheduled": False, "flagged": True}

    youtube.videos().update(
        part="status",
        body={
            "id": vid_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": meta["recommended_slot_utc"],
                "selfDeclaredMadeForKids": False,
            },
        },
    ).execute()
    print(f"[Uploader] Canary clean -> Scheduled for {meta['recommended_slot_utc']}")
    return {"video_id": vid_id, "scheduled": True, "publish_at": meta["recommended_slot_utc"]}
