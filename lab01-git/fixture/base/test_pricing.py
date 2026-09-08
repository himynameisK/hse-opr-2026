import unittest

from pricing import total


class PricingTest(unittest.TestCase):
    def setUp(self):
        self.items = [{"price": 1000, "quantity": 2}]

    def test_items(self):
        self.assertEqual(total(self.items), 2000)

    def test_discount(self):
        self.assertEqual(total(self.items, discount_percent=10), 1800)

    def test_delivery(self):
        self.assertEqual(total(self.items, delivery=500), 2500)
