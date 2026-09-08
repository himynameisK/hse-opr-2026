def format_money(cents):
    """Форматирует сумму в копейках."""
    return f"{cents // 100}.{cents % 100:02d} ₽"
