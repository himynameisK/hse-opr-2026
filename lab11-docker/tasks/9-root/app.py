"""Счётчик посещений. Код не менять.

Каждое посещение дописывает строку в /app/data/visits.log.
GET / → «посещений: N». При старте пишет в тот же файл строку «старт».
"""
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = "/app/data/visits.log"


def append(line):
    with open(DATA, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    with open(DATA, encoding="utf-8") as f:
        return sum(1 for s in f if s.startswith("посещение"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            code, text = 200, "посещений: {}\n".format(append("посещение " + self.path))
        except OSError as e:
            code, text = 500, "не могу записать {}: {}\n".format(DATA, e)
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
append("старт uid={}".format(os.getuid()))
print("uid={}, данные в {}, слушаю 0.0.0.0:8000".format(os.getuid(), DATA), flush=True)
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
