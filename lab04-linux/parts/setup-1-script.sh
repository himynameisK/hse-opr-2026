#!/usr/bin/env bash
set -euo pipefail

# Эта лаба разворачивается ВНУТРИ Linux и от root: нужны useradd и, возможно, mount.
# Всё остальное студент делает обычным пользователем.

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-/opt/opr-lab04}"
STUDENT=opr
PATH="$PATH:/usr/sbin:/sbin"

[ "$(uname -s)" = "Linux" ] || {
  echo "Занятие 4 живёт только в Linux: виртуальная машина, WSL или контейнер." >&2; exit 1; }
[ "$(id -u)" = "0" ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
command -v useradd >/dev/null || { echo "нет useradd (пакет passwd)" >&2; exit 1; }

# Каталог создаёт головной setup.sh; повторный запуск ловится там же.

PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 || continue
  "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' >/dev/null 2>&1 || continue
  PY="$c"; break
done
[ -n "$PY" ] || { echo "Python 3.8+ не найден: поставьте python3" >&2; exit 1; }

# --- 1. Обычный пользователь ------------------------------------------------
# Под root пятая поломка не воспроизводится вообще: root обходит права на каталоги.
if ! id "$STUDENT" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$STUDENT"
fi

# --- 2. Раздел, смонтированный с noexec -------------------------------------
# Сначала ищем готовый (в контейнере это обычно /dev/shm), потом пробуем свой tmpfs.
usable_noexec() {
  local dir="$1" probe rc=0
  mkdir -p "$dir" 2>/dev/null || return 1
  probe="$dir/.probe.sh"
  printf '#!/bin/sh\nexit 7\n' > "$probe" 2>/dev/null || return 1
  chmod 0755 "$probe" 2>/dev/null || { rm -f "$probe"; return 1; }
  "$probe" >/dev/null 2>&1 || rc=$?
  rm -f "$probe"
  [ "$rc" != "7" ]          # запустился — значит exec разрешён, нам не подходит
}

NOEXEC=""
NAME="$(basename "$LAB")"
for candidate in ${OPR_NOEXEC:-} /noexec /dev/shm /run/shm; do
  [ -d "$candidate" ] || continue
  if usable_noexec "$candidate/$NAME"; then NOEXEC="$candidate/$NAME"; break; fi
  rmdir "$candidate/$NAME" 2>/dev/null || true
done
if [ -z "$NOEXEC" ]; then
  OWN="$LAB-noexec"
  mkdir -p "$OWN"
  if mount -t tmpfs -o noexec,nosuid,size=1m opr-noexec "$OWN" 2>/dev/null \
     && usable_noexec "$OWN"; then
    NOEXEC="$OWN"
  else
    umount "$OWN" 2>/dev/null || true
    rmdir "$OWN" 2>/dev/null || true
  fi
fi
if [ -z "$NOEXEC" ]; then
  echo "Не нашёл и не смог создать раздел с noexec." >&2
  echo "В виртуальной машине или WSL это делает сам setup.sh, но здесь mount не дали." >&2
  echo "Если вы в контейнере — запустите его так:" >&2
  echo "  docker run -it --rm --tmpfs /noexec:noexec,size=1m debian:12 bash" >&2
  echo "Или укажите готовую точку монтирования: OPR_NOEXEC=/что-то bash $0" >&2
  exit 1
fi

# --- 3. Пять скриптов -------------------------------------------------------
make_script() {   # путь, слово, шебанг
  cat > "$1" <<EOF
$3
# Занятие 4. Скрипт печатает своё слово — если ему дадут запуститься.
echo $2
EOF
  chmod 0755 "$1"
}

mkdir -p "$LAB"/s1 "$LAB"/s2 "$LAB"/s3 "$LAB"/s4 "$LAB"/s5

# Сама лаба обязана лежать там, где запускать РАЗРЕШЕНО: иначе сломаны все пять,
# а починить нельзя ни одного. Так бывает, если развернуть её в /tmp с noexec.
if usable_noexec "$LAB/s1"; then
  echo "Каталог $LAB сам лежит на разделе с noexec: здесь не запустится ничего." >&2
  echo "Разверните лабу на обычном разделе, например: bash $0 /opt/opr-lab04" >&2
  rm -rf "$LAB"
  exit 1
fi

# s1 — всё в порядке, кроме бита x
make_script "$LAB/s1/script.sh" ok-1 '#!/bin/bash'
chmod 0644 "$LAB/s1/script.sh"

# s2 — приехал с Windows: CRLF во всех строках, включая шебанг
make_script "$LAB/s2/script.sh" ok-2 '#!/bin/bash'
awk '{ printf "%s\r\n", $0 }' "$LAB/s2/script.sh" > "$LAB/s2/.crlf"
mv "$LAB/s2/.crlf" "$LAB/s2/script.sh"
chmod 0755 "$LAB/s2/script.sh"

# s3 — сам файл в порядке, а лежит на разделе с noexec
make_script "$NOEXEC/s3-script.sh" ok-3 '#!/bin/bash'
ln -s "$NOEXEC/s3-script.sh" "$LAB/s3/script.sh"

# s4 — шебанг указывает на интерпретатор, которого в этой системе нет
MISSING=/usr/local/bin/bash
if [ -e "$MISSING" ]; then MISSING=/opt/bash/bin/bash; fi
make_script "$LAB/s4/script.sh" ok-4 "#!$MISSING"

# s5 — сам скрипт исправен, закрыт каталог на пути к нему
make_script "$LAB/s5/script.sh" ok-5 '#!/bin/bash'

chmod 0755 "$LAB/check.py"

# Всё, что студент чинит, принадлежит ему: chmod можно делать без sudo.
chown -R "$STUDENT:$STUDENT" "$LAB"/s1 "$LAB"/s2 "$LAB"/s3 "$LAB"/s4 "$LAB"/s5
chown "$STUDENT:$STUDENT" "$NOEXEC/s3-script.sh"
chown root:root "$LAB" "$LAB/check.py"
chmod 0755 "$LAB"
chmod 0644 "$LAB/s5"           # вот она, поломка номер пять

# runuser лежит в util-linux и есть везде, но su — запасной вход.
as_student() {
  if command -v runuser >/dev/null 2>&1; then runuser -u "$STUDENT" -- "$@"
  else su "$STUDENT" -s /bin/sh -c "$*"; fi
}

as_student test -r "$LAB/s1/script.sh" || {
  echo "Пользователь $STUDENT не видит $LAB: каталог выше по пути закрыт." >&2
  echo "Разверните лабу в другом месте, например: bash $0 /srv/opr-lab04" >&2
  exit 1
}

echo "Готово: $LAB"
echo "Сломаны все пять скриптов, каждый ровно одним способом."
echo "Работать так:   su - $STUDENT   и   cd $LAB"
echo "Проверять так:  sudo $LAB/check.py   (проверка идёт от root)"
echo "Условие: $HERE/README.md"
case "$NOEXEC" in
  "$LAB-noexec") echo "Раздел с noexec поднят в $NOEXEC (tmpfs, после перезагрузки исчезнет)." ;;
  *)             echo "Раздел с noexec взят готовый: $NOEXEC" ;;
esac