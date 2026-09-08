def total(items, discount_percent=0, delivery=0):
    """Возвращает итоговую стоимость заказа в копейках."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    discounted = subtotal * (100 - discount_percent) // 100
    return discounted + delivery
