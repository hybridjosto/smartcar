#!/usr/bin/env python3

import json
import logging
import os
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Optional, Any
import urllib.parse as urlparse

import requests
from requests.auth import HTTPDigestAuth


# Constants
TOKEN_FILE = "tokens.json"
TOKEN_URL = "https://auth.smartcar.com/oauth/token"
AUTH_URL = "https://connect.smartcar.com/oauth/authorize"
REDIRECT_URI = "http://localhost:8000/callback"
PORT = 8000
SCOPES = "read_vin read_vehicle_info read_location read_engine_oil read_battery read_charge read_fuel control_security read_odometer read_tires read_charge"
MYENERGI_BASE_URL = "https://s18.myenergi.net"
BATTERY_THRESHOLD = 0.8
TOKEN_BUFFER_SECONDS = 60
ZAPPI_CHARGING_STATUS = "3"
ZAPPI_STOP_MODE = "4"
ZAPPI_STOP_MODE_STRING = "4-0-0-0000"


class SmartcarError(Exception):
    """Base exception for Smartcar operations."""

    pass


class TokenError(SmartcarError):
    """Exception raised for token-related errors."""

    pass


class VehicleError(SmartcarError):
    """Exception raised for vehicle-related errors."""

    pass


class ChargingError(SmartcarError):
    """Exception raised for charging-related errors."""

    pass


@dataclass
class Config:
    """Configuration class for environment variables."""

    smartcar_client_id: str
    smartcar_client_secret: str
    smartcar_vehicle_id: str
    myenergi_serial: str
    myenergi_key: str
    discord_webhook_url: Optional[str] = None
    # Default to False so the application does not check the battery
    # percentage unless explicitly enabled by the environment variable.
    check_battery: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        required_vars = {
            "smartcar_client_id": "SMARTCAR_CLIENT_ID",
            "smartcar_client_secret": "SMARTCAR_CLIENT_SECRET",
            "smartcar_vehicle_id": "SMARTCAR_VEHICLE_ID",
            "myenergi_serial": "MYENERGI_SERIAL",
            "myenergi_key": "MYENERGI_KEY",
        }

        config_data = {}
        for key, env_var in required_vars.items():
            value = os.getenv(env_var)
            if not value:
                raise ValueError(f"Required environment variable {env_var} not set")
            config_data[key] = value

        config_data["discord_webhook_url"] = os.getenv("DISCORD_WEBHOOK_URL")
        # CHECK_BATTERY defaults to False until argument support is added.
        check_battery_env = os.getenv("CHECK_BATTERY", "False")
        config_data["check_battery"] = check_battery_env.lower() == "true"
        return cls(**config_data)


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler("smart.log"),
            logging.StreamHandler(),
        ],
    )


setup_logging()


class NotificationService:
    """Service for sending notifications."""

    def __init__(self, config: Config) -> None:
        """Initialize notification service.

        Args:
            config: Configuration containing webhook URL
        """
        self.config = config

    def send_discord_notification(self, message: str) -> None:
        """Send notification to Discord webhook.

        Args:
            message: Message to send
        """
        if not self.config.discord_webhook_url:
            logging.warning("Discord webhook URL not configured, skipping notification")
            return

        data = {
            "content": message,
            "username": "Smartcar Bot",
            "avatar_url": "https://example.com/avatar.png",
        }

        try:
            response = requests.post(
                self.config.discord_webhook_url, json=data, timeout=30
            )
            response.raise_for_status()
            logging.info("Discord notification sent successfully")
        except requests.RequestException as e:
            logging.error(f"Failed to send Discord notification: {e}")


class SmartcarTokenManager:
    """Manages Smartcar OAuth tokens with automatic refresh."""

    def __init__(
        self, client_id: str, client_secret: str, token_file: str = TOKEN_FILE
    ) -> None:
        """Initialize token manager.

        Args:
            client_id: Smartcar client ID
            client_secret: Smartcar client secret
            token_file: Path to token storage file
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self.tokens = self._load_tokens()

    def _load_tokens(self) -> Dict[str, Any]:
        """Load tokens from file if it exists."""
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
        """Save tokens to file."""
        try:
            with open(self.token_file, "w") as f:
                json.dump(self.tokens, f)
                logging.info(f"Tokens saved to {self.token_file}")
        except IOError as e:
            logging.error(f"Failed to save tokens: {e}")
            raise TokenError(f"Failed to save tokens to {self.token_file}: {e}")

    def has_tokens(self) -> bool:
        """Check if refresh token exists."""
        return "refresh_token" in self.tokens

    def _is_access_token_expired(self) -> bool:
        """Check if access token is expired or will expire soon."""
        expires_at = self.tokens.get("expires_at")
        if not expires_at:
            return True
        return time.time() >= expires_at - TOKEN_BUFFER_SECONDS

    def get_access_token(self) -> str:
        """Get valid access token, refreshing if necessary."""
        if not self.has_tokens():
            logging.info("No refresh token found. Starting full OAuth flow...")
            self._run_initial_auth_flow()
        elif self._is_access_token_expired():
            return self._refresh_access_token()

        return self.tokens["access_token"]

    def _refresh_access_token(self) -> str:
        """Refresh access token using refresh token."""
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
            logging.debug(
                "Refresh token response: %s %s", response.status_code, response.text
            )
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
        """Run complete OAuth flow to get initial tokens."""
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
            logging.debug(
                "Token exchange response: %s %s", response.status_code, response.text
            )
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
        """Get authorization code via OAuth flow."""
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
                """Suppress default HTTP server logs."""
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

        server_thread.join(timeout=300)  # 5 minute timeout

        if server_thread.is_alive():
            logging.error("Authorization timeout")
            raise TokenError("Authorization flow timed out after 5 minutes")

        if "code" not in auth_code_holder:
            raise TokenError("Failed to receive authorization code")

        return auth_code_holder["code"]


class SmartcarClient:
    """Client for interacting with Smartcar API."""

    def __init__(self, token_manager: SmartcarTokenManager) -> None:
        """Initialize Smartcar client.

        Args:
            token_manager: Token manager for authentication
        """
        self.token_manager = token_manager

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers with current access token."""
        access_token = self.token_manager.get_access_token()
        return {"Authorization": f"Bearer {access_token}"}

    def get_vehicle_info(self) -> str:
        """Get first vehicle ID from user's vehicles.

        Returns:
            Vehicle ID string

        Raises:
            VehicleError: If unable to retrieve vehicle information
        """
        headers = self._get_headers()
        logging.info("Sending request to get vehicle IDs")

        try:
            vehicle_ids_resp = requests.get(
                "https://api.smartcar.com/v2.0/vehicles", headers=headers, timeout=30
            )
            logging.debug(
                "Vehicle ID response status: %s", vehicle_ids_resp.status_code
            )
            logging.debug("Vehicle ID response body: %s", vehicle_ids_resp.text)
            vehicle_ids_resp.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"Failed to get vehicle IDs: {e}")
            raise VehicleError(f"Failed to retrieve vehicle IDs: {e}")

        try:
            vehicles_data = vehicle_ids_resp.json()
            if not vehicles_data.get("vehicles"):
                raise VehicleError("No vehicles found in account")
            return vehicles_data["vehicles"][0]
        except (KeyError, IndexError, ValueError) as e:
            logging.error(f"Invalid vehicle response: {e}")
            raise VehicleError(f"Invalid vehicle response: {e}")

    def check_battery_level(
        self,
        vehicle_id: str,
        charging_controller: "ChargingController",
        notification_service: "NotificationService",
    ) -> None:
        """Check battery level and stop charging if above threshold.

        Args:
            vehicle_id: ID of vehicle to check
            charging_controller: Controller for managing charging

        Raises:
            VehicleError: If unable to retrieve battery information
        """
        headers = self._get_headers()
        logging.debug(f"Requesting battery info for vehicle {vehicle_id}")

        try:
            battery_resp = requests.get(
                f"https://api.smartcar.com/v2.0/vehicles/{vehicle_id}/battery",
                headers=headers,
                timeout=30,
            )
            logging.debug("Battery response status: %s", battery_resp.status_code)
            logging.debug("Battery response body: %s", battery_resp.text)
            battery_resp.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"Failed to get battery info: {e}")
            raise VehicleError(f"Failed to retrieve battery information: {e}")

        try:
            battery = battery_resp.json()
            battery_percentage = battery["percentRemaining"] * 100
            logging.info(f"Battery percent remaining: {battery_percentage:.1f}%")
            notification_service.send_discord_notification(
                message=f"Battery percent remaining: {battery_percentage:.1f}%"
            )
            if battery["percentRemaining"] >= BATTERY_THRESHOLD:
                charging_controller.stop_charging()
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid battery response: {e}")
            raise VehicleError(f"Invalid battery response: {e}")


class ChargingController:
    """Controller for managing Zappi charging operations."""

    def __init__(self, config: Config, notifier: NotificationService) -> None:
        """Initialize charging controller.

        Args:
            config: Configuration containing MyEnergi credentials
        """
        self.config = config
        self.notifier = notifier

    def _zappi_request(self, url: str) -> requests.Response:
        """Make authenticated request to MyEnergi API.

        Args:
            url: API endpoint path

        Returns:
            Response object

        Raises:
            ChargingError: If request fails
        """
        final_url = MYENERGI_BASE_URL + url
        try:
            response = requests.get(
                final_url,
                auth=HTTPDigestAuth(
                    self.config.myenergi_serial, self.config.myenergi_key
                ),
                timeout=30,
            )
            return response
        except requests.RequestException as e:
            logging.error(f"Zappi request failed: {e}")
            raise ChargingError(f"Failed to communicate with Zappi: {e}")

    def is_charging(self) -> bool:
        """Check if Zappi is currently charging.

        Returns:
            True if charging, False otherwise

        Raises:
            ChargingError: If unable to get charging status
        """
        logging.info("Checking if charging...")
        url = f"/cgi-jstatus-Z{self.config.myenergi_serial}"

        try:
            response = self._zappi_request(url)
            response.raise_for_status()
            status_json = response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Failed to get charging status: {e}")
            raise ChargingError(f"Failed to get charging status: {e}")

        try:
            zappi_data = status_json["zappi"][0]
            zappi_mode = zappi_data.get("zmo", "")
            charging_status = zappi_data.get("sta", "")
            charge_amount = zappi_data.get("che", "")
            # Status  1=Paused 3=Diverting/Charging 5=Complete
            logging.debug("Zappi status: %s", json.dumps(status_json, indent=2))
            logging.debug(f"mode={zappi_mode}, status={charging_status}")
            self.notifier.send_discord_notification(f"{charge_amount}")
            return (
                zappi_mode
                != ZAPPI_STOP_MODE
                # and charging_status == ZAPPI_CHARGING_STATUS
            )
        except (KeyError, IndexError) as e:
            logging.error(f"Invalid zappi response format: {e}")
            raise ChargingError(f"Invalid zappi response format: {e}")

    def stop_charging(self) -> None:
        """Stop charging if currently charging.

        Raises:
            ChargingError: If unable to stop charging
        """
        if not self.is_charging():
            logging.info("Not currently charging, no action needed")
            return

        logging.info("Stopping charging...")

        url = f"/cgi-zappi-mode-Z{self.config.myenergi_serial}-{ZAPPI_STOP_MODE_STRING}"

        try:
            response = self._zappi_request(url)
            response.raise_for_status()
            logging.info("Charging stopped successfully. %s", response.text)
        except requests.RequestException as e:
            logging.error(f"Failed to stop charging: {e}")
            raise ChargingError(f"Failed to stop charging: {e}")


def main() -> None:
    """Main application entry point."""
    try:
        config = Config.from_env()
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        exit(1)

    # Initialize services
    notification_service = NotificationService(config)
    charging_controller = ChargingController(config, notification_service)

    # Check if currently charging
    try:
        if not charging_controller.is_charging():
            logging.info("Not currently charging")
            notification_service.send_discord_notification("Not charging")
            return
    except ChargingError as e:
        logging.error(f"Failed to check charging status: {e}")
        exit(1)

    # Initialize Smartcar services
    token_manager = SmartcarTokenManager(
        config.smartcar_client_id, config.smartcar_client_secret
    )
    smartcar_client = SmartcarClient(token_manager)

    try:
        if config.check_battery:
            vehicle_id = config.smartcar_vehicle_id
            smartcar_client.check_battery_level(
                vehicle_id, charging_controller, notification_service
            )
        else:
            logging.info("Battery check disabled; skipping battery level call")
    except (TokenError, VehicleError, ChargingError) as e:
        logging.error(f"Application error: {e}")
        exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
