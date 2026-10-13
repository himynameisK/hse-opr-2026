#!/usr/bin/env bash
# Занятие 5: вернуть всё в состояние до начала решения.
# Останавливает учебные службы, сносит развёрнутое и разворачивает заново.
# Запускать ВНУТРИ своего Linux и от root: sudo bash reset.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-/opt/opr-lab05}"

[ "$(uname -s)" = "Linux" ] || { echo "Только Linux: ВМ, WSL или контейнер." >&2; exit 1; }
[ "$(id -u)" = "0" ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }

# 1. Закрыть учебные сессии tmux вместе со всем, что в них крутится.
for session in tariffs tariffs-old nightly tmp api; do
  tmux kill-session -t "$session" 2>/dev/null || true
done

# 2. Остановить учебные службы. Ищем по командной строке, а не по имени: так
#    под kill не попадёт чужой процесс с похожим названием в аргументах.
for name in /usr/local/sbin/opr-auditd /usr/local/sbin/opr-collector /usr/local/sbin/opr-api; do
  for entry in /proc/[0-9]*; do
    [ -r "$entry/cmdline" ] || continue
    tr '\0' ' ' < "$entry/cmdline" 2>/dev/null | grep -q "$name" || continue
    kill -9 "${entry#/proc/}" 2>/dev/null || true
  done
done
# 3. Убрать юнит, которым студент заменил запуск из tmux. Имя он выбирал сам,
#    поэтому ищем по строке запуска, а не по имени файла.
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  for unit in $(grep -rls "/usr/local/sbin/opr-api" /etc/systemd/system 2>/dev/null); do
    name="$(basename "$unit")"
    systemctl stop "$name" 2>/dev/null || true
    systemctl disable "$name" 2>/dev/null || true
    rm -f "$unit"
  done
  systemctl daemon-reload 2>/dev/null || true
fi

# 4. Снести всё, что заявки насыпали по системе, вместе с ответами студента.
#    Пользователя opr оставляем: его домашний каталог к заявкам отношения не имеет.
rm -rf "$LAB" /var/lib/opr-lab05 /var/tmp/opr-lab05
rm -f /var/log/opr-audit.log
rm -f /usr/local/sbin/opr-auditd /usr/local/sbin/opr-collector /usr/local/sbin/opr-api

# 5. Развернуть заново — заявки соберутся с нуля, как в первый раз.
bash "$HERE/setup.sh" "$LAB"
