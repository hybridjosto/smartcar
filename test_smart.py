import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Provide a minimal stub for the requests module so smart.py can be imported
requests_module = types.ModuleType("requests")
requests_module.get = MagicMock()
requests_module.post = MagicMock()
requests_module.Response = MagicMock

auth_submodule = types.ModuleType("requests.auth")
auth_submodule.HTTPDigestAuth = MagicMock()
requests_module.auth = auth_submodule
sys.modules.setdefault("requests", requests_module)
sys.modules.setdefault("requests.auth", auth_submodule)

from smart import (
    ChargingController,
    NotificationService,
    Config,
)


class TestEnergyCheck(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            smartcar_client_id="id",
            smartcar_client_secret="secret",
            smartcar_vehicle_id="veh",
            myenergi_serial="ser",
            myenergi_key="key",
            energy_threshold_kwh=25.0,
        )
        self.notifier = NotificationService(self.config)
        self.controller = ChargingController(self.config, self.notifier)

    @patch.object(ChargingController, "_zappi_request")
    def test_check_energy_delivered_triggers_stop(self, mock_req):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"zappi": [{"che": self.config.energy_threshold_kwh + 1}]}
        mock_req.return_value = resp

        with patch.object(self.controller, "stop_charging") as mock_stop, patch.object(
            self.notifier, "send_discord_notification"
        ) as mock_notify:
            self.controller.check_energy_delivered()
            mock_stop.assert_called_once()
            mock_notify.assert_called_once()

    def test_is_charging_notifies_only_when_charging(self):
        charging_status = {"zappi": [{"zmo": "1", "sta": "3", "che": "1"}]}
        idle_status = {"zappi": [{"zmo": "4", "sta": "1", "che": "1"}]}

        with patch.object(self.notifier, "send_discord_notification") as mock_notify:
            assert self.controller.is_charging(status=charging_status)
            mock_notify.assert_called_once()

        with patch.object(self.notifier, "send_discord_notification") as mock_notify:
            assert not self.controller.is_charging(status=idle_status)
            mock_notify.assert_not_called()

    @patch("smart.SmartcarClient")
    @patch("smart.SmartcarTokenManager")
    @patch("smart.ChargingController")
    @patch("smart.NotificationService")
    def test_main_exits_early_when_not_charging(
        self,
        mock_notification_cls,
        mock_charging_cls,
        mock_token_cls,
        mock_client_cls,
    ):
        from smart import main

        mock_charging = mock_charging_cls.return_value
        mock_charging.is_charging.return_value = False

        config = Config(
            smartcar_client_id="id",
            smartcar_client_secret="secret",
            smartcar_vehicle_id="veh",
            myenergi_serial="ser",
            myenergi_key="key",
            check_battery=True,
            energy_threshold_kwh=25.0,
        )

        with patch.object(Config, "from_env", return_value=config):
            with self.assertRaises(SystemExit):
                main()

        mock_charging.check_energy_delivered.assert_not_called()
        mock_client_cls.assert_not_called()
        mock_token_cls.assert_not_called()
        mock_client_cls.return_value.check_battery_level.assert_not_called()


if __name__ == "__main__":
    unittest.main()
