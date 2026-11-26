import cv2, base64, json, urllib.request, os
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

video_path = "input/yt_KZm6HRhW21Q.mp4"
cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = total_frames / fps
print(f"Video {video_path}: {duration:.1f}s, {total_frames} frames")

# Sample 6 frames across timeline: 10%, 25%, 45%, 65%, 85%, 95%
ratios = [0.10, 0.25, 0.45, 0.65, 0.85, 0.95]
images_b64 = []
for r in ratios:
    sec = r * duration
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(sec * fps))
    ret, frame = cap.read()
    if ret:
        h, w = frame.shape[:2]
        new_w = 480
        new_h = int(h * (480 / w))
        resized = cv2.resize(frame, (new_w, new_h))
        _, buf = cv2.imencode(".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 75])
        images_b64.append((sec, base64.b64encode(buf).decode("utf-8")))
cap.release()

prompt = f"""You are an elite short-form video editor for YouTube Shorts and TikTok.
Analyze these 6 sequential frames sampled across a {duration:.1f}-second edit clip:
- Frame 1: at {images_b64[0][0]:.1f}s
- Frame 2: at {images_b64[1][0]:.1f}s
- Frame 3: at {images_b64[2][0]:.1f}s
- Frame 4: at {images_b64[3][0]:.1f}s
- Frame 5: at {images_b64[4][0]:.1f}s
- Frame 6: at {images_b64[5][0]:.1f}s

Provide a JSON evaluation with:
- "approved": bool (false if low-effort, watermarked spam, or static slideshow)
- "quality_score": float (1 to 10)
- "scene_label": string (2-3 words for on-screen HUD, e.g. "Spider-Verse Leap")
- "optimal_cut": {{"start_sec": float, "end_sec": float, "reason": string}}
- "hook_description": string
- "climax_description": string

Respond ONLY with valid JSON. Do not include markdown codeblocks or extra text.
"""

parts = [{"text": prompt}]
for sec, b64 in images_b64:
    parts.append({
        "inline_data": {
            "mime_type": "image/jpeg",
            "data": b64
        }
    })

req_body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"})

with urllib.request.urlopen(req, timeout=30) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    txt = res["candidates"][0]["content"]["parts"][0]["text"]
    print("\n--- GEMINI 2.5 FLASH FRAME ANALYSIS ---")
    print(txt)
