"""Ведомость оценок. Код не менять: при проверке check.py сам правит REPORT_VERSION в своей копии."""
import tabulate

REPORT_VERSION = "1.0"

ROWS = [
    ("Иванов", 8),
    ("Петрова", 10),
    ("Сидоров", 6),
]

print(tabulate.tabulate(ROWS, headers=["студент", "балл"], tablefmt="github"))
print("версия ведомости: {}; tabulate {}".format(REPORT_VERSION, tabulate.__version__))
