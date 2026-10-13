#!/usr/bin/env bash
# Занятие 5, заявка 2. Четыре отсоединённые сессии tmux. В одной из них в истории
# панели лежит контрольная сумма, которой нет ни в одном файле на диске.
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: sudo bash $0" >&2; exit 1; }
set -euo pipefail

LAB="${1:-/opt/opr-lab05}"
STATE_DIR=/var/lib/opr-lab05
STATE="$STATE_DIR/state"
SEED="$STATE_DIR/seed-tariffs.sh"
ANSWER=/var/tmp/opr-lab05/checksum.txt
SESSIONS="tariffs tariffs-old nightly tmp"

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
command -v tmux >/dev/null || {
  echo "Не найден tmux — без него заявок 2 и 4 не будет:" >&2
  echo "  apt-get update && apt-get install -y tmux" >&2
  exit 1; }
command -v sha256sum >/dev/null || { echo "Не найден sha256sum" >&2; exit 1; }
mkdir -p "$STATE_DIR" "$(dirname "$ANSWER")" "$LAB"
chmod 1777 "$(dirname "$ANSWER")"
rm -f "$ANSWER"

# Прошлые учебные сессии убираем: иначе студент будет искать сумму в истории
# с предыдущего развёртывания, а проверка ждёт новую.
for s in $SESSIONS; do tmux kill-session -t "$s" 2>/dev/null || true; done

# Контрольная сумма существует в одном месте — в памяти tmux-сервера. На диске
# остаётся только её sha256: списать нельзя даже будучи root.
VALUE="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
SHA="$(printf '%s' "$VALUE" | sha256sum | cut -d' ' -f1)"

# Сеанс вчерашнего пересчёта: баннер, сумма, а потом сто с лишним строк отчёта,
# которые уводят её за край экрана. Увидеть её можно только в истории панели.
cat > "$SEED" <<EOF
#!/usr/bin/env bash
echo "=== пересчёт тарифов, запуск \$(date -u '+%Y-%m-%d %H:%M:%S') UTC ==="
for n in \$(seq 1 40); do echo "тариф \$n/40: пересчитан"; done
echo
echo "пересчёт завершён, контрольная сумма выгрузки: $VALUE"
echo
for n in \$(seq 1 140); do
  printf 'выгрузка: пакет %s/140 отправлен, подтверждение получено\n' "\$n"
done
echo "СЕАНС-ЗАВЕРШЁН"
EOF
chmod 700 "$SEED"

tmux new-session -d -s tariffs "bash $SEED; exec bash" 2>/dev/null
# Соседние сессии — тот самый мусор, который на живой машине накапливается
# годами. Нужная среди них одна, и по имени она не угадывается.
tmux new-session -d -s tariffs-old "echo '=== пересчёт тарифов (старая версия скрипта) ==='; echo 'ошибка: не найден /etc/tariffs.conf'; exec bash" 2>/dev/null
tmux new-session -d -s nightly "echo '=== ночные задачи ==='; for n in 1 2 3; do echo \"задача \$n: ок\"; done; exec bash" 2>/dev/null
tmux new-session -d -s tmp "echo 'что-то проверял, не помню что'; exec bash" 2>/dev/null

# Ждём, пока сеанс допечатает всё до последней строки: только после этого можно
# удалять скрипт — к этому моменту bash прочитал его целиком и заменился на себя.
SEEDED=""
for _ in $(seq 1 150); do
  if tmux capture-pane -p -S - -t tariffs 2>/dev/null | grep -q 'СЕАНС-ЗАВЕРШЁН'; then
    SEEDED=1; break
  fi
  sleep 0.2
done
rm -f "$SEED"
[ -n "$SEEDED" ] || { echo "Сеанс в tmux не отработал" >&2; exit 1; }

cat >> "$STATE" <<EOF
answer=$ANSWER
answer_sha256=$SHA
sessions=$(echo $SESSIONS | tr ' ' ,)
EOF
chmod 600 "$STATE"

echo "В tmux висят четыре отсоединённые сессии: tmux ls."
