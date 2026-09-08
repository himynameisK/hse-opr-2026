def total(items, discount_percent=0):
    """Стоимость товаров с процентной скидкой, в копейках."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    return subtotal * (100 - discount_percent) // 100
