import webbrowser
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse
import os
import json

# === CONFIG ===
CLIENT_ID = os.getenv("SMARTCAR_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("SMARTCAR_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:8000/callback"
SCOPES = "read_vin read_vehicle_info read_location read_engine_oil read_battery read_charge read_fuel control_security read_odometer read_tires read_charge"
PORT = 8000

print(f"DEBUG: CLIENT_ID={CLIENT_ID}")
print(f"DEBUG: CLIENT_SECRET={'<hidden>' if CLIENT_SECRET else '<missing>'}")
print(f"DEBUG: REDIRECT_URI={REDIRECT_URI}")
print(f"DEBUG: SCOPES={SCOPES}")
print(f"DEBUG: PORT={PORT}")

auth_code = None


# === OAuth Redirect Handler ===
class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed.query)

        print("DEBUG: Redirected to path:", self.path)
        print("DEBUG: Parsed query:", query)

        if "code" in query:
            auth_code = query["code"][0]
            print("DEBUG: Authorization code received:", auth_code)
            message = b"You can close this window now. Auth successful."
        else:
            print("DEBUG: Authorization code not found in query.")
            message = b"Authorization failed or was cancelled."

        self.send_response(200)
        self.end_headers()
        self.wfile.write(message)


# === Start local server in a thread ===
def start_server():
    print(f"DEBUG: Starting local HTTP server on port {PORT}")
    server = HTTPServer(("localhost", PORT), CallbackHandler)
    print(f"Listening on http://localhost:{PORT}...")
    server.handle_request()


server_thread = threading.Thread(target=start_server)
server_thread.start()

# === Step 1: Start OAuth flow ===
params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": SCOPES,
    "mode": "live",
}
auth_url = "https://connect.smartcar.com/oauth/authorize?" + urlparse.urlencode(params)
print("DEBUG: Generated auth URL:")
print(auth_url)

print("Opening browser for authentication...")
webbrowser.open(auth_url)

# Wait for the server to get the code
server_thread.join()

if not auth_code:
    print("ERROR: Failed to get authorization code.")
    exit(1)

# === Step 2: Exchange code for access token ===
token_url = "https://auth.smartcar.com/oauth/token"
token_data = {
    "grant_type": "authorization_code",
    "code": auth_code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
}
print("DEBUG: Sending token exchange request with payload:")
print(token_data)

token_resp = requests.post(token_url, data=token_data)
print("DEBUG: Token response status:", token_resp.status_code)
print("DEBUG: Token response body:", token_resp.text)

token_resp.raise_for_status()
access_token = token_resp.json()["access_token"]
print("DEBUG: Access token acquired:", access_token)

# === Step 3: Get vehicle IDs ===
headers = {"Authorization": f"Bearer {access_token}"}
print("DEBUG: Sending request to get vehicle IDs")
vehicle_ids_resp = requests.get(
    "https://api.smartcar.com/v2.0/vehicles", headers=headers
)
print("DEBUG: Vehicle ID response status:", vehicle_ids_resp.status_code)
print("DEBUG: Vehicle ID response body:", vehicle_ids_resp.text)

# Uncomment if you want to use a live vehicle ID:
vehicle_ids_resp.raise_for_status()
vehicle_id = vehicle_ids_resp.json()["vehicles"][0]

# vehicle_id = "d6797263-79e2-4e03-80bc-c29905b4504a"
print(f"DEBUG: Using vehicle ID: {vehicle_id}")

# === Step 4: Get battery info ===
print(f"DEBUG: Requesting battery info for vehicle {vehicle_id}")
battery_resp = requests.get(
    f"https://api.smartcar.com/v2.0/vehicles/{vehicle_id}/battery",
    headers=headers,
)
print("DEBUG: Battery response status:", battery_resp.status_code)
print("DEBUG: Battery response body:", battery_resp.text)

battery_resp.raise_for_status()
battery = battery_resp.json()

print(f"Battery percent remaining: {battery['percentRemaining'] * 100:.1f}%")
