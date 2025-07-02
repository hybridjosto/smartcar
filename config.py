import json
import os
from dataclasses import dataclass
from typing import Optional


def load_energy_threshold(file_path: str = "battery.json") -> float:
    """Load the energy threshold from a JSON file."""
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            return float(data.get("kwh_needed", 25.0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
        # Default to 25.0 if the file is not found, invalid, or the value is not a number
        print(f"Error loading battery config, defaulting to 25.0 kWh: {e}")
        return 25.0


@dataclass
class Config:
    """Configuration class for environment variables."""

    smartcar_client_id: str
    smartcar_client_secret: str
    smartcar_vehicle_id: str
    myenergi_serial: str
    myenergi_key: str
    energy_threshold_kwh: float
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
        config_data["energy_threshold_kwh"] = load_energy_threshold()
        return cls(**config_data)
