#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-$HOME/opr-lab03}"
SHOP="$LAB/shop"

command -v git >/dev/null || { echo "git не найден" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 не найден" >&2; exit 1; }

if [[ -e "$LAB" ]]; then
  echo "Каталог уже существует: $LAB" >&2
  echo "Удалите его сами или укажите другой: make lab3 LAB3_DEST=/tmp/opr-lab03" >&2
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
mkdir -p deliveries
cp "$HERE/fixture/deliveries/"* deliveries/
printf '__pycache__/\n' > .gitignore
git add .
git commit -q -m "Начальная версия магазина и записанные доставки вебхука"
git tag start

echo "Готово: $SHOP"
echo "Хуков здесь пока нет — их вы напишете сами."
echo "Условие: $HERE/README.md"
