#!/usr/bin/env bash
set -euo pipefail
# Занятие 4, заявка 4: на разделе кончились inode, а место свободно.
# Нужен loop-mount: в ВМ и WSL работает, в контейнере — только с --privileged.

LAB="${1:-/opt/opr-lab04}"
STUDENT=opr
IMG="$LAB/.cache-disk.img"
MNT=/srv/cache
PATH="$PATH:/usr/sbin:/sbin"

command -v mkfs.ext4 >/dev/null || {
  echo "нет mkfs.ext4 (пакет e2fsprogs) — заявка 4 не развернётся" >&2; exit 1; }

mkdir -p "$MNT"
dd if=/dev/zero of="$IMG" bs=1M count=24 status=none
# Мало inode при нормальном объёме — ровно та диспропорция, что бывает в жизни
mkfs.ext4 -q -N 256 -F "$IMG" 2>/dev/null

if ! mount -o loop "$IMG" "$MNT" 2>/dev/null; then
  rm -f "$IMG"; rmdir "$MNT" 2>/dev/null || true
  echo "Смонтировать не дали — заявка 4 пропущена." >&2
  echo "В виртуальной машине и WSL она разворачивается сама." >&2
  echo "В контейнере нужен флаг: docker run --privileged ..." >&2
  exit 3
fi

# Три файла, которые терять нельзя: это и есть смысл задачи — чистить выборочно
mkdir -p "$MNT/data"
printf 'важные данные за сентябрь\n' > "$MNT/data/report-2026-09.csv"
printf 'важные данные за август\n'   > "$MNT/data/report-2026-08.csv"
printf 'настройки сервиса\n'         > "$MNT/data/service.conf"

# Служба, которая писала по файлу на сессию и съела все inode
mkdir -p "$MNT/sessions"
i=0
while : ; do
  : > "$MNT/sessions/sess-$i" 2>/dev/null || break
  i=$((i+1))
  [ "$i" -gt 5000 ] && break
done

chown -R "$STUDENT:$STUDENT" "$MNT"
chmod 0755 "$MNT"
echo "Готово: заявка 4 — раздел $MNT, inode заняты ($i файлов сессий)"
