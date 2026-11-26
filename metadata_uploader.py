"""CTR metadata builder, Section 107 Fair-Use credits, and optional Private-Canary YouTube uploader."""

import datetime
import hashlib
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Genre and topic-aware high-CTR emotional emoji palettes
EMOJI_PALETTES = {
    # Psychological, crime, thriller, mystery
    "mentalist": ["🧠♟️", "🥶🍷", "👁️🕵️‍♂️", "🍷🧠"],
    "patrick jane": ["🧠♟️", "🥶🍷", "☕♟️", "🍷🧠"],
    "sherlock": ["🔍🎻", "🧠⚡", "🕵️‍♂️♟️"],
    "dexter": ["🩸🔪", "🍷💀", "🕶️🩸"],
    "death note": ["🍎📓", "🧠⚡", "♟️💀"],
    # Horror, survival, psychological games
    "squid game": ["🎯🩸", "💀⚡", "🚨🎲", "⚡🩸"],
    "alice in borderland": ["♠️🃏", "⚡🎲", "🩸🎯"],
    # Action, superhero, sci-fi
    "avengers": ["⚡🎬", "💥🔥", "🛡️⚡", "🔥🎬"],
    "doomsday": ["⚡💥", "🔥🎬", "🛡️⚡", "💀⚡"],
    "batman": ["🦇⚡", "🌑🔥", "🦇💥"],
    "spiderman": ["🕷️⚡", "🕸️🔥", "🕷️💥"],
    "spiderverse": ["🕷️✨", "🕸️⚡", "🎨🕷️"],
    "marvel": ["⚡🎬", "💥🔥", "🛡️⚡"],
    # Song trends, music, emotional
    "heartless": ["🖤🎧", "🥀✨", "🖤🎶", "✨🎧"],
    "weeknd": ["🖤🎧", "🥀✨", "🖤🎶", "✨🎧"],
    "dilruba": ["✨🥀", "🎶🔥", "🖤✨", "🎵✨"],
    "song": ["🎵✨", "🎶🔥", "🎧✨", "🖤🎶"],
    # Mythological, epic
    "ramayana": ["🏹✨", "🔱🔥", "👑✨", "🏹🔱"],
    "adipurush": ["🏹✨", "🔱🔥", "👑✨"],
    # Romance, K-Drama
    "my demon": ["🖤✨", "😈🥀", "✨🥀", "🖤😈"],
    "kdrama": ["✨🥀", "🖤✨", "🎭✨"],
    # Anime, shonen
    "anime": ["⚔️🔥", "⚡💥", "🔥⚡", "🗡️⚡"],
    "jujutsu": ["🤞⚡", "🩸🔥", "⚡💀"],
    "naruto": ["🍥🔥", "⚡🦊", "🔥⚔️"],
}

DEFAULT_EMOJIS = ["🔥🎬", "⚡🔥", "🤯🎬", "💥🍿", "🏆🔥", "⚡🍿"]


def get_topic_emojis(topic: str) -> str:
    """Selects a context-aware high-CTR emoji pair based on topic and genre sentiment."""
    tl = topic.lower()
    for key, palette in EMOJI_PALETTES.items():
        if key in tl:
            idx = int(hashlib.md5(topic.encode("utf-8")).hexdigest(), 16) % len(palette)
            return palette[idx]
    idx = int(hashlib.md5(topic.encode("utf-8")).hexdigest(), 16) % len(DEFAULT_EMOJIS)
    return DEFAULT_EMOJIS[idx]


def get_contextual_hashtags(topic: str, clips: list[dict]) -> tuple[str, list[str]]:
    """Generates relevant, topic-specific hashtags and tag keywords (zero spam/generic filler)."""
    slug_tag = "#" + "".join(ch for ch in topic.lower() if ch.isalnum())
    topic_clean = re.sub(r"[^A-Za-z0-9 ]+", " ", topic).strip()
    words = [w.lower() for w in topic_clean.split() if len(w) > 2]

    # Collect entity keywords from topic and clips
    tags = ["shorts", "edits", "ranking", "viral", "trending", "cinema", "tvseries"]
    tags.extend(words)

    # Extract unique creator tags & edit titles
    for c in clips:
        creator = c.get("creator") or ""
        c_clean = "".join(ch for ch in creator.lower() if ch.isalnum())
        if c_clean and len(c_clean) > 2 and c_clean not in tags:
            tags.append(c_clean)

    # Add topic slug
    if topic.lower() not in tags:
        tags.insert(0, topic.lower())

    # Build clean description cloud tags (relevant to movies, series, edits)
    cloud_tags = [slug_tag, "#shorts", "#viral", "#edits", "#trending", "#cinema"]
    for w in words[:3]:
        cloud_tags.append(f"#{w}")

    seen = set()
    deduped_cloud = []
    for ct in cloud_tags:
        if ct.lower() not in seen:
            seen.add(ct.lower())
            deduped_cloud.append(ct)

    return slug_tag, " ".join(deduped_cloud[:8]), tags[:15]


def build_metadata(
    topic: str,
    fmt: str,
    clips: list[dict],
    handle: str = "@OtakuSnapster",
) -> dict:
    slug_tag, cloud_tags, tags = get_contextual_hashtags(topic, clips)
    emojis = get_topic_emojis(topic)

    titles = {
        "edit_ranking": f"Ranking Best {topic} Edits! {emojis} #shorts {slug_tag}",
        "release_hype": f"This Week Is NOT Holding Back! ({topic}) {emojis} #shorts {slug_tag}",
        "movie_trivia": f"Movie Scenes That Cost an INSANE Amount! 🤯🎬 #shorts #movies",
        "scene_commentary": f"Everyone Missed THIS Detail in {topic}! 💀🎬 #shorts {slug_tag}",
    }
    title = titles.get(fmt, f"{topic} Viral Moments Ranked! {emojis} #shorts {slug_tag}")[:100]

    debate_comment = (
        f"👇 Honest take: Did #1 deserve the top spot for {topic}, or who got robbed? Drop your ranking!"
        if fmt == "edit_ranking"
        else f"👇 Which {topic} release or update are you most hyped for? Comment below! 🎬"
    )

    credits_lines = []
    rank_medals = {1: "🥇 Rank #1 (Gold)", 2: "🥈 Rank #2 (Silver)", 3: "🥉 Rank #3 (Bronze)"}
    for idx, c in enumerate(clips, 1):
        creator = c.get("creator") or c.get("source") or "Original Creator"
        clip_title = c.get("title") or f"Edit #{idx}"
        url = c.get("url") or c.get("link") or ""
        medal = rank_medals.get(idx, f"• Rank #{idx}")
        entry = f"{medal}: {creator} — \"{clip_title}\""
        if url:
            entry += f"\n  ▶ Watch Original: {url}"
        credits_lines.append(entry)

    hashtags = f"{cloud_tags} #movienews"

    description = "\n".join([
        f"{title}",
        "",
        debate_comment,
        "",
        "🔥 Featured Edits & Original Creator Credits:",
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
    """Gets the next guaranteed unique 7:30 PM IST (14:00 UTC) prime-time Shorts slot (1 video per day)."""
    try:
        from queue_manager import get_next_available_slot_utc
        slot_iso, _ = get_next_available_slot_utc(min_lead_time_minutes=45)
        return slot_iso
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
    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception as e:
            print(f"[Uploader] Warning: Token refresh failed: {e}")
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

    # Record scheduled video in upload_queue.json
    try:
        from queue_manager import load_upload_queue, save_upload_queue
        q_data = load_upload_queue()
        q_data["queue"].append({
            "video_id": vid_id,
            "scheduled": True,
            "publish_at": meta["recommended_slot_utc"],
            "title": meta.get("title", ""),
            "uploaded_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
        save_upload_queue(q_data)
    except Exception as e:
        print(f"[Uploader] Warning: failed to record in upload_queue.json: {e}")

    # Release file handle before unlinking on Windows
    try:
        del req
        del media
        import gc
        gc.collect()
    except Exception:
        pass

    # Delete local master MP4 to prevent disk bloat
    try:
        if video_path.exists():
            video_path.unlink(missing_ok=True)
            print(f"[Uploader] Cleaned up local master MP4: {video_path}")
    except Exception as e:
        print(f"[Uploader] Could not delete {video_path}: {e}")

    return {"video_id": vid_id, "scheduled": True, "publish_at": meta["recommended_slot_utc"]}


def reschedule_youtube_video(video_id: str, new_publish_at_iso: str, token_path: Path = ROOT / "config" / "youtube_token.json") -> bool:
    """Updates the scheduled publishing time of a private canary video in YouTube Studio via YouTube Data API v3."""
    if not token_path.exists():
        print(f"[Uploader] No token found at {token_path}; local schedule updated only.")
        return False

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request

    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        except Exception:
            pass
    youtube = build("youtube", "v3", credentials=creds)

    try:
        youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {
                    "privacyStatus": "private",
                    "publishAt": new_publish_at_iso,
                    "selfDeclaredMadeForKids": False,
                },
            },
        ).execute()
        print(f"[Uploader] Successfully rescheduled YouTube video {video_id} -> {new_publish_at_iso}")
        return True
    except Exception as e:
        print(f"[Uploader] Failed to reschedule YouTube video {video_id}: {e}")
        return False
