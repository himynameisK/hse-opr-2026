#!/usr/bin/env bash
# Занятие 10: вернуть check.py, README, app.py и requirements.txt как было — ничего не спрашивая.
# Ваши Dockerfile, .dockerignore, compose.yaml и .github/ не трогает. Удалённый мусор кладёт обратно.
# Изменённые check.py и app.py перед этим сохраняются в *.bak.
#   bash lab10-docker/reset.sh              для ../opr-lab10
#   bash lab10-docker/reset.sh /куда/надо   для своего каталога
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: bash $0" >&2; exit 1; }
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="${1:-$(cd "$HERE/../.." && pwd)/opr-lab10}"

if [ ! -f "$DEST/check.py" ]; then
  echo "Лаба не развёрнута: $DEST" >&2
  echo "Сначала: bash \"$HERE/setup.sh\"" >&2
  exit 1
fi

for pair in "check.py:check.py" "app.py:app/app.py"; do
  f="${pair%%:*}"; src="$HERE/${pair#*:}"
  if [ -f "$DEST/$f" ] && ! cmp -s "$DEST/$f" "$src"; then
    cp -p "$DEST/$f" "$DEST/$f.bak"
    echo "Ваш $f сохранён: $DEST/$f.bak"
  fi
done
install -m 0755 "$HERE/check.py" "$DEST/check.py"
install -m 0644 "$HERE/README.md" "$DEST/README.md"
install -m 0644 "$HERE/app/app.py" "$DEST/app.py"
install -m 0644 "$HERE/app/requirements.txt" "$DEST/requirements.txt"
bash "$HERE/garbage.sh" "$DEST"
echo "Готово: $DEST — check.py, README и приложение как в начале, ваши файлы на месте"
