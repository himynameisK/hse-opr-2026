"""Витрина: GET / → спрашивает api по имени api:8000 и отдаёт его ответ. Код не менять."""
import signal
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API = "http://api:8000/"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with urllib.request.urlopen(API, timeout=3) as r:
                code, text = 200, "front → " + r.read().decode("utf-8")
        except Exception as e:
            code, text = 502, "front: api недоступен ({}): {}\n".format(API, e)
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print("front слушает 0.0.0.0:8000", flush=True)
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
