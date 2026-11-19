"""
One-Time YouTube OAuth 2.0 Authenticator for @OtakuSnapster.
Generates config/youtube_token.json for local testing & GitHub Actions secret.
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

CLIENT_SECRETS_PATH = CONFIG_DIR / "client_secret.json"
TOKEN_OUTPUT_PATH = CONFIG_DIR / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    if not CLIENT_SECRETS_PATH.exists():
        # Check if user put it in root or with different name
        candidates = list(ROOT.glob("*client_secret*.json")) + list(CONFIG_DIR.glob("*client_secret*.json"))
        if candidates:
            secrets_file = candidates[0]
            print(f"Found client secrets at: {secrets_file}")
        else:
            print("\n" + "=" * 60)
            print("❌ CLIENT SECRETS FILE MISSING!")
            print("=" * 60)
            print("Please follow these quick steps:")
            print("1. Go to Google Cloud Console: https://console.cloud.google.com/")
            print("2. Create a project and enable 'YouTube Data API v3'")
            print("3. Go to 'APIs & Services' -> 'Credentials' -> 'Create Credentials' -> 'OAuth client ID'")
            print("4. Application type: Choose 'Desktop app'")
            print("5. Download the JSON file and save it as:")
            print(f"   {CLIENT_SECRETS_PATH}")
            print("=" * 60 + "\n")
            return
    else:
        secrets_file = CLIENT_SECRETS_PATH

    print(f"Starting browser OAuth flow using: {secrets_file.name}...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    TOKEN_OUTPUT_PATH.write_text(creds.to_json(), encoding="utf-8")
    print("\n" + "=" * 60)
    print("✅ AUTHENTICATION SUCCESSFUL!")
    print(f"Token saved to: {TOKEN_OUTPUT_PATH}")
    print("=" * 60)
    print("\nNext step for 100% Autonomous Cloud Automation (GitHub Actions):")
    print("1. Open config/youtube_token.json and copy its entire text.")
    print("2. Go to your GitHub repository -> Settings -> Secrets and variables -> Actions")
    print("3. Click 'New repository secret'")
    print("   Name:  YOUTUBE_TOKEN_JSON")
    print("   Value: Paste the full JSON content from config/youtube_token.json")
    print("4. Click 'Add secret'. You are done! The cloud runner will now auto-upload.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
