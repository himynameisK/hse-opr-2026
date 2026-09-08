def total(items):
    """Стоимость товаров в копейках."""
    return sum(item["price"] * item["quantity"] for item in items)
