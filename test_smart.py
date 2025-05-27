import unittest
from unittest.mock import patch, MagicMock
from smart import check_battery_level, stop_charging, is_charging

class TestSmartcarBatteryLogic(unittest.TestCase):
    @patch("smart.requests.get")
    def test_check_battery_level_stops_charging_when_above_threshold(self, mock_get):
        # Setup mock for battery level API
        mock_battery_response = MagicMock()
        mock_battery_response.json.return_value = {"percentRemaining": 0.85}
        mock_battery_response.status_code = 200
        mock_battery_response.raise_for_status = MagicMock()
        
        # Patch both battery and stop charging requests
        mock_get.return_value = mock_battery_response

        # Patch stop_charging to monitor its call
        with patch("smart.stop_charging") as mock_stop:
            check_battery_level("fake_vehicle_id")
            mock_stop.assert_called_once()

    @patch("smart.zappi_request")
    def test_stop_charging_only_if_currently_charging(self, mock_zappi_request):
        # Simulate Zappi is charging
        mock_zappi_request.side_effect = [
            MagicMock(json=lambda: {"zmo": "1", "sta": "3"}),  # is_charging
            MagicMock(status_code=200, text="OK", raise_for_status=MagicMock())  # stop_charging
        ]

        stop_charging()
        self.assertEqual(mock_zappi_request.call_count, 2)

    @patch("smart.zappi_request")
    def test_stop_charging_skips_if_not_charging(self, mock_zappi_request):
        # Simulate Zappi is not charging
        mock_zappi_request.return_value.json.return_value = {"zmo": "4", "sta": "1"}  # Not charging
        stop_charging()
        # Only one call to check status, no attempt to stop
        mock_zappi_request.assert_called_once()

if __name__ == "__main__":
    unittest.main()

