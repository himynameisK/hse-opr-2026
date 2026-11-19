"""Шаг сборки: «скачивает» каталог товаров из закрытого хранилища по токену. Код не менять.

Токен берётся из переменной окружения API_TOKEN, а если её нет —
из файла /run/secrets/api_token. Сам токен в каталог не попадает,
только отпечаток, по которому видно, с каким токеном скачивали.
"""
import hashlib
import json
import os
import sys

token = os.environ.get("API_TOKEN", "")
if not token and os.path.isfile("/run/secrets/api_token"):
    with open("/run/secrets/api_token", encoding="utf-8") as f:
        token = f.read().strip()
if not token:
    sys.exit("prepare.py: нет токена — хранилище не отдаёт каталог")

catalog = {
    "stamp": hashlib.sha256(("каталог:" + token).encode()).hexdigest()[:16],
    "items": ["тетрадь", "ручка", "линейка"],
}
with open("/app/catalog.json", "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False)
print("prepare.py: каталог скачан, товаров:", len(catalog["items"]))
