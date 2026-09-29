import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

DSN = os.environ['DATABASE_URL']
LOCK = threading.Lock()
STATE = {'version': 'v1', 'sequence': 0}
REQUESTS = Counter('shop_requests', 'Checkout attempts', ['release', 'status'])
DURATION = Histogram('shop_duration_seconds', 'Checkout latency', ['release'],
                     buckets=(.05, .1, .2, .5, 1, 2, 5))
ACTIVE = Gauge('shop_release', 'Active lab release: 1, 2 or 3')
ACTIVE.set(1)


def query(sql, values=(), fetch=False):
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, values)
            return cursor.fetchall() if fetch else None


def log(**fields):
    print(json.dumps({'timestamp': time.time(), **fields}), flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, payload):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/metrics':
            data = generate_latest()
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(data)
        elif self.path in ('/', '/health'):
            self.reply(200, {'status': 'up', 'release': STATE['version']})
        elif self.path == '/evidence':
            rows = query('''SELECT release, count(*),
                count(*) FILTER (WHERE http_status >= 500),
                count(*) FILTER (WHERE outcome = 'paid')
                FROM attempts WHERE NOT synthetic_history GROUP BY release ORDER BY release''', fetch=True)
            history = query('SELECT version FROM releases ORDER BY id', fetch=True)
            last = query('SELECT release, outcome FROM attempts WHERE NOT synthetic_history ORDER BY id DESC LIMIT 20', fetch=True)
            self.reply(200, {'active': STATE['version'], 'counts': rows,
                             'releases': [r[0] for r in history], 'last': last})
        else:
            self.reply(404, {'error': 'not_found'})

    def do_POST(self):
        if self.path.startswith('/release/'):
            version = self.path.rsplit('/', 1)[-1]
            if version not in ('v1', 'v2', 'v3'):
                return self.reply(400, {'error': 'unknown_release'})
            with LOCK:
                STATE.update(version=version, sequence=0)
                ACTIVE.set(int(version[-1]))
            query('INSERT INTO releases(version) VALUES (%s)', (version,))
            log(event='release_changed', release=version)
            return self.reply(200, {'release': version})
        if self.path != '/checkout':
            return self.reply(404, {'error': 'not_found'})
        with LOCK:
            version = STATE['version']
            STATE['sequence'] += 1
            sequence = STATE['sequence']
        started = time.monotonic()
        code, outcome, reason = 200, 'paid', 'ok'
        # Контролируемые дефекты. Сервис не обращается к внешним платёжным системам.
        if version == 'v2' and sequence % 4 == 0:
            time.sleep(1.2)
            code, outcome, reason = 503, 'failed', 'payment_pool_timeout'
        elif version == 'v3' and sequence % 4 != 0:
            time.sleep(.08)
            outcome, reason = 'declined', 'amount_limit_units_mismatch'
        else:
            time.sleep(.08)
        latency = time.monotonic() - started
        query('''INSERT INTO attempts(release,http_status,outcome,amount_kopecks,latency_ms)
                 VALUES (%s,%s,%s,%s,%s)''', (version, code, outcome, 150000, round(latency * 1000)))
        REQUESTS.labels(version, str(code)).inc()
        DURATION.labels(version).observe(latency)
        log(event='checkout', release=version, outcome=outcome, reason=reason,
            http_status=code, latency_ms=round(latency * 1000))
        self.reply(code, {'outcome': outcome, 'release': version})


if __name__ == '__main__':
    query('INSERT INTO releases(version) VALUES (%s)', ('v1',))
    log(event='started', release='v1')
    ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
