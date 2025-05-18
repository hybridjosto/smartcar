import smart
import os
import logging

# App to connect to smartcar API, retrieve vehicle info and battery level,
#  optionally, if battery is >= 80% send a  STOP command to the myenergi chargepoint API.

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("smart.log"),
        # logging.StreamHandler(),  # optional: still logs to console
    ],
)
vehicle = "d6797263-79e2-4e03-80bc-c29905b4504a"
# === Example usage ===
if __name__ == "__main__":
    CLIENT_ID = os.getenv("SMARTCAR_CLIENT_ID", "")
    CLIENT_SECRET = os.getenv("SMARTCAR_CLIENT_SECRET", "")

    if not CLIENT_ID or not CLIENT_SECRET:
        logging.error("Client ID or Secret not set in environment variables.")
        exit(1)

    token_manager = smart.SmartcarTokenManager(CLIENT_ID, CLIENT_SECRET)

    try:
        access_token = token_manager.get_access_token()
        logging.debug("Access token:", access_token)
        headers = {"Authorization": f"Bearer {access_token}"}
        smart.check_battery_level(vehicle)
    except Exception as e:
        logging.error(str(e))
