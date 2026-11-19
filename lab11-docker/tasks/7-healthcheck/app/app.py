"""Сервис заказов. Код не менять.

При старте один раз проверяет базу и, если она недоступна, завершается с кодом 1.
GET /health → 200 «ok», если база отвечает прямо сейчас, иначе 503.
Проверка базы — настоящий вход в PostgreSQL по протоколу (пользователь postgres).
"""
import os
import signal
import socket
import struct
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB_HOST = os.environ.get("DB_HOST", "db")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))


def db_ping():
    """None, если база приняла вход, иначе текст ошибки."""
    try:
        with socket.create_connection((DB_HOST, DB_PORT), timeout=3) as s:
            params = b"user\0postgres\0database\0postgres\0\0"
            s.sendall(struct.pack("!ii", 8 + len(params), 196608) + params)
            kind = s.recv(1)
            if kind == b"R":
                _, code = struct.unpack("!ii", s.recv(8))
                s.sendall(b"X\0\0\0\4")
                return None if code == 0 else "база просит пароль (код {})".format(code)
            if kind == b"E":
                data = s.recv(4096)
                for field in data[4:].split(b"\0"):
                    if field[:1] == b"M":
                        return field[1:].decode("utf-8", "replace")
                return "ошибка входа"
            return "непонятный ответ базы"
    except OSError as e:
        return str(e)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_error(404)
            return
        err = db_ping()
        body = ("ok\n" if err is None else "база недоступна: {}\n".format(err)).encode()
        self.send_response(200 if err is None else 503)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
err = db_ping()
if err is not None:
    print("не могу подключиться к базе {}:{}: {}".format(DB_HOST, DB_PORT, err), flush=True)
    sys.exit(1)
print("база на месте, слушаю 0.0.0.0:8000", flush=True)
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
