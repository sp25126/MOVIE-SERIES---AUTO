"""
One-Time YouTube OAuth 2.0 Authenticator for @OtakuSnapster.
Generates config/youtube_token.json for local testing & GitHub Actions secret.
"""

import json
import sys
import webbrowser
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
        print(f"ERROR: {CLIENT_SECRETS_PATH} does not exist!", flush=True)
        return

    print("=" * 70, flush=True)
    print("Starting YouTube OAuth flow on port 8080...", flush=True)
    print("=" * 70, flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        SCOPES,
    )
    # run_local_server on port 8080
    creds = flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message="Please visit this URL to authorize: {url}",
        success_message="Authentication successful! You may close this tab.",
        open_browser=True,
        prompt="consent",
        access_type="offline",
    )

    TOKEN_OUTPUT_PATH.write_text(creds.to_json(), encoding="utf-8")
    print("\n" + "=" * 70, flush=True)
    print("✅ AUTHENTICATION SUCCESSFUL!", flush=True)
    print(f"Token saved to: {TOKEN_OUTPUT_PATH}", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
