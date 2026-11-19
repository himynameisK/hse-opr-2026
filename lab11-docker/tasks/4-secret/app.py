"""Сервис каталога. Код не менять.

При старте читает каталог, собранный prepare.py, и токен API_TOKEN
из окружения (или из файла /run/secrets/api_token). Без токена не стартует.
GET / → JSON: отпечаток каталога, отпечаток токена, число товаров.
"""
import hashlib
import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

with open("/app/catalog.json", encoding="utf-8") as f:
    CATALOG = json.load(f)

TOKEN = os.environ.get("API_TOKEN", "")
if not TOKEN and os.path.isfile("/run/secrets/api_token"):
    with open("/run/secrets/api_token", encoding="utf-8") as f:
        TOKEN = f.read().strip()
if not TOKEN:
    sys.exit("app.py: нет API_TOKEN — без него к хранилищу не обратиться")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "catalog": CATALOG["stamp"],
            "token": hashlib.sha256(("ключ:" + TOKEN).encode()).hexdigest()[:16],
            "items": len(CATALOG["items"]),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("запрос:", fmt % args, flush=True)


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print("каталог готов, слушаю 0.0.0.0:8000", flush=True)
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
