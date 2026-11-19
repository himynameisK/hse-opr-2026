#!/usr/bin/env bash
# Занятие 11 · Docker 2: одиннадцать сломанных контейнеров, условия, проверка, README.
# Нужен запущенный Docker (Docker Desktop или dockerd), root не нужен.
#   bash lab11-docker/setup.sh              в ../opr-lab11, рядом с репозиторием курса
#   bash lab11-docker/setup.sh /куда/надо   в свой каталог
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: bash $0" >&2; exit 1; }
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$(cd "$HERE/../.." && pwd)/opr-lab11}"

if [ -e "$DEST/check.py" ]; then
  echo "Лаба уже развёрнута: $DEST" >&2
  echo "Вернуть check.py и условия как было (решения не тронутся): bash \"$HERE/reset.sh\" \"$DEST\"" >&2
  echo "Вернуть задачу 3 целиком в исходное сломанное состояние: bash \"$HERE/reset.sh\" \"$DEST\" 3" >&2
  exit 1
fi
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "Каталог уже есть и не пуст: $DEST" >&2
  echo "Уберите его или укажите другой: bash $0 /путь" >&2
  exit 1
fi

mkdir -p "$DEST/задачи"
DEST="$(cd "$DEST" && pwd)"
for d in "$HERE"/tasks/*/; do
  cp -R "$d" "$DEST/задачи/$(basename "$d")"
done
install -m 0755 "$HERE/check.py" "$DEST/check.py"
install -m 0644 "$HERE/README.md" "$DEST/README.md"

PY=""
for c in python3 python py; do
  command -v "$c" >/dev/null 2>&1 || continue
  "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1 || continue
  PY="$c"; break
done

echo
echo "Задачи: $DEST/задачи/0-secrets … 11-signals, условие — УСЛОВИЕ.txt в каждой"
if ! docker info >/dev/null 2>&1; then
  echo "Внимание: docker не отвечает. Запустите Docker Desktop (или dockerd) до занятия."
fi
if [ -n "$PY" ]; then
  echo "Проверка: cd \"$DEST\" && $PY check.py"
else
  echo "Проверка: check.py, но Python 3.8+ не найден — поставьте его, см. README."
fi
echo "Готово: $DEST"
