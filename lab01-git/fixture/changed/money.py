def format_money(cents):
    """Форматирует сумму в копейках, включая отрицательные значения."""
    sign = "-" if cents < 0 else ""
    rubles, kopecks = divmod(abs(cents), 100)
    return f"{sign}{rubles}.{kopecks:02d} ₽"
