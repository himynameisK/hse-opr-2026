#!/bin/sh
# Готовит каталог очереди и запускает обработчик.
set -e
mkdir -p "${QUEUE_DIR:-/tmp/queue}"
echo "entrypoint: очередь в ${QUEUE_DIR:-/tmp/queue}, запускаю обработчик"
python3 /app/app.py
