#!/usr/bin/env bash
# Занятие 4: вернуть всё в состояние до начала решения.
# Сносит развёрнутое занятие вместе с loop-разделом и разворачивает заново.
# Запускать ВНУТРИ своего Linux и от root: sudo bash reset.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-/opt/opr-lab04}"
MNT=/srv/cache
PATH="$PATH:/usr/sbin:/sbin"

[ "$(uname -s)" = "Linux" ] || { echo "Только Linux: ВМ, WSL или контейнер." >&2; exit 1; }
[ "$(id -u)" = "0" ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }

# 1. Отцепить учебный раздел. Пока он смонтирован, файл-образ удалять нельзя:
#    место не освободится, а точка останется висеть на удалённом inode.
for _ in 1 2 3; do
  mountpoint -q "$MNT" 2>/dev/null || break
  umount "$MNT" 2>/dev/null || umount -l "$MNT" 2>/dev/null || true
done
if mountpoint -q "$MNT" 2>/dev/null; then
  echo "Не вышло отмонтировать $MNT — закройте программы, которые туда смотрят" >&2
  echo "(lsof +f -- $MNT), и запустите reset.sh ещё раз." >&2
  exit 1
fi

# 2. Снести всё развёрнутое. Вместе с $LAB уходит и файл-образ раздела.
rm -rf "$LAB"
rm -rf "$MNT"

# 3. Развернуть заново — заявки соберутся с нуля, как в первый раз.
bash "$HERE/setup.sh" "$LAB"
