import json
import logging
from typing import Optional, Dict, Any

import requests
from requests.auth import HTTPDigestAuth

from config import Config
from exceptions import ChargingError
from notification_service import NotificationService

MYENERGI_BASE_URL = "https://s18.myenergi.net"
BATTERY_THRESHOLD = 0.8
ZAPPI_CHARGING_STATUS = "3"
ZAPPI_STOP_MODE = "4"
ZAPPI_STOP_MODE_STRING = "4-0-0-0000"
ENERGY_THRESHOLD_KWH = 28.5


class ChargingController:
    """Controller for managing Zappi charging operations."""

    def __init__(self, config: Config, notifier: NotificationService) -> None:
        self.config = config
        self.notifier = notifier
        self._auth = HTTPDigestAuth(self.config.myenergi_serial, self.config.myenergi_key)

    def _zappi_request(self, url: str) -> requests.Response:
        final_url = MYENERGI_BASE_URL + url
        try:
            response = requests.get(final_url, auth=self._auth, timeout=30)
            return response
        except requests.RequestException as e:
            logging.error(f"Zappi request failed: {e}")
            raise ChargingError(f"Failed to communicate with Zappi: {e}")

    def get_status(self) -> Dict[str, Any]:
        url = f"/cgi-jstatus-Z{self.config.myenergi_serial}"
        try:
            response = self._zappi_request(url)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            logging.error(f"Failed to get charging status: {e}")
            raise ChargingError(f"Failed to get charging status: {e}")

    def is_charging(self, status: Optional[Dict[str, Any]] = None, notify: bool = True) -> bool:
        logging.info("Checking if charging...")
        if status is None:
            status = self.get_status()
        status_json = status
        try:
            zappi_data = status_json["zappi"][0]
            zappi_mode = zappi_data.get("zmo", "")
            charging_status = zappi_data.get("sta", "")
            charge_amount = zappi_data.get("che", "")
            logging.debug("Zappi status: %s", json.dumps(status_json, indent=2))
            zappi_status = f"mode={zappi_mode}, status={charging_status}"
            logging.debug(zappi_status)
            if notify:
                self.notifier.send_discord_notification(f"{zappi_status}, {charge_amount}")
            return zappi_mode != ZAPPI_STOP_MODE
        except (KeyError, IndexError) as e:
            logging.error(f"Invalid zappi response format: {e}")
            raise ChargingError(f"Invalid zappi response format: {e}")

    def stop_charging(self, skip_check: bool = False) -> None:
        if not skip_check and not self.is_charging():
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

    def check_energy_delivered(self, status: Optional[Dict[str, Any]] = None) -> None:
        logging.info("Checking delivered energy...")
        if status is None:
            status = self.get_status()
        try:
            zappi_data = status["zappi"][0]
            charge_amount = float(zappi_data.get("che", 0))
        except (ValueError, KeyError, IndexError) as e:
            logging.error(f"Failed to get delivered energy: {e}")
            raise ChargingError(f"Failed to get delivered energy: {e}")

        logging.debug(f"Delivered energy: {charge_amount} kWh")

        if charge_amount >= ENERGY_THRESHOLD_KWH:
            message = (
                f"Energy delivered {charge_amount} kWh reached threshold {ENERGY_THRESHOLD_KWH} kWh. Stopping charge."
            )
            self.notifier.send_discord_notification(message)
            self.stop_charging(skip_check=True)
