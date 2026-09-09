import unittest

from receipt import build


class ReceiptTest(unittest.TestCase):
    def test_build(self):
        items = [{"name": "Кружка", "price": 1000, "quantity": 2}]
        self.assertEqual(
            build(items),
            "Кружка x2 — 20.00 ₽\nИтого: 20.00 ₽",
        )
