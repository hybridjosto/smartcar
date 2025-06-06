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
    ENERGY_THRESHOLD_KWH,
)

class TestEnergyCheck(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            smartcar_client_id="id",
            smartcar_client_secret="secret",
            smartcar_vehicle_id="veh",
            myenergi_serial="ser",
            myenergi_key="key",
        )
        self.notifier = NotificationService(self.config)
        self.controller = ChargingController(self.config, self.notifier)

    @patch.object(ChargingController, "_zappi_request")
    def test_check_energy_delivered_triggers_stop(self, mock_req):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"zappi": [{"che": ENERGY_THRESHOLD_KWH + 1}]}
        mock_req.return_value = resp

        with patch.object(self.controller, "stop_charging") as mock_stop, patch.object(
            self.notifier, "send_discord_notification"
        ) as mock_notify:
            self.controller.check_energy_delivered()
            mock_stop.assert_called_once()
            mock_notify.assert_called_once()

    @patch.object(ChargingController, "_zappi_request")
    def test_is_charging_notify_false_suppresses_notification(self, mock_req):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"zappi": [{"zmo": "1", "sta": "1", "che": "1"}]}
        mock_req.return_value = resp

        with patch.object(self.notifier, "send_discord_notification") as mock_notify:
            self.controller.is_charging(notify=False)
            mock_notify.assert_not_called()



if __name__ == "__main__":
    unittest.main()

