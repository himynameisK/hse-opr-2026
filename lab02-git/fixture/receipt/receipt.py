from catalog import item_title
from money import format_money
from order import total


def build(items):
    """Собирает чек: строка на позицию и итог."""
    lines = [
        f"{item_title(item)} — {format_money(item['price'] * item['quantity'])}"
        for item in items
    ]
    lines.append(f"Итого: {format_money(total(items))}")
    return "\n".join(lines)
