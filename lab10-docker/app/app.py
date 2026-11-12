"""Счётчик посещений. Код не править — упаковывать как есть.

    GET /        увеличивает счётчик в redis и печатает его
    GET /health  200, если redis отвечает на PING, иначе 503

Настройки — только из переменных окружения:
    HOST        на каком адресе слушать, по умолчанию 127.0.0.1
    PORT        на каком порту, по умолчанию 8000
    REDIS_HOST  где redis, по умолчанию localhost
    REDIS_PORT  его порт, по умолчанию 6379
"""
import os

import redis
from flask import Flask

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

app = Flask(__name__)
db = redis.Redis(
    host=os.environ.get("REDIS_HOST", "localhost"),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    socket_connect_timeout=1,
    socket_timeout=1,
)


@app.get("/")
def index():
    try:
        hits = db.incr("hits")
    except redis.RedisError as e:
        return "redis недоступен: {}\n".format(e), 503
    return "Посещений: {}\n".format(hits)


@app.get("/health")
def health():
    try:
        db.ping()
    except redis.RedisError as e:
        return "not ready: {}\n".format(e), 503
    return "ok\n"


if __name__ == "__main__":
    print("Слушаю http://{}:{}".format(HOST, PORT), flush=True)
    app.run(host=HOST, port=PORT)
