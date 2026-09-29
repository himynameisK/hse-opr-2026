#!/usr/bin/env python3
"""Повторяемая настройка локального Metabase через API закреплённой версии."""
import json
import time
import urllib.error
import urllib.request

URL = 'http://127.0.0.1:13001'
EMAIL = 'teacher@example.org'
PASSWORD = 'Lab12-local-only!'
SESSION = None


def api(method, path, payload=None):
    headers = {'Content-Type': 'application/json'}
    if SESSION:
        headers['X-Metabase-Session'] = SESSION
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(URL + '/api' + path, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f'{method} {path}: {error.code} {error.read().decode()}') from error


def main():
    global SESSION
    for attempt in range(180):
        try:
            if api('GET', '/health').get('status') == 'ok':
                break
        except Exception:
            if attempt % 10 == 0:
                print('Ожидаю Metabase...', flush=True)
        time.sleep(2)
    else:
        raise RuntimeError('Metabase не готов: docker compose logs metabase')
    token = api('GET', '/session/properties').get('setup-token')
    if token:
        api('POST', '/setup', {'token': token, 'user': {'email': EMAIL, 'password': PASSWORD,
            'first_name': 'Course', 'last_name': 'Teacher'},
            'prefs': {'site_name': 'ОПР: учебный магазин', 'site_locale': 'ru', 'allow_tracking': False}})
    SESSION = api('POST', '/session', {'username': EMAIL, 'password': PASSWORD})['id']
    databases = api('GET', '/database')['data']
    database = next((d for d in databases if d['name'] == 'Учебный магазин'), None)
    if database is None:
        database = api('POST', '/database', {'name': 'Учебный магазин', 'engine': 'postgres',
            'details': {'host': 'db', 'port': 5432, 'dbname': 'shop', 'user': 'dashboard',
                        'password': 'dashboard-read-only', 'ssl': False}, 'is_full_sync': True})
    dashboards = api('GET', '/dashboard')
    existing = next((d for d in dashboards if d['name'] == 'Магазин: оплаты и выручка'), None)
    if existing:
        print(f"Готово: {URL}/dashboard/{existing['id']} (повторная настройка не нужна)")
        return
    cards = [
      ('Оплаченные за последние 5 минут', 'scalar', "SELECT count(*) AS paid FROM attempts WHERE outcome='paid' AND created_at >= now()-interval '5 minutes'", {}),
      ('Доля оплат за 5 минут, %', 'scalar', "SELECT round(100.0*count(*) FILTER(WHERE outcome='paid')/NULLIF(count(*),0),1) AS paid_pct FROM attempts WHERE created_at>=now()-interval '5 minutes'", {}),
      ('Выручка за 5 минут, руб.', 'scalar', "SELECT coalesce(sum(amount_kopecks) FILTER(WHERE outcome='paid'),0)/100.0 AS revenue FROM attempts WHERE created_at>=now()-interval '5 minutes'", {}),
      ('Оплаты по минутам: график', 'line', "SELECT date_trunc('minute',created_at) AS minute, count(*) FILTER(WHERE outcome='paid') AS paid, count(*) AS attempts FROM attempts WHERE created_at>=now()-interval '30 minutes' GROUP BY 1 ORDER BY 1", {'graph.dimensions':['minute'], 'graph.metrics':['paid','attempts']}),
      ('Выручка по минутам, руб.', 'line', "SELECT date_trunc('minute',created_at) AS minute, coalesce(sum(amount_kopecks) FILTER(WHERE outcome='paid'),0)/100.0 AS revenue FROM attempts WHERE created_at>=now()-interval '30 minutes' GROUP BY 1 ORDER BY 1", {'graph.dimensions':['minute'], 'graph.metrics':['revenue']}),
      ('По версиям за 5 минут', 'table', "SELECT release, count(*) AS attempts, count(*) FILTER(WHERE http_status>=500) AS http_errors, count(*) FILTER(WHERE outcome='paid') AS paid, round(100.0*count(*) FILTER(WHERE outcome='paid')/count(*),1) AS paid_pct FROM attempts WHERE created_at>=now()-interval '5 minutes' GROUP BY release ORDER BY release", {})]
    dashboard = api('POST', '/dashboard', {'name':'Магазин: оплаты и выручка',
         'description':'Синтетический магазин. До запуска есть 15 минут помеченной фоновой истории. Денег и внешних платежей нет. Обновите дашборд после переключения релиза.'})
    positions = [(0,0,8,4),(0,8,8,4),(0,16,8,4),(4,0,12,8),(4,12,12,8),(12,0,24,6)]
    dashcards = []
    for index, (name, display, sql, settings) in enumerate(cards):
        card = api('POST','/card',{'name':name,'display':display,'visualization_settings':settings,
                   'dataset_query':{'database':database['id'],'type':'native','native':{'query':sql}}})
        row,col,width,height = positions[index]
        dashcards.append({'id':-(index+1),'card_id':card['id'],'row':row,'col':col,
                          'size_x':width,'size_y':height,'parameter_mappings':[],'visualization_settings':{}})
    api('PUT',f"/dashboard/{dashboard['id']}",{'dashcards':dashcards})
    print(f"Готово: {URL}/dashboard/{dashboard['id']}")
    print(f'Вход: {EMAIL} / {PASSWORD}')


if __name__ == '__main__':
    main()
