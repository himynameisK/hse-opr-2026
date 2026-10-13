#!/usr/bin/env bash
# Занятие 5, заявка 4. Поднимает «API» внутри сессии tmux — так, как его поднял
# бы человек руками. Юнита у него нет, автозапуска нет, перезагрузки он не переживёт.
[ -n "${BASH_VERSION:-}" ] || { echo "Запускать через bash, не sh: sudo bash $0" >&2; exit 1; }
set -euo pipefail

LAB="${1:-/opt/opr-lab05}"
API=/usr/local/sbin/opr-api
STATE_DIR=/var/lib/opr-lab05
STATE="$STATE_DIR/state"
PORT=8080
SESSION=api

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
command -v tmux >/dev/null || {
  echo "Не найден tmux: apt-get update && apt-get install -y tmux" >&2; exit 1; }
PY="$(command -v python3 || command -v python)" || { echo "Нужен python3" >&2; exit 1; }
mkdir -p "$STATE_DIR"

# Прошлый экземпляр убираем вместе с его сессией: два процесса на один порт
# не встанут, и заявка не развернётся.
tmux kill-session -t "$SESSION" 2>/dev/null || true
if command -v systemctl >/dev/null && [ -d /run/systemd/system ]; then
  systemctl stop opr-api 2>/dev/null || true
  systemctl disable opr-api 2>/dev/null || true
  rm -f /etc/systemd/system/opr-api.service
  systemctl daemon-reload 2>/dev/null || true
fi
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
for pid in $(pids_of "$API"); do
  kill -9 "$pid" 2>/dev/null || true
done
sleep 0.5

cat > "$API" <<EOF
#!$PY
"""Учебное API. Слушает порт $PORT и пишет обращения на свой stdout."""
import http.server
import socketserver

PORT = $PORT


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"opr-api: on"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("opr-api " + fmt % args, flush=True)


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as server:
    print(f"opr-api: слушаю 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
EOF
chmod 755 "$API"

# Так его и поднял человек: зашёл по ssh, открыл tmux, запустил руками.
# В истории панели остались его команды — по ним заявка и разбирается.
tmux new-session -d -s "$SESSION" \
  "echo '# поднимаю API, пока не дошли руки сделать нормально'; echo '\$ $API'; $API; exec bash" 2>/dev/null

UP=""
for _ in $(seq 1 100); do
  "$PY" - <<'PROBE' >/dev/null 2>&1 && { UP=1; break; }
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8080/", timeout=1).read()
PROBE
  sleep 0.2
done
[ -n "$UP" ] || { echo "API в tmux не поднялось" >&2; exit 1; }

cat >> "$STATE" <<EOF
api=$API
api_port=$PORT
api_session=$SESSION
EOF
chmod 600 "$STATE"

echo "API отвечает на порту $PORT, но живёт внутри сессии tmux $SESSION."
