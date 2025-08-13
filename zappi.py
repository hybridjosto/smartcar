from charging_controller import ChargingController, ENERGY_THRESHOLD_KWH
from config import Config
from notification_service import NotificationService

try:
    config = Config.from_env()
except ValueError as e:
    logging.error(f"Configuration error: {e}")
    exit(1)

notification_service = NotificationService(config)
charging_controller = ChargingController(config, notification_service)


status = charging_controller.get_status()
charging = charging_controller.is_charging(status=status, notify=False)
if not charging:
    exit(1)
print(charging)
