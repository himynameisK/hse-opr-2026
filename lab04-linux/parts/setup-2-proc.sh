#!/usr/bin/env bash
# Занятие 4. Создаёт состояние: журнал со случайным содержимым, службу, которая
# держит его открытым, и rm поверх этого.
# Запускать ВНУТРИ своего Linux и от root: скрипт пишет в /var и /usr/local/sbin.

# Проверка до set -o pipefail: под sh (dash) следующая же строка падает
# с «Illegal option -o pipefail», и догадаться по ней не о чем.
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: sudo bash $0" >&2; exit 1; }
set -euo pipefail

LOG=/var/log/opr-audit.log
DAEMON=/usr/local/sbin/opr-auditd
STATE_DIR=/var/lib/opr-lab04
STATE="$STATE_DIR/state"
RESTORED_DIR=/var/tmp/opr-lab04
RESTORED="$RESTORED_DIR/restored.log"
RAW_BYTES=$((24 * 1024 * 1024))   # столько случайных байт; в base64 выйдет ~33 МБ

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
[ -r /proc/self/stat ] || { echo "Нужен смонтированный /proc" >&2; exit 1; }
for tool in base64 sha256sum stat setsid df; do
  command -v "$tool" >/dev/null || { echo "Не найден $tool" >&2; exit 1; }
done

# Повторный запуск разрешён и нужен: если студент убил службу, содержимое ушло
# вместе с ней, и вернуть задание в рабочее состояние больше нечем.
# Прежнего держателя ищем по дескриптору, а не по имени процесса: так под kill
# не попадёт чужой редактор, у которого в командной строке похожая строка.
for entry in /proc/[0-9]*; do
  for link in "$entry"/fd/*; do
    target="$(readlink "$link" 2>/dev/null || true)"
    [ "$target" = "$LOG" ] || [ "$target" = "$LOG (deleted)" ] || continue
    kill "${entry#/proc/}" 2>/dev/null || true
    echo "Прошлая служба (pid ${entry#/proc/}) остановлена: содержимое журнала будет другим."
    break
  done
done
rm -f "$LOG" "$RESTORED" "$STATE"
mkdir -p "$STATE_DIR" "$RESTORED_DIR" /var/log "$(dirname "$DAEMON")"
chmod 700 "$STATE_DIR"

# Тело журнала — случайное. Эталон нигде не лежит, хранится только его sha256:
# подсмотреть или набрать руками нечего, вернуть можно лишь через дескриптор.
{
  printf '# opr-audit: журнал аудита, создан %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  head -c "$RAW_BYTES" /dev/urandom | base64
} > "$LOG"
chmod 640 "$LOG"
SIZE="$(stat -c %s "$LOG")"
SHA="$(sha256sum "$LOG" | cut -d' ' -f1)"

# Учебная «служба аудита»: открывает журнал на дозапись и больше ничего не делает.
# Дочернему sleep дескриптор не достаётся (9>&-), иначе журнал держали бы двое.
cat > "$DAEMON" <<EOF
#!/usr/bin/env bash
# Держит свой журнал открытым, как это делает любая служба с логом.
exec 9>>"$LOG"
echo \$\$ > "$STATE_DIR/holder.pid"
while :; do sleep 30 9>&-; done
EOF
chmod 755 "$DAEMON"

setsid "$DAEMON" </dev/null >/dev/null 2>&1 &
PID=""
for _ in $(seq 1 100); do
  [ -s "$STATE_DIR/holder.pid" ] && { PID="$(cat "$STATE_DIR/holder.pid")"; break; }
  sleep 0.1
done
# Подсказку убираем: найти процесс — часть задания.
rm -f "$STATE_DIR/holder.pid"
[ -n "$PID" ] && [ -d "/proc/$PID" ] || { echo "Служба не поднялась" >&2; exit 1; }
[ "$(readlink "/proc/$PID/fd/9")" = "$LOG" ] || { echo "Служба не открыла журнал" >&2; exit 1; }

# Время старта процесса (поле 22 в /proc/<pid>/stat): по нему проверка отличит
# тот самый процесс от нового, которому достался освободившийся pid.
STAT="$(cat "/proc/$PID/stat")"
STARTTIME="$(cut -d' ' -f20 <<< "${STAT##*) }")"

# Занятое место снимаем до и после rm: сравнить эти два числа студенту больше
# негде — к моменту, когда он дойдёт до df, удаление уже случилось.
used() { df -P "$1" | tail -1 | tr -s ' ' | cut -d' ' -f3; }
USED_BEFORE="$(used /var/log)"
rm "$LOG"
USED_AFTER="$(used /var/log)"
[ "$(readlink "/proc/$PID/fd/9")" = "$LOG (deleted)" ] || { echo "Файл не удалился" >&2; exit 1; }

# Состояние для проверки: пары ключ=значение, чтобы check.py обошёлся hashlib
# и не требовал ничего сверх голого python3.
cat > "$STATE" <<EOF
log=$LOG
restored=$RESTORED
pid=$PID
starttime=$STARTTIME
size=$SIZE
sha256=$SHA
EOF
chmod 600 "$STATE"

echo "Готово."
echo "df /var/log, колонка Used: до rm $USED_BEFORE, после rm $USED_AFTER (1K-блоков)."
echo "Журнала $LOG больше нет в каталоге, а занятое им место не вернулось."
echo "Восстановите содержимое в $RESTORED, не убивая процесс."
echo "Проверка (от root): python3 check.py"