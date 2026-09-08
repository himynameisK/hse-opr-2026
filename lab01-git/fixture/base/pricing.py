def total(items, discount_percent=0, delivery=0):
    """Возвращает итоговую стоимость заказа в копейках."""
    subtotal = sum(item["price"] * item["quantity"] for item in items)
    return (subtotal + delivery) * (100 - discount_percent) // 100
