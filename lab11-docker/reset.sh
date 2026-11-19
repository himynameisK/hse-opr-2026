#!/usr/bin/env bash
# Занятие 11: вернуть check.py, условия и README как было — ничего не спрашивая.
# С номерами задач — ещё и сами задачи: каталог задачи/N-… снова сломан, как в начале.
# Изменённое перед этим сохраняется в бэкап/ (check.py — в check.py.bak).
#   bash lab11-docker/reset.sh                   check.py, README, УСЛОВИЕ.txt; решения не трогает
#   bash lab11-docker/reset.sh 3                 и задачу 3 целиком; можно несколько: 3 5
#   bash lab11-docker/reset.sh все               и все задачи
#   bash lab11-docker/reset.sh /куда/надо 3      то же для своего каталога
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: bash $0" >&2; exit 1; }
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST=""
NUMS=()
for a in "$@"; do
  case "$a" in
    все|all) for d in "$HERE"/tasks/*/; do n="$(basename "$d")"; NUMS+=("${n%%-*}"); done ;;
    *[!0-9]*|"") DEST="$a" ;;
    *) NUMS+=("$a") ;;
  esac
done
DEST="${DEST:-$(cd "$HERE/../.." && pwd)/opr-lab11}"

if [ ! -f "$DEST/check.py" ]; then
  echo "Лаба не развёрнута: $DEST" >&2
  echo "Сначала: bash \"$HERE/setup.sh\"" >&2
  exit 1
fi
DEST="$(cd "$DEST" && pwd)"

# Сначала убедиться, что все номера есть — чтобы не сделать половину работы.
for n in ${NUMS[@]+"${NUMS[@]}"}; do
  set -- "$HERE"/tasks/"$n"-*/
  [ -d "$1" ] || { echo "Нет задачи $n. Задачи: $(cd "$HERE/tasks" && ls | sed 's/-.*//' | sort -n | tr '\n' ' ')" >&2; exit 1; }
done

if ! cmp -s "$DEST/check.py" "$HERE/check.py"; then
  cp -p "$DEST/check.py" "$DEST/check.py.bak"
  echo "Ваш check.py сохранён: $DEST/check.py.bak"
fi
install -m 0755 "$HERE/check.py" "$DEST/check.py"
install -m 0644 "$HERE/README.md" "$DEST/README.md"
mkdir -p "$DEST/задачи"
for d in "$HERE"/tasks/*/; do
  name="$(basename "$d")"
  mkdir -p "$DEST/задачи/$name"
  install -m 0644 "$d/УСЛОВИЕ.txt" "$DEST/задачи/$name/УСЛОВИЕ.txt"
done

STAMP="$(date +%Y%m%d-%H%M%S)"
for n in ${NUMS[@]+"${NUMS[@]}"}; do
  set -- "$HERE"/tasks/"$n"-*/
  src="${1%/}"
  name="$(basename "$src")"
  dst="$DEST/задачи/$name"
  if [ -d "$dst" ] && ! diff -r "$src" "$dst" >/dev/null 2>&1; then
    mkdir -p "$DEST/бэкап"
    mv "$dst" "$DEST/бэкап/$name-$STAMP"
    echo "Задача $n: ваш вариант сохранён в $DEST/бэкап/$name-$STAMP"
  else
    rm -rf "$dst"
  fi
  cp -R "$src" "$dst"
  echo "Задача $n: снова как в начале — $dst"
done
if [ ${#NUMS[@]} -eq 0 ]; then
  echo "Готово: $DEST — check.py, условия и README как в начале, решения на месте"
else
  echo "Готово: $DEST"
fi
