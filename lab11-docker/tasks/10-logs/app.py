"""Приём заказов. Код не менять.

Журнал пишется в файл из переменной окружения LOG_FILE
(по умолчанию /var/log/shop/app.log). В stdout сервис ничего не печатает.
GET /order?id=N → «заказ N принят», и строка в журнале.
"""
import os
import signal
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG_FILE = os.environ.get("LOG_FILE", "/var/log/shop/app.log")
log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")


def journal(msg):
    log.write("{} {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), msg))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        order = urllib.parse.parse_qs(url.query).get("id", ["?"])[0]
        if url.path != "/order":
            self.send_error(404)
            return
        journal("заказ {} принят".format(order))
        body = "заказ {} принят\n".format(order).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        journal("http " + fmt % args)


def stop(*_):
    journal("остановка по сигналу")
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
journal("старт, слушаю 0.0.0.0:8000")
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
