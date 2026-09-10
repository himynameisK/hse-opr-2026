#!/usr/bin/env bash
# Собирает репозиторий для слайдов 19–21 лекции 2.
# Две ветки правят РАЗНЫЕ файлы, слияние проходит чисто, тесты падают.
set -euo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY
DEST="${1:-$HOME/демо-семантика}"
[ -e "$DEST" ] && { echo "Каталог уже существует: $DEST"; echo "Удалите его или укажите другой: ./собрать.sh /tmp/демо"; exit 1; }

mkdir -p "$DEST"; cd "$DEST"
git init -q -b main
git config user.name "Преподаватель"
git config user.email "opr@example.invalid"
git config commit.gpgsign false
git config core.quotepath false

# ── база: cart.py с функцией total_price и её вызов в checkout.py
cat > cart.py <<'PY'
def total_price(items):
    """Стоимость корзины в копейках."""
    return sum(i["price"] * i["qty"] for i in items)
PY
cat > checkout.py <<'PY'
from cart import total_price


def receipt(items):
    return f"К оплате: {total_price(items)}"
PY
cat > test_cart.py <<'PY'
import unittest
from cart import total_price


class CartTest(unittest.TestCase):
    def test_sum(self):
        self.assertEqual(total_price([{"price": 100, "qty": 2}]), 200)
PY
git add . && git commit -q -m "Корзина и чек"

# ── ветка 1: переименование, все существующие вызовы поправлены
git switch -q -c feature/rename
sed -i '' 's/total_price/order_total/g' cart.py checkout.py test_cart.py 2>/dev/null \
  || sed -i 's/total_price/order_total/g' cart.py checkout.py test_cart.py
git commit -qam "Переименовать total_price в order_total"

# ── ветка 2: новый файл со СТАРЫМ именем, про переименование не знает
git switch -q main
git switch -q -c feature/report
cat > report.py <<'PY'
from cart import total_price


def daily(orders):
    return sum(total_price(o) for o in orders)
PY
cat > test_report.py <<'PY'
import unittest
from report import daily


class ReportTest(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(daily([[{"price": 100, "qty": 2}]]), 200)
PY
git add . && git commit -q -m "Добавить дневной отчёт"

git switch -q feature/rename
echo "Готово: $DEST"
echo "Вы на ветке feature/rename. Дальше по слайду 19: git merge feature/report"
