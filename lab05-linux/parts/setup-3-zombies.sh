#!/usr/bin/env bash
# Занятие 5, заявка 3. Служба, которая порождает рабочих и не забирает их коды
# возврата. Зомби занимают места в таблице процессов пользователя, и у него
# перестаёт запускаться что-либо ещё.
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: sudo bash $0" >&2; exit 1; }
set -euo pipefail

LAB="${1:-/opt/opr-lab05}"
COLLECTOR=/usr/local/sbin/opr-collector
STATE_DIR=/var/lib/opr-lab05
STATE="$STATE_DIR/state"
USER_NAME=opr
WORKERS=60
NPROC=80

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
command -v setsid >/dev/null || { echo "Не найден setsid" >&2; exit 1; }
command -v useradd >/dev/null || {
  echo "Не найден useradd — ставится вместе с passwd:" >&2
  echo "  apt-get update && apt-get install -y passwd" >&2
  exit 1; }
PY="$(command -v python3 || command -v python)" || { echo "Нужен python3" >&2; exit 1; }
mkdir -p "$STATE_DIR" "$LAB/t3" "$(dirname "$COLLECTOR")"

id "$USER_NAME" >/dev/null 2>&1 || useradd -m -s /bin/bash "$USER_NAME"

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

# Прошлый сборщик останавливаем: иначе зомби с прошлого запуска останутся висеть
# на мёртвом state, и проверка будет искать не того родителя.
for pid in $(pids_of "$COLLECTOR"); do
  kill -9 "$pid" 2>/dev/null || true
done

# Служба сборки отчётов. Поломка одна и ровно в одной отсутствующей строке:
# родитель не вызывает wait(), поэтому записи о завершившихся детях остаются
# в таблице процессов. Текст открыт — студент будет в него смотреть.
cat > "$COLLECTOR" <<EOF
#!$PY
"""Сборщик отчётов: раздаёт работу рабочим процессам и ждёт следующей смены."""
import os
import time

WORKERS = $WORKERS

for number in range(WORKERS):
    if os.fork() == 0:
        # Рабочий сделал своё дело и завершился с кодом 0.
        os._exit(0)

while True:
    time.sleep(30)
EOF
chmod 755 "$COLLECTOR"

# Скрипт дежурного — то, что у него перестало запускаться. Лимит на процессы
# выставлен тут же, явной строкой: на сервере он стоит в /etc/security/limits.d,
# но так заявка воспроизводится одинаково и в ВМ, и в WSL, и в контейнере.
cat > "$LAB/t3/report.sh" <<EOF
#!/usr/bin/env bash
# Выгрузка отчётов: двадцать пять параллельных задач.
# На сервере такой лимит стоит в /etc/security/limits.d/opr.conf.
ulimit -u $NPROC

for task in \$(seq 1 25); do
  ( sleep 0.2; echo "задача \$task: готово" > /dev/null ) &
done
wait
echo ok-3
EOF
chmod 755 "$LAB/t3/report.sh"

su -s /bin/bash "$USER_NAME" -c "setsid $COLLECTOR </dev/null >/dev/null 2>&1 &"

# Ждём, пока рабочие завершатся и превратятся в записи таблицы процессов.
PID=""
COUNT=0
for _ in $(seq 1 150); do
  PID="$(ps -u "$USER_NAME" -o pid=,stat=,args= 2>/dev/null \
         | awk -v c="$COLLECTOR" '$2 != "Z" && index($0, c) {print $1; exit}')"
  [ -n "$PID" ] || { sleep 0.2; continue; }
  COUNT="$(awk '$3 == "Z" && $4 == '"$PID"' {n++} END {print n+0}' /proc/[0-9]*/stat 2>/dev/null || echo 0)"
  [ "$COUNT" -ge "$WORKERS" ] && break
  sleep 0.2
done
[ -n "$PID" ] && [ -d "/proc/$PID" ] || { echo "Сборщик не поднялся" >&2; exit 1; }
[ "$COUNT" -ge 1 ] || { echo "Зомби не появились — ядро или python повели себя иначе" >&2; exit 1; }

STAT="$(cat "/proc/$PID/stat")"
STARTTIME="$(cut -d' ' -f20 <<< "${STAT##*) }")"
cat >> "$STATE" <<EOF
collector=$COLLECTOR
collector_pid=$PID
collector_starttime=$STARTTIME
collector_user=$USER_NAME
report=$LAB/t3/report.sh
workers=$COUNT
EOF
chmod 600 "$STATE"

echo "У пользователя $USER_NAME $COUNT записей в состоянии Z, и его выгрузка больше не запускается."
