#!/usr/bin/env bash
set -euo pipefail
# Занятие 4, заявки 1-3: не запускается файл, не запускается из-за CRLF,
# не пройти сквозь каталог. Привилегий не требуют — только root для useradd.

LAB="${1:-/opt/opr-lab04}"
STUDENT=opr
PATH="$PATH:/usr/sbin:/sbin"

[ "$(uname -s)" = "Linux" ] || { echo "Только Linux: ВМ, WSL или контейнер." >&2; exit 1; }
[ "$(id -u)" = "0" ] || { echo "Запускать от root." >&2; exit 1; }
command -v useradd >/dev/null || { echo "нет useradd (пакет passwd)" >&2; exit 1; }

id "$STUDENT" >/dev/null 2>&1 || useradd -m -s /bin/bash "$STUDENT"

make_script() {   # путь, слово, шебанг
  cat > "$1" <<EOF
$3
# Занятие 4. Скрипт печатает своё слово — если ему дадут запуститься.
echo $2
EOF
  chmod 0755 "$1"
}

mkdir -p "$LAB"/t1 "$LAB"/t2 "$LAB"/t3/config

# t1 — всё в порядке, кроме бита x у файла
make_script "$LAB/t1/script.sh" ok-1 '#!/bin/bash'
chmod 0644 "$LAB/t1/script.sh"

# t2 — приехал с Windows: CRLF во всех строках, включая шебанг
make_script "$LAB/t2/script.sh" ok-2 '#!/bin/bash'
awk '{ printf "%s\r\n", $0 }' "$LAB/t2/script.sh" > "$LAB/t2/.crlf"
mv "$LAB/t2/.crlf" "$LAB/t2/script.sh"
chmod 0755 "$LAB/t2/script.sh"

# t3 — сам скрипт исправен, но кто-то прошёлся chmod -R 644 по дереву:
# у ДВУХ каталогов на пути пропал x. Одной командой не видно, нужен namei -l.
make_script "$LAB/t3/config/script.sh" ok-3 '#!/bin/bash'

chown -R "$STUDENT:$STUDENT" "$LAB"/t1 "$LAB"/t2 "$LAB"/t3
chmod 0644 "$LAB/t3" "$LAB/t3/config"     # вот она, третья заявка

echo "Готово: заявки 1-3 в $LAB"
