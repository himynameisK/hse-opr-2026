import unittest

from money import format_money


class MoneyTest(unittest.TestCase):
    def test_positive_amount(self):
        self.assertEqual(format_money(12345), "123.45 ₽")
