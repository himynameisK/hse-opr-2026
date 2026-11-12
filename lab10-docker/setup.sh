#!/usr/bin/env bash
# Занятие 10 · Docker 1. Готовое приложение-счётчик, мусор вокруг него и проверка.
# Студент пишет Dockerfile, .dockerignore, compose.yaml и .github/workflows/ci.yml.
# Root не нужен, нужен Docker: Docker Desktop (macOS, Windows) или docker engine (Linux).
#   bash lab10-docker/setup.sh              в ../opr-lab10, рядом с репозиторием курса
#   bash lab10-docker/setup.sh /куда/надо   в свой каталог
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: bash $0" >&2; exit 1; }
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$(cd "$HERE/../.." && pwd)/opr-lab10}"

if [ -e "$DEST/check.py" ]; then
  echo "Лаба уже развёрнута: $DEST" >&2
  echo "Вернуть check.py, README и код приложения как было (ваши файлы не тронутся): bash \"$HERE/reset.sh\" \"$DEST\"" >&2
  exit 1
fi
if [ -e "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "Каталог уже есть и не пуст: $DEST" >&2
  echo "Уберите его или укажите другой: bash $0 /путь" >&2
  exit 1
fi

mkdir -p "$DEST"
DEST="$(cd "$DEST" && pwd)"
install -m 0644 "$HERE/app/app.py" "$DEST/app.py"
install -m 0644 "$HERE/app/requirements.txt" "$DEST/requirements.txt"
install -m 0755 "$HERE/check.py" "$DEST/check.py"
install -m 0644 "$HERE/README.md" "$DEST/README.md"
bash "$HERE/garbage.sh" "$DEST"

PY=""
for c in python3 python py; do
  command -v "$c" >/dev/null 2>&1 || continue
  "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1 || continue
  PY="$c"; break
done

echo
echo "Приложение: $DEST/app.py — код не правим, только упаковываем"
echo "Ваши файлы: Dockerfile, .dockerignore, compose.yaml, .github/workflows/ci.yml"
if [ -n "$PY" ]; then
  echo "Проверка: cd \"$DEST\" && $PY check.py"
else
  echo "Проверка: check.py, но Python 3.8+ не найден — поставьте его"
fi
docker info >/dev/null 2>&1 || echo "Внимание: docker не отвечает — запустите Docker Desktop до проверки"
echo "Готово: $DEST"
