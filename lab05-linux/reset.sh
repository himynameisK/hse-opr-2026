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

# 2. Остановить учебные службы.
# Процессы службы ищем по argv[0], а не по вхождению пути в командную строку:
# иначе под kill попадает всё, где путь просто упомянут в аргументах, —
# редактор с открытым юнитом, grep по /etc или шелл самого студента.
pids_of() {
  local path="$1" entry argv0
  for entry in /proc/[0-9]*; do
    [ -r "$entry/cmdline" ] || continue
    argv0="$(tr '\0' '\n' < "$entry/cmdline" 2>/dev/null | head -1)"
    [ "$argv0" = "$path" ] || continue
    echo "${entry#/proc/}"
  done
}

for name in /usr/local/sbin/opr-auditd /usr/local/sbin/opr-collector /usr/local/sbin/opr-api; do
  for pid in $(pids_of "$name"); do
    kill -9 "$pid" 2>/dev/null || true
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
