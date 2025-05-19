import os
import json
import time
import logging
import requests
from datetime import datetime, timezone

# Smartcar OAuth settings
CLIENT_ID = os.getenv("SMARTCAR_CLIENT_ID")
CLIENT_SECRET = os.getenv("SMARTCAR_CLIENT_SECRET")
TOKEN_URL = "https://auth.smartcar.com/oauth/token"
TOKEN_FILE = "tokens.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"{TOKEN_FILE} not found.")
    with open(TOKEN_FILE, "r") as f:
        logging.info(f"Loading tokens from {TOKEN_FILE}")
        return json.load(f)


def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    logging.info(f"Tokens saved to {TOKEN_FILE}")


def refresh_access_token(tokens):
    logging.info("Refreshing access token...")
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    print(data)

    response = requests.post(TOKEN_URL, data=data)
    logging.debug(f"Response status: {response.status_code}")
    logging.debug(f"Response body: {response.text}")
    response.raise_for_status()

    token_data = response.json()

    now = datetime.now(timezone.utc)
    expires_at_unix = time.time() + token_data["expires_in"]
    expires_at_dt = datetime.fromtimestamp(expires_at_unix, tz=timezone.utc)

    tokens["access_token"] = token_data["access_token"]
    tokens["refresh_token"] = token_data["refresh_token"]
    tokens["refreshed_at"] = now.isoformat()
    tokens["refreshed_at_unix"] = now.timestamp()
    tokens["expires_at"] = expires_at_dt.isoformat()
    tokens["expires_at_unix"] = expires_at_unix
    save_tokens(tokens)
    logging.info("Access token refreshed and saved.")

    # Print and log summary
    token_summary = {
        "refreshed_at": tokens["refreshed_at"],
        "expires_at": tokens["expires_at"],
        "refresh_token": tokens["refresh_token"],
        "access_token": tokens["access_token"],
        "refreshed_at_unix": tokens["refreshed_at_unix"],
        "expires_at_unix": tokens["expires_at_unix"],
    }

    logging.info("Token refresh summary:\n%s", json.dumps(token_summary, indent=2))
    print(json.dumps(token_summary, indent=2))

    return tokens["access_token"]


if __name__ == "__main__":
    if not CLIENT_ID or not CLIENT_SECRET:
        logging.error("SMARTCAR_CLIENT_ID or SMARTCAR_CLIENT_SECRET not set.")
        exit(1)

    try:
        tokens = load_tokens()
        refresh_access_token(tokens)
    except Exception as e:
        logging.error(f"Failed to refresh token: {e}")
        exit(1)
