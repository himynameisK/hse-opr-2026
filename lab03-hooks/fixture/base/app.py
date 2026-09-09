"""Точка входа учебного магазина."""

import os

from pricing import total


def load_config():
    return {
        "api_url": os.environ.get("API_URL", "http://localhost:8000"),
        "token": os.environ.get("SHOP_TOKEN", ""),
    }


if __name__ == "__main__":
    print(total([{"price": 1000, "quantity": 2}], discount_percent=10, delivery=500))
