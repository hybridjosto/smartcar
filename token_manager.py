import json
import logging
import os
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any
import urllib.parse as urlparse

import requests

from exceptions import TokenError

TOKEN_FILE = "tokens.json"
TOKEN_URL = "https://auth.smartcar.com/oauth/token"
AUTH_URL = "https://connect.smartcar.com/oauth/authorize"
REDIRECT_URI = "http://localhost:8000/callback"
PORT = 8000
SCOPES = (
    "read_vin read_vehicle_info read_location read_engine_oil read_battery "
    "read_charge read_fuel control_security read_odometer read_tires read_charge"
)
TOKEN_BUFFER_SECONDS = 60


class SmartcarTokenManager:
    """Manages Smartcar OAuth tokens with automatic refresh."""

    def __init__(self, client_id: str, client_secret: str, token_file: str = TOKEN_FILE) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self.tokens = self._load_tokens()

    def _load_tokens(self) -> Dict[str, Any]:
        if os.path.exists(self.token_file):
            try:
                with open(self.token_file, "r") as f:
                    logging.info(f"Loaded tokens from {self.token_file}")
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logging.error(f"Failed to load tokens: {e}")
                raise TokenError(f"Failed to load tokens from {self.token_file}: {e}")
        return {}

    def _save_tokens(self) -> None:
        try:
            with open(self.token_file, "w") as f:
                json.dump(self.tokens, f)
                logging.info(f"Tokens saved to {self.token_file}")
        except IOError as e:
            logging.error(f"Failed to save tokens: {e}")
            raise TokenError(f"Failed to save tokens to {self.token_file}: {e}")

    def has_tokens(self) -> bool:
        return "refresh_token" in self.tokens

    def _is_access_token_expired(self) -> bool:
        expires_at = self.tokens.get("expires_at")
        if not expires_at:
            return True
        return time.time() >= expires_at - TOKEN_BUFFER_SECONDS

    def get_access_token(self) -> str:
        if not self.has_tokens():
            logging.info("No refresh token found. Starting full OAuth flow...")
            self._run_initial_auth_flow()
        elif self._is_access_token_expired():
            return self._refresh_access_token()
        return self.tokens["access_token"]

    def _refresh_access_token(self) -> str:
        if "refresh_token" not in self.tokens:
            raise TokenError("No refresh token available")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.tokens["refresh_token"],
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        logging.info("Refreshing access token...")
        try:
            response = requests.post(TOKEN_URL, data=data, timeout=30)
            logging.debug("Refresh token response: %s %s", response.status_code, response.text)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"Failed to refresh token: {e}")
            raise TokenError(f"Failed to refresh access token: {e}")

        try:
            token_data = response.json()
            self.tokens["access_token"] = token_data["access_token"]
            self.tokens["refresh_token"] = token_data["refresh_token"]
            self.tokens["expires_at"] = time.time() + token_data["expires_in"]
            self._save_tokens()
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid token response: {e}")
            raise TokenError(f"Invalid token response: {e}")

        return self.tokens["access_token"]

    def _run_initial_auth_flow(self) -> None:
        auth_code = self._get_authorization_code()
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": REDIRECT_URI,
        }

        logging.info("Exchanging code for tokens...")
        try:
            response = requests.post(TOKEN_URL, data=token_data, timeout=30)
            logging.debug("Token exchange response: %s %s", response.status_code, response.text)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"Failed to exchange code for tokens: {e}")
            raise TokenError(f"Failed to exchange authorization code: {e}")

        try:
            token_json = response.json()
            self.tokens = {
                "access_token": token_json["access_token"],
                "refresh_token": token_json["refresh_token"],
                "expires_at": time.time() + token_json["expires_in"],
            }
            self._save_tokens()
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid token exchange response: {e}")
            raise TokenError(f"Invalid token exchange response: {e}")

    def _get_authorization_code(self) -> str:
        auth_code_holder: Dict[str, str] = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse.urlparse(self.path)
                query = urlparse.parse_qs(parsed.query)
                logging.debug("OAuth redirect received: %s", self.path)
                if "code" in query:
                    auth_code_holder["code"] = query["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Auth complete. You can close this tab.")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Authorization failed.")

            def log_message(self, format: str, *args: Any) -> None:
                pass

        def start_server() -> None:
            try:
                server = HTTPServer(("localhost", PORT), CallbackHandler)
                logging.debug(f"Listening on http://localhost:{PORT}...")
                server.handle_request()
            except OSError as e:
                logging.error(f"Failed to start callback server: {e}")
                raise TokenError(f"Failed to start callback server on port {PORT}: {e}")

        server_thread = threading.Thread(target=start_server)
        server_thread.start()

        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
            "mode": "live",
        }
        full_auth_url = AUTH_URL + "?" + urlparse.urlencode(params)
        logging.info("Opening browser for authentication...")
        try:
            webbrowser.open(full_auth_url)
        except Exception as e:
            logging.error(f"Failed to open browser: {e}")
            logging.info(f"Please manually visit: {full_auth_url}")

        server_thread.join(timeout=300)

        if server_thread.is_alive():
            logging.error("Authorization timeout")
            raise TokenError("Authorization flow timed out after 5 minutes")

        if "code" not in auth_code_holder:
            raise TokenError("Failed to receive authorization code")

        return auth_code_holder["code"]
