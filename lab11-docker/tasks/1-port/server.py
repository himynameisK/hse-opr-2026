"""Справочная служба: отвечает на GET /. Код не менять."""
import argparse
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = "справочная служба: работает\n".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        print("запрос:", fmt % args, flush=True)


def main():
    p = argparse.ArgumentParser(description="справочная служба")
    p.add_argument("--bind", default="127.0.0.1", help="адрес, на котором слушать")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    srv = ThreadingHTTPServer((a.bind, a.port), Handler)
    print("слушаю {}:{}".format(a.bind, a.port), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
