import logging
from typing import Dict, Any

import requests

from exceptions import VehicleError
from notification_service import NotificationService
from charging_controller import ChargingController, BATTERY_THRESHOLD
from token_manager import SmartcarTokenManager


class SmartcarClient:
    """Client for interacting with Smartcar API."""

    def __init__(self, token_manager: SmartcarTokenManager) -> None:
        self.token_manager = token_manager

    def _get_headers(self) -> Dict[str, str]:
        access_token = self.token_manager.get_access_token()
        return {"Authorization": f"Bearer {access_token}"}

    def get_vehicle_info(self) -> str:
        headers = self._get_headers()
        logging.info("Sending request to get vehicle IDs")
        try:
            vehicle_ids_resp = requests.get(
                "https://api.smartcar.com/v2.0/vehicles", headers=headers, timeout=30
            )
            logging.debug("Vehicle ID response status: %s", vehicle_ids_resp.status_code)
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
        charging_controller: ChargingController,
        notification_service: NotificationService,
    ) -> None:
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
            logging.info(
                f"Battery percent remaining: {battery_percentage:.1f}%"
            )
            notification_service.send_discord_notification(
                message=f"Battery percent remaining: {battery_percentage:.1f}%"
            )
            if battery["percentRemaining"] >= BATTERY_THRESHOLD:
                charging_controller.stop_charging(skip_check=True)
        except (KeyError, ValueError) as e:
            logging.error(f"Invalid battery response: {e}")
            raise VehicleError(f"Invalid battery response: {e}")
