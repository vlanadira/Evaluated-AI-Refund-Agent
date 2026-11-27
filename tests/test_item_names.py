import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from objects import PurchaseItem
from tools import _assess_refund, display_item_name


class ItemDisplayNameTests(unittest.TestCase):
    def test_known_items_use_customer_friendly_names(self):
        self.assertEqual(display_item_name("esp32_devkit"), "ESP32 Dev Kit")
        self.assertEqual(
            display_item_name("dht22_temperature_sensor"),
            "DHT22 temperature sensor",
        )

    def test_unknown_item_identifier_is_readable(self):
        self.assertEqual(
            display_item_name("new_sensor_type"),
            "New Sensor Type",
        )

    def test_refund_assessment_uses_display_names(self):
        assessment, _ = _assess_refund(
            "customer_001",
            [
                PurchaseItem(name="esp32_devkit"),
                PurchaseItem(name="dht22_temperature_sensor"),
            ],
        )

        self.assertIn("ESP32 Dev Kit: eligible", assessment)
        self.assertIn("DHT22 temperature sensor: eligible", assessment)
        self.assertNotIn("_", assessment)


if __name__ == "__main__":
    unittest.main()
