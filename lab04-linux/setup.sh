#!/usr/bin/env bash
# Занятие 4 · Файлы, права, процессы. Разворачивает заявки дежурной смены.
# Запускать ВНУТРИ своего Linux и от root: нужны useradd, mount, запись в /var.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-/opt/opr-lab04}"

[ "$(uname -s)" = "Linux" ] || {
  echo "Занятие 4 живёт только в Linux: виртуальная машина, WSL или контейнер." >&2
  echo "На macOS и в Windows напрямую прав и точек монтирования просто нет." >&2
  exit 1; }
[ "$(id -u)" = "0" ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }

PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 || continue
  "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' >/dev/null 2>&1 || continue
  PY="$c"; break
done
[ -n "$PY" ] || {
  echo "Python 3.8+ не найден. В голом контейнере его нет, ставится одной строкой:" >&2
  echo "  apt-get update && apt-get install -y python3" >&2
  exit 1; }

if [ -e "$LAB/check.py" ]; then
  echo "Лаба уже развёрнута: $LAB" >&2
  echo "Чтобы начать заново: sudo bash $HERE/reset.sh" >&2
  exit 1
fi

# Проверку кладём ДО частей: часть 1 выставляет на неё права.
mkdir -p "$LAB"
install -m 0755 "$HERE/fixture/check.py" "$LAB/check.py"

# Код 3 от части — «развернуть не дали, но это не беда»: так выходит заявка 4,
# когда в контейнере нет --privileged. Остальные части должны развернуться.
for p in "$HERE"/parts/setup-*.sh; do
  echo "── $(basename "$p")"
  rc=0; bash "$p" "$LAB" || rc=$?
  [ "$rc" = 0 ] || [ "$rc" = 3 ] || exit "$rc"
done
echo
echo "Готово: $LAB"
echo "Условие: $HERE/README.md"
echo "Проверка: sudo $LAB/check.py"
