#!/usr/bin/env bash
# Занятие 10: разложить мусор, который не должен попасть в образ. Вызывают setup.sh и reset.sh.
# Кладёт только то, чего нет: .env, venv/, __pycache__/, debug.log на 8 МБ.
# То же самое делает check.py, если мусор удалили, — содержимое должно совпадать.
set -euo pipefail
D="$1"
TOKEN="opr-fake-token-7f3c9a1e2b4d5a6c"

[ -f "$D/.env" ] || printf '%s\n' \
  "# Локальные настройки. В git и в образ не попадает." \
  "# Токен ненастоящий, но обращаться с ним надо как с настоящим." \
  "API_TOKEN=$TOKEN" > "$D/.env"

if [ ! -f "$D/venv/pyvenv.cfg" ]; then
  mkdir -p "$D/venv/bin"
  printf 'home = /usr/bin\nversion = 3.12.0\n' > "$D/venv/pyvenv.cfg"
  printf '# заглушка виртуального окружения\n' > "$D/venv/bin/activate"
fi

if ! ls "$D/__pycache__/"*.pyc >/dev/null 2>&1; then
  mkdir -p "$D/__pycache__"
  head -c 1024 /dev/zero > "$D/__pycache__/app.cpython-312.pyc"
fi

if [ ! -f "$D/debug.log" ] || [ "$(wc -c < "$D/debug.log")" -lt 1048576 ]; then
  # yes бесконечен; head закрывает трубу на 8 МБ — yes получает SIGPIPE, это не ошибка
  ( yes "2026-11-05 19:00:00 DEBUG redis: GET hits -> ok, token=$TOKEN" || true ) \
    | head -c 8388608 > "$D/debug.log"
fi
