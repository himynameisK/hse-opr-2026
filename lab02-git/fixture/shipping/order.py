def total(items, delivery=0):
    """Стоимость товаров и доставки, в копейках."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    return subtotal + delivery
