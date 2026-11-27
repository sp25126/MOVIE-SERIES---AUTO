"""
One-Time YouTube OAuth 2.0 Authenticator for @OtakuSnapster.
Generates config/youtube_token.json for local testing & GitHub Actions secret.
Allows manual paste of the redirect URL/code to prevent MismatchingStateError from browser caching.
"""

import json
import sys
import webbrowser
import urllib.parse
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
    print("YouTube OAuth 2.0 Authentication Helper", flush=True)
    print("=" * 70, flush=True)

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CLIENT_SECRETS_PATH),
        SCOPES,
        redirect_uri="http://localhost:8080/",
    )

    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")

    print("\n👉 STEP 1: Open this URL in your browser:\n")
    print(auth_url)
    print("\n" + "-" * 70)
    webbrowser.open(auth_url)

    print("\n👉 STEP 2: After granting permission, Google will redirect to localhost:8080 (which may say 'Site can't be reached').")
    print("Copy the FULL redirect URL from your browser address bar (e.g. http://localhost:8080/?state=...&code=...) and paste it below:\n")

    redirect_response = input("Paste Full Redirect URL here: ").strip()

    if not redirect_response:
        print("ERROR: No URL provided.")
        return

    # Extract code and state
    parsed = urllib.parse.urlparse(redirect_response)
    query_params = urllib.parse.parse_qs(parsed.query)

    code = query_params.get("code", [None])[0]
    if not code:
        # User might have pasted just the code
        code = redirect_response

    # Exchange code for credentials
    flow.fetch_token(code=code)
    creds = flow.credentials

    TOKEN_OUTPUT_PATH.write_text(creds.to_json(), encoding="utf-8")
    print("\n" + "=" * 70, flush=True)
    print("✅ AUTHENTICATION SUCCESSFUL!", flush=True)
    print(f"Token saved to: {TOKEN_OUTPUT_PATH}", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()

