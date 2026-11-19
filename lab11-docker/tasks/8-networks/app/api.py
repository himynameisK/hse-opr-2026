"""API: GET / → отправляет PING в базу по имени db:6379 и отдаёт ответ. Код не менять."""
import signal
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = ("db", 6379)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with socket.create_connection(DB, timeout=3) as s:
                s.sendall(b"PING\r\n")
                reply = s.recv(64).decode().strip().lstrip("+")
            code, text = 200, "api → db: {}\n".format(reply)
        except Exception as e:
            code, text = 502, "api: база недоступна ({}:{}): {}\n".format(DB[0], DB[1], e)
        body = text.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
print("api слушает 0.0.0.0:8000", flush=True)
ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
