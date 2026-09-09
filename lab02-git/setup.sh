#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-$HOME/opr-lab02}"
SHOP="$LAB/shop"

command -v git >/dev/null || { echo "git не найден" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 не найден" >&2; exit 1; }

if [[ -e "$LAB" ]]; then
  echo "Каталог уже существует: $LAB" >&2
  echo "Удалите его сами или укажите другой: make lab2 DEST=/tmp/opr-lab02" >&2
  exit 1
fi

mkdir -p "$SHOP"
cd "$SHOP"
git init -q
git symbolic-ref HEAD refs/heads/main
git config user.name "OPR Course"
git config user.email "opr-course@example.invalid"

cp "$HERE/fixture/base/order.py" .
cp "$HERE/fixture/base/money.py" .
cp "$HERE/fixture/base/catalog.py" .
cp "$HERE/fixture/base/check.py" .
chmod +x check.py
printf '__pycache__/\n' > .gitignore
git add .
git commit -q -m "Начальная версия расчёта заказа"
BASE=$(git rev-parse HEAD)

cp "$HERE/fixture/discount/order.py" order.py
git add order.py
git commit -q -m "Добавить процентную скидку"

cp "$HERE/fixture/fix/money.py" money.py
git add money.py
git commit -q -m "Исправить формат отрицательных сумм"
git reset -q --hard HEAD~1

git switch -q -c feature/naming "$BASE"
cp "$HERE/fixture/naming/catalog.py" catalog.py
git add catalog.py
git commit -q -m "Переименовать item_title в format_item"

git switch -q -c feature/receipt "$BASE"
cp "$HERE/fixture/receipt/receipt.py" receipt.py
cp "$HERE/fixture/receipt/test_receipt.py" test_receipt.py
git add receipt.py test_receipt.py
git commit -q -m "Добавить сборку чека"

git switch -q -c feature/shipping "$BASE"
cp "$HERE/fixture/shipping/order.py" order.py
git add order.py
git commit -q -m "Добавить стоимость доставки"

echo "Готово: $SHOP"
echo "Текущая ветка: feature/shipping"
echo "Ветки в работе: main, feature/naming, feature/receipt"
echo "Условие: $HERE/README.md"
