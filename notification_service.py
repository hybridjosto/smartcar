import logging
from typing import Optional

import requests

from config import Config


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
            response = requests.post(self.config.discord_webhook_url, json=data, timeout=30)
            response.raise_for_status()
            logging.info("Discord notification sent successfully")
        except requests.RequestException as e:
            logging.error(f"Failed to send Discord notification: {e}")
