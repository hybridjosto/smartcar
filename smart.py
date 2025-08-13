import logging

from charging_controller import ChargingController
from config import Config, load_energy_threshold
from exceptions import ChargingError, TokenError, VehicleError
from logging_utils import setup_logging
from notification_service import NotificationService
from smartcar_client import SmartcarClient
from token_manager import SmartcarTokenManager

__all__ = [
    "ChargingController",
    "NotificationService",
    "SmartcarTokenManager",
    "SmartcarClient",
    "Config",
    "ENERGY_THRESHOLD_KWH",
    "ChargingError",
    "TokenError",
    "VehicleError",
    "main",
]

setup_logging()


def main() -> None:
    try:
        config = Config.from_env()
    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        exit(1)

    notification_service = NotificationService(config)
    charging_controller = ChargingController(config, notification_service)

    try:
        status = charging_controller.get_status()
        if not charging_controller.is_charging(status=status, notify=False):
            logging.info("Not currently charging")
            exit(1)
        else:

            logging.info("charging")
            try:
                charging_controller.check_energy_delivered(status=status)
            except ChargingError as e:
                logging.error(f"Failed to check delivered energy: {e}")

            try:
                if config.check_battery:
                    token_manager = SmartcarTokenManager(
                        config.smartcar_client_id, config.smartcar_client_secret
                    )
                    smartcar_client = SmartcarClient(token_manager)

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


    except ChargingError as e:
        logging.error(f"Failed to check charging status: {e}")
        exit(1)

if __name__ == "__main__":
    main()
