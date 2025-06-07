import os
from dataclasses import dataclass
from typing import Optional


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
