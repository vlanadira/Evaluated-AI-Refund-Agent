import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web import chat_storage


class ChatStorageRefundStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        for name, value in (
            ("DATA_DIR", root),
            ("DATABASE_FILE", root / "chats.sqlite3"),
        ):
            patcher = patch.object(chat_storage, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        chat_storage.initialize_database()

    def test_only_issued_item_is_marked_in_saved_purchase_cards(self):
        chat = chat_storage.create_chat()
        chat_storage.append_turn(
            chat["id"],
            [],
            [
                {"role": "user", "text": "I want to request a refund."},
                {
                    "role": "assistant",
                    "text": "Which item?",
                    "purchases": [
                        {"name": "esp32_devkit"},
                        {"name": "dht22_temperature_sensor"},
                    ],
                },
            ],
            None,
        )

        updated = chat_storage.append_turn(
            chat["id"],
            [],
            [
                {"role": "user", "text": "The ESP32 Dev Kit."},
                {"role": "assistant", "text": "Your refund was issued."},
            ],
            None,
            refunded_items=["esp32_devkit"],
        )

        purchases = updated["messages"][1]["purchases"]
        self.assertTrue(purchases[0]["refundIssued"])
        self.assertNotIn("refundIssued", purchases[1])


if __name__ == "__main__":
    unittest.main()
