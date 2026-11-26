import urllib.request, json, os, re
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")

topic = "Godzilla"
genre = "superhero_scifi"
clips_info = "1. Godzilla Minus Zero Atomic Breath\n2. Godzilla vs Kong Hollow Earth\n3. King of Monsters Burning Godzilla"

prompt = f"""You are an elite YouTube Shorts SEO expert and viral copywriter.
For this video topic: "{topic}" (Genre: {genre})
Featured clips:
{clips_info}

Respond with ONLY valid JSON:
{{
  "title": "string (punchy, high-CTR, under 65 chars, with 1-2 dynamic topic-matching emojis and #shorts #{topic.lower().replace(' ', '')})",
  "pinned_comment": "string (spicy debate question asking viewers if #1 deserved it or who was robbed)",
  "topic_seo_tags": ["list", "of", "10", "specific", "entity", "tags"],
  "viral_trending_tags": ["#shorts", "#viral", "#trending", "#reels", "#explore", "#fyp", "#cinematic", "#edits"]
}}"""

req_body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
req = urllib.request.Request(url, data=req_body, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=15) as resp:
    res = json.loads(resp.read().decode())
    txt = res["candidates"][0]["content"]["parts"][0]["text"]
    print("AI METADATA RESPONSE:")
    print(txt)
