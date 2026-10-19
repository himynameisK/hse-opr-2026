#!/usr/bin/env bash
# Занятие 9 · Скрипт, который не ломается. Разворачивает учебную выкладку.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$(cd "$HERE/../.." && pwd)/opr-lab09}"

[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: bash $0" >&2; exit 1; }

if [ -e "$DEST" ]; then
  echo "Каталог уже есть: $DEST" >&2
  echo "Уберите его или укажите другой: bash $0 /путь" >&2
  exit 1
fi

mkdir -p "$DEST/app/logs" "$DEST/app/releases/old" "$DEST/app/releases/current"
install -m 0755 "$HERE/fixture/deploy.sh" "$DEST/deploy.sh"
install -m 0755 "$HERE/fixture/check.py" "$DEST/check.py"

printf '2.4.1\n' > "$DEST/app/VERSION"
printf 'ERROR база недоступна\nINFO всё хорошо\nERROR таймаут\n' > "$DEST/app/logs/report.txt"
printf 'строка журнала\n' > "$DEST/app/logs/app.log"
printf 'строка журнала\n' > "$DEST/app/logs/my report.log"
printf 'старый релиз\n' > "$DEST/app/releases/old/release.txt"

echo
echo "Готово: $DEST"
echo "Скрипт выкладки: $DEST/deploy.sh, данные в $DEST/app"
echo "Условие: $HERE/README.md"
echo "Проверка: $DEST/check.py"
