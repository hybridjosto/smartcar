#!/usr/bin/env python3

import time
import os
import json
import webbrowser
import threading
import requests
from requests.auth import HTTPDigestAuth
import urllib.parse as urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging


# Smartcar settings
CLIENT_ID = os.getenv("SMARTCAR_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SMARTCAR_CLIENT_SECRET", "")
VEHICLE_ID = os.getenv("SMARTCAR_VEHICLE_ID", "")
TOKEN_FILE = "tokens.json"
TOKEN_URL = "https://auth.smartcar.com/oauth/token"
AUTH_URL = "https://connect.smartcar.com/oauth/authorize"
REDIRECT_URI = "http://localhost:8000/callback"
PORT = 8000
SCOPES = "read_vin read_vehicle_info read_location read_engine_oil read_battery read_charge read_fuel control_security read_odometer read_tires read_charge"

access_token = ""
headers = {"Authorization": "Bearer"}

# Zappi Settings
MYENERGI_SERIAL = os.getenv("MYENERGI_SERIAL", "")
MYENERGI_KEY = os.getenv("MYENERGI_KEY", "")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("smart.log"),
        logging.StreamHandler(),  # optional: still logs to console
    ],
)


class SmartcarTokenManager:
    def __init__(self, client_id, client_secret, token_file=TOKEN_FILE):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self.tokens = self._load_tokens()

    def _load_tokens(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, "r") as f:
                logging.debug(f"Loaded tokens from {self.token_file}")
                return json.load(f)
        return {}

    def _save_tokens(self):
        with open(self.token_file, "w") as f:
            json.dump(self.tokens, f)
            logging.debug(f"Tokens saved to {self.token_file}")

    def has_tokens(self):
        return "refresh_token" in self.tokens

    def _is_access_token_expired(self):
        expires_at = self.tokens.get("expires_at")
        if not expires_at:
            return True
        return time.time() >= expires_at - 60

    def get_access_token(self):
        if not self.has_tokens():
            logging.debug("No refresh token found. Starting full OAuth flow...")
            self._run_initial_auth_flow()
        elif self._is_access_token_expired():
            self._refresh_access_token()

        return self._refresh_access_token()

    def _refresh_access_token(self):
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.tokens["refresh_token"],
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        logging.debug("Refreshing access token...")
        response = requests.post(TOKEN_URL, data=data)
        logging.debug(
            "Refresh token response: %s %s", response.status_code, response.text
        )
        response.raise_for_status()

        token_data = response.json()
        self.tokens["access_token"] = token_data["access_token"]
        self.tokens["refresh_token"] = token_data["refresh_token"]
        self.tokens["expires_at"] = time.time() + token_data["expires_in"]
        self._save_tokens()

        return self.tokens["access_token"]

    def _run_initial_auth_flow(self):
        auth_code = self._get_authorization_code()
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": REDIRECT_URI,
        }

        logging.debug("Exchanging code for tokens...")
        response = requests.post(TOKEN_URL, data=token_data)
        logging.debug("Token exchange response:", response.status_code, response.text)
        response.raise_for_status()

        token_json = response.json()
        self.tokens = {
            "access_token": token_json["access_token"],
            "refresh_token": token_json["refresh_token"],
            "expires_at": time.time() + token_json["expires_in"],
        }
        self._save_tokens()

    def _get_authorization_code(self):
        auth_code_holder = {}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse.urlparse(self.path)
                query = urlparse.parse_qs(parsed.query)
                logging.debug("OAuth redirect received:", self.path)
                if "code" in query:
                    auth_code_holder["code"] = query["code"][0]
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Auth complete. You can close this tab.")
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Authorization failed.")

        def start_server():
            server = HTTPServer(("localhost", PORT), CallbackHandler)
            logging.debug(f"Listening on http://localhost:{PORT}...")
            server.handle_request()

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
        logging.debug("Opening browser for authentication...")
        webbrowser.open(full_auth_url)

        server_thread.join()

        if "code" not in auth_code_holder:
            raise RuntimeError("Failed to receive authorization code.")

        return auth_code_holder["code"]


def get_vehicle_info():
    headers = {"Authorization": f"Bearer {access_token}"}
    logging.debug("Sending request to get vehicle IDs")
    vehicle_ids_resp = requests.get(
        "https://api.smartcar.com/v2.0/vehicles", headers=headers
    )
    logging.debug("Vehicle ID response status:", vehicle_ids_resp.status_code)
    logging.debug("Vehicle ID response body:", vehicle_ids_resp.text)

    # Uncomment if you want to use a live vehicle ID:
    vehicle_ids_resp.raise_for_status()
    vehicle_id = vehicle_ids_resp.json()["vehicles"][0]
    return vehicle_id


def check_battery_level(vehicle_id):
    # === Step 4: Get battery info ===
    logging.debug(f"Requesting battery info for vehicle {vehicle_id}")
    battery_resp = requests.get(
        f"https://api.smartcar.com/v2.0/vehicles/{vehicle_id}/battery",
        headers=headers,
    )
    logging.debug("Battery response status: %s", battery_resp.status_code)
    logging.debug("Battery response body: %s", battery_resp.text)

    battery_resp.raise_for_status()
    battery = battery_resp.json()

    logging.debug(
        f"Battery percent remaining: {battery['percentRemaining'] * 100:.1f}%"
    )
    if battery["percentRemaining"] >= 0.8:
        stop_charging()


def zappi_request(url):

    base_url = "https://s18.myenergi.net"
    final_url = base_url + url
    response = requests.get(
        final_url, auth=HTTPDigestAuth(MYENERGI_SERIAL, MYENERGI_KEY)
    )
    return response


def is_charging():
    logging.debug("Checking if charging...")
    url = f"/cgi-jstatus-Z{MYENERGI_SERIAL}"
    response = zappi_request(url)
    status_json = response.json()
    zappi_mode = status_json['zappi'][0].get("zmo", "")
    charging = status_json['zappi'][0].get("sta", "")
    # Status  1=Paused 3=Diverting/Charging 5=Complete
    logging.debug(status_json)
    logging.debug(f"mode ={zappi_mode}, status={charging}")
    return zappi_mode != "4" and charging == "3"


def stop_charging():
    # === Step 5: stop charging ===
    if is_charging():
        logging.debug("Stopping charging...")
        # Add your logic to stop charging here
        # "stop" mode string
        stop_mode = "4-0-0-0000"

        # Construct the URL for setting mode
        url = f"/cgi-zappi-mode-Z{MYENERGI_SERIAL}-{stop_mode}"

        # Make the request
        response = zappi_request(url)
        response.raise_for_status()
        logging.debug("Charging stopped successfully. %s", response.text)
    pass


# === Example usage ===
if __name__ == "__main__":

    if not CLIENT_ID or not CLIENT_SECRET:
        logging.error("Client ID or Secret not set in environment variables.")
        exit(1)

    if not MYENERGI_SERIAL or not MYENERGI_KEY:
        logging.error("Zappi ID or Secret not set in environment variables.")
        exit(1)

    if not is_charging():
        logging.info("Not Charging")
        exit(1)

    token_manager = SmartcarTokenManager(CLIENT_ID, CLIENT_SECRET)

    vehicle = VEHICLE_ID
    try:
        access_token = token_manager.get_access_token()
        logging.debug("Access token: %s", access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        check_battery_level(vehicle)
    except Exception as e:
        logging.error(str(e))
