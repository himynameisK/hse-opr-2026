#!/usr/bin/env python3
"""Управление только локальным стендом lab12; Python standard library."""
import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def request(path, data=None):
    req = urllib.request.Request('http://127.0.0.1:18080' + path,
                                 data=b'' if data is not None else None)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['release', 'status', 'check', 'logs'])
    parser.add_argument('version', nargs='?', choices=['v1', 'v2', 'v3'])
    args = parser.parse_args()
    if args.command == 'release':
        if not args.version:
            parser.error('укажите v1, v2 или v3')
        print(request('/release/' + args.version, data=True))
    elif args.command == 'logs':
        subprocess.run(['docker', 'compose', 'logs', '--tail=40', 'shop'], cwd=ROOT, check=True)
    elif args.command == 'status':
        print(json.dumps(request('/evidence'), indent=2, ensure_ascii=False))
    else:
        evidence = request('/evidence')
        history = evidence['releases']
        observed = {r[0]: r for r in evidence['counts']}
        checks = [
            ('наблюдали минимум 20 попыток v2 и ошибки',
             'v2' in observed and observed['v2'][1] >= 20 and observed['v2'][2] > 0),
            ('после v2 вернулись к v1', 'v2' in history and 'v1' in history[history.index('v2')+1:] and evidence['active'] == 'v1'),
            ('последние 20 попыток успешны на v1', len(evidence['last']) == 20 and all(row == ['v1', 'paid'] for row in evidence['last']))]
        for label, ok in checks:
            print(('PASS: ' if ok else 'FAIL: ') + label)
        print('Преподаватель отдельно проверяет объяснение по графикам и логам.')
        if 'v3' in observed:
            print('Дополнение v3: paid / attempts =', observed['v3'][3], '/', observed['v3'][1])
        return 0 if all(ok for _, ok in checks) else 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Ошибка:', error, '\nПроверьте docker compose ps.', file=sys.stderr)
        sys.exit(1)
