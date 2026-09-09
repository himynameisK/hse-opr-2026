#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-$HOME/opr-lab01}"
SHOP="$LAB/shop"

command -v git >/dev/null || { echo "git не найден" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 не найден" >&2; exit 1; }

if [[ -e "$LAB" ]]; then
  echo "Каталог уже существует: $LAB" >&2
  echo "Удалите его сами или укажите другой: make lab1 LAB1_DEST=/tmp/opr-lab01" >&2
  exit 1
fi

mkdir -p "$SHOP"
cd "$SHOP"
git init -q
git symbolic-ref HEAD refs/heads/main
git config user.name "OPR Course"
git config user.email "opr-course@example.invalid"

cp "$HERE/fixture/base/"*.py .
cp "$HERE/fixture/check.py" check.py
chmod +x check.py
printf '__pycache__/\n' > .gitignore
git add .
git commit -q -m "Начальная версия магазина"
git tag start

cp "$HERE/fixture/changed/"*.py .
printf 'API_URL=http://localhost:8000\n' > .env.local
printf 'DEBUG cart_id=42 subtotal=2000\n' > debug.log
git add .

echo "Готово: $SHOP"
echo "Все изменения уже добавлены в индекс. Начните с git status."
echo "Условие: $HERE/README.md"
