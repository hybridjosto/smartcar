import os
import json
import logging
import requests
from requests.auth import HTTPDigestAuth

TOKEN_FILE = "tokens.json"
VEHICLE_ID = os.getenv("VEHICLE_ID", "")
MYENERGI_SERIAL = os.getenv("MYENERGI_SERIAL", "")
MYENERGI_KEY = os.getenv("MYENERGI_KEY", "")

logging.basicConfig(level=logging.INFO)


def load_access_token():
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)["access_token"]


def zappi_request(url):
    base_url = "https://s18.myenergi.net"
    full_url = base_url + url
    return requests.get(full_url, auth=HTTPDigestAuth(MYENERGI_SERIAL, MYENERGI_KEY))


def is_charging():
    logging.info("Checking if charging...")
    url = f"/cgi-jstatus-Z{MYENERGI_SERIAL}"
    response = zappi_request(url)
    response.raise_for_status()
    data = response.json()
    return data.get("zmo") != "4" and data.get("sta") == "3"


def stop_charging():
    if is_charging():
        logging.info("Stopping charging...")
        stop_mode = "4-0-0-0000"
        url = f"/cgi-zappi-mode-Z{MYENERGI_SERIAL}-{stop_mode}"
        response = zappi_request(url)
        response.raise_for_status()
        logging.info("Charging stopped successfully.")


def check_battery_level(vehicle_id, token):
    headers = {"Authorization": f"Bearer {token}"}
    logging.info(f"Checking battery for vehicle {vehicle_id}")
    response = requests.get(
        f"https://api.smartcar.com/v2.0/vehicles/{vehicle_id}/battery", headers=headers
    )
    response.raise_for_status()
    battery = response.json()
    percent = battery["percentRemaining"] * 100
    logging.info(f"Battery level: {percent:.1f}%")
    if battery["percentRemaining"] >= 0.8:
        stop_charging()


if __name__ == "__main__":
    if not MYENERGI_SERIAL or not MYENERGI_KEY:
        logging.error("Missing MyEnergi serial or key.")
        exit(1)
    try:
        token = load_access_token()
        check_battery_level(VEHICLE_ID, token)
    except Exception as e:
        logging.error(f"Error during execution: {e}")
