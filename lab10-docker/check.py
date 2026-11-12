#!/usr/bin/env python3
"""Занятие 10: проверка Dockerfile, .dockerignore, compose.yaml и CI.

    python3 check.py         все задачи
    python3 check.py 3       только задача 3; можно несколько номеров: 3 4
    На Windows: python check.py или py check.py

Нужен запущенный Docker (Docker Desktop или docker engine) с docker compose v2.
Проверка всё делает по-настоящему: собирает образ, запускает контейнер,
поднимает compose. Порты берёт свободные, имя проекта compose — своё на каждый
прогон, и всё, что подняла, убирает за собой: контейнеры, тома, сети, образы.
Ваши compose-проекты и образы не трогает.

Python 3.8+, только стандартная библиотека.
"""

LAB = "Занятие 10"

TITLES = {
    1: "Образ собирается и отвечает с хоста",
    2: "В образ не попадает мусор",
    3: "compose: app + redis, счётчик считает",
    4: "Данные переживают down и up",
    5: "CI собирает образ на каждый push",
    6: "Плюсом: healthcheck и порядок запуска",
}

# Мусор, который лежит в каталоге и не должен попасть ни в контекст сборки, ни в образ.
GARBAGE = [".env", "venv", "__pycache__", "debug.log"]
SECRET = "opr-fake-token-7f3c9a1e2b4d5a6c"
ENV_TEXT = ("# Локальные настройки. В git и в образ не попадает.\n"
            "# Токен ненастоящий, но обращаться с ним надо как с настоящим.\n"
            "API_TOKEN={}\n".format(SECRET))

BUILD_LIMIT = 600       # с: первая сборка с pip может идти минуты
UP_LIMIT = 600          # с: compose up --build, плюс скачать redis
HEALTH_WAIT = 60        # с: сколько ждать ответа /health
HEALTHY_WAIT = 120      # с: сколько ждать статуса healthy (задача 6)
STOP_TIMEOUT = "5"      # с: docker compose down -t
SHOW = 3                # сколько деталей показывать под FAIL
LABEL = "opr-lab10-check"
PREFIX = "opr-lab10-check-"

import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
RUN_ID = uuid.uuid4().hex[:8]
DOCKER = shutil.which("docker") or "docker"
CLEANUP = []            # что убрать в конце, функции; выполняются в обратном порядке


class Fail(Exception):
    """Задача не прошла. details — строки «что ждали / что получили»."""

    def __init__(self, *details):
        super().__init__(details[0] if details else "")
        self.details = [d for d in details if d]


class Missing(Exception):
    """Нет нужного файла — задача не начата."""


# ─── запуск команд ────────────────────────────────────────────────────────

def child_env():
    env = dict(os.environ)
    # Свои compose-файлы мы передаём явно; чужие переменные не должны их подменять.
    for var in ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PATH_SEPARATOR"):
        env.pop(var, None)
    env.setdefault("DOCKER_BUILDKIT", "1")
    env["DOCKER_CLI_HINTS"] = "false"
    return env


ENV = child_env()


def sh(args, timeout=60, cwd=None, env=None):
    """→ (код возврата, stdout+stderr). Код None — не уложилось в timeout."""
    try:
        p = subprocess.run([DOCKER] + list(args), cwd=str(cwd or HERE), env=env or ENV,
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        out = e.output or b""
        return None, out.decode("utf-8", "replace")
    except OSError as e:
        return 127, str(e)
    return p.returncode, p.stdout.decode("utf-8", "replace")


def quiet(args, timeout=60):
    """Команда уборки: результат не важен, ошибки не показываем."""
    try:
        subprocess.run([DOCKER] + list(args), env=ENV, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        pass


def tail(text, n=3, width=150):
    """Последние n значимых строк вывода — обычно там причина ошибки."""
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line or set(line) <= set("-=#.─ "):
            continue
        if re.match(r"^#\d+ (\[internal\]|DONE|CACHED|sha256:)", line):
            continue
        lines.append(line if len(line) <= width else line[:width] + "…")
    return lines[-n:]


def say(text=""):
    print(text, flush=True)


def note(text):
    """Что сейчас происходит — чтобы долгие шаги не выглядели зависанием."""
    print("  … " + text, flush=True)


# ─── HTTP с хоста ─────────────────────────────────────────────────────────

def http_get(port, path, timeout=3):
    """→ (код, тело) или (None, текст ошибки). Без прокси: идём прямо на 127.0.0.1."""
    conn = http.client.HTTPConnection("127.0.0.1", int(port), timeout=timeout)
    try:
        conn.request("GET", path, headers={"Connection": "close"})
        r = conn.getresponse()
        return r.status, r.read(4096).decode("utf-8", "replace").strip()
    except (OSError, http.client.HTTPException) as e:
        return None, (type(e).__name__ + ": " + str(e)).strip(": ")
    finally:
        conn.close()


def wait_http(port, path, want, limit, alive=None, stuck=None):
    """Ждём, пока GET path вернёт один из кодов want. → (код, тело), последний ответ.

    alive() — «есть смысл ждать?»: контейнер упал или слушает не тот адрес — ждать нечего.
    stuck — сколько секунд подряд терпеть один и тот же неверный HTTP-код: приложение
    отвечает, но 503 не проходит — значит, оно не видит redis и само не увидит.
    """
    end = time.monotonic() + limit
    last = (None, "ни одного ответа")
    since = None
    while True:
        prev, last = last, http_get(port, path)
        if last[0] in want:
            return last
        if last[0] is None or last[0] != prev[0]:
            since = time.monotonic()
        elif stuck is not None and time.monotonic() - since > stuck:
            return last
        if alive is not None and not alive():
            return last
        if time.monotonic() > end:
            return last
        time.sleep(0.5)


def short(text, width=100):
    text = " ".join(str(text).split())
    return "«" + (text if len(text) <= width else text[:width] + "…") + "»"


# ─── Docker в целом ───────────────────────────────────────────────────────

def compose_version():
    code, out = sh(["compose", "version", "--short"], timeout=30)
    if code != 0:
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def preflight():
    """Docker есть и запущен, compose v2 есть. Иначе — понятное сообщение и выход."""
    if not shutil.which("docker"):
        say("Не найдена команда docker. Поставьте Docker Desktop (macOS, Windows)")
        say("или docker engine (Linux) и откройте новый терминал.")
        return None
    code, out = sh(["info", "--format", "{{.ServerVersion}}"], timeout=30)
    if "permission denied" in out.lower():
        say("Нет прав на docker: добавьте себя в группу docker (Linux) и перелогиньтесь:")
        say("  sudo usermod -aG docker $USER")
        return None
    if code != 0 or not out.strip() or "error" in out.lower():
        say("Docker не отвечает: команда docker есть, а демон не запущен.")
        for line in tail(out, 2):
            say("  " + line)
        say("Запустите Docker Desktop (или: sudo systemctl start docker) и подождите,")
        say("пока docker info не перестанет ругаться. Потом повторите проверку.")
        return None
    ver = compose_version()
    if ver is None:
        say("Не найден docker compose (v2). Он идёт в составе Docker Desktop;")
        say("в Linux — пакет docker-compose-plugin. Старый docker-compose v1 не подходит.")
        return None
    return ver


def sweep_leftovers():
    """Убрать то, что оставили прошлые прогоны, прерванные на полпути (kill -9, закрыли окно)."""
    code, out = sh(["ps", "-aq", "--filter", "label=" + LABEL], timeout=30)
    ids = out.split() if code == 0 else []
    code, out = sh(["ps", "-a", "--filter", "label=com.docker.compose.project",
                    "--format", '{{.Label "com.docker.compose.project"}}'], timeout=30)
    projects = sorted({p for p in out.split() if p.startswith(PREFIX)}) if code == 0 else []
    for p in projects:
        sweep_project(p)
    if ids:
        quiet(["rm", "-f", "-v"] + ids)
    code, out = sh(["images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30)
    for img in (out.split() if code == 0 else []):
        if img.startswith(PREFIX) or img.startswith("opr-lab10-check:"):
            quiet(["rmi", "-f", img])


def sweep_project(project):
    """Удалить всё с меткой compose-проекта: контейнеры, тома, сети, собранные образы."""
    flt = "label=com.docker.compose.project=" + project
    code, out = sh(["ps", "-aq", "--filter", flt], timeout=30)
    if code == 0 and out.split():
        quiet(["rm", "-f", "-v"] + out.split())
    code, out = sh(["volume", "ls", "-q", "--filter", flt], timeout=30)
    if code == 0 and out.split():
        quiet(["volume", "rm", "-f"] + out.split())
    code, out = sh(["network", "ls", "-q", "--filter", flt], timeout=30)
    if code == 0 and out.split():
        quiet(["network", "rm"] + out.split())
    code, out = sh(["images", "--format", "{{.Repository}}:{{.Tag}}"], timeout=30)
    for img in (out.split() if code == 0 else []):
        if img.startswith(project + "-"):
            quiet(["rmi", "-f", img])


# ─── файлы студента ───────────────────────────────────────────────────────

def ensure_garbage():
    """Мусор должен лежать на месте: задача — не пустить его в образ, а не удалить.

    Если его удалили, кладём обратно (содержимое то же, что делает setup.sh).
    """
    back = []
    if not (HERE / ".env").is_file():
        (HERE / ".env").write_text(ENV_TEXT, encoding="utf-8")
        back.append(".env")
    v = HERE / "venv"
    if not (v / "pyvenv.cfg").is_file():
        (v / "bin").mkdir(parents=True, exist_ok=True)
        (v / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.12.0\n", encoding="utf-8")
        (v / "bin" / "activate").write_text("# заглушка виртуального окружения\n",
                                            encoding="utf-8")
        back.append("venv/")
    pc = HERE / "__pycache__"
    if not any(pc.glob("*.pyc")):
        pc.mkdir(exist_ok=True)
        (pc / "app.cpython-312.pyc").write_bytes(b"\xcb\r\r\n" + b"\0" * 1020)
        back.append("__pycache__/")
    log = HERE / "debug.log"
    if not log.is_file() or log.stat().st_size < (1 << 20):
        line = "2026-11-05 19:00:00 DEBUG redis: GET hits -> ok, token={}\n".format(SECRET)
        with log.open("w", encoding="utf-8") as f:
            f.write(line * ((8 << 20) // len(line)))
        back.append("debug.log")
    return back


def compose_file():
    for name in ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml"):
        if (HERE / name).is_file():
            return HERE / name
    return None


def workflows():
    d = HERE / ".github" / "workflows"
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix in (".yml", ".yaml"))


# ─── образ: собрать один раз на прогон ────────────────────────────────────

IMAGE = {"tag": None, "error": None}


def build_image():
    """docker build . — ровно как просит контракт. → тег образа или Fail."""
    if IMAGE["tag"]:
        return IMAGE["tag"]
    if IMAGE["error"]:
        raise Fail(*IMAGE["error"])
    if not (HERE / "Dockerfile").is_file():
        raise Missing("Dockerfile")
    tag = "opr-lab10-check:" + RUN_ID
    note("собираю образ: docker build . (первый раз с pip — до пары минут)")
    t0 = time.monotonic()
    code, out = sh(["build", "--progress=plain", "-t", tag, "."], timeout=BUILD_LIMIT)
    if code == 0:
        CLEANUP.append(lambda: quiet(["rmi", "-f", tag]))
        IMAGE["tag"] = tag
        note("образ собран за {:.0f} с".format(time.monotonic() - t0))
        return tag
    if code is None:
        IMAGE["error"] = ["docker build . не уложился в {} с".format(BUILD_LIMIT),
                          "проверьте интернет: pip качает пакеты при сборке"]
    else:
        IMAGE["error"] = ["ждали: docker build . завершится с кодом 0",
                          "получили: код {}. {}".format(code, build_reason(out))]
    raise Fail(*IMAGE["error"])


def build_reason(out):
    """Причина падения docker build одной строкой.

    Под FAIL помещается SHOW строк, поэтому причину ищем, а не берём хвост целиком.
    Итоговая строка ERROR у BuildKit обычно говорит «команда упала с кодом 1»,
    а настоящая причина (ошибка pip, опечатка в команде) стоит выше, в выводе шага.
    """
    lines = tail(out, 80, width=400)
    errors = [re.sub(r"^(#\d+ )?(\d+\.\d+ )?(ERROR: )?(failed to build: )?(failed to solve: )?",
                     "", l)
              for l in lines if re.search(r"error|not found|no such file", l, re.I)]
    if not errors:
        return "последние строки: " + short(" | ".join(lines[-2:]), 220)
    final = errors[-1]
    if "did not complete successfully" in final and len(errors) > 1:
        return short(errors[-2], 160) + " → " + short(final, 120)
    return short(final, 220)


def image_config(tag):
    code, out = sh(["image", "inspect", tag], timeout=30)
    if code != 0:
        return {}
    try:
        return (json.loads(out)[0] or {})
    except (ValueError, IndexError):
        return {}


def container_port(cfg):
    """Порт приложения внутри контейнера: единственный EXPOSE, иначе PORT из ENV, иначе 8000."""
    c = cfg.get("Config") or {}
    exposed = [k.split("/")[0] for k in (c.get("ExposedPorts") or {}) if k.endswith("/tcp")]
    if len(exposed) == 1 and exposed[0].isdigit():
        return int(exposed[0])
    for kv in c.get("Env") or []:
        if kv.startswith("PORT=") and kv[5:].isdigit():
            return int(kv[5:])
    return 8000


def listens_on_localhost(logs):
    """По логу: приложение слушает только 127.0.0.1? app.py пишет «Слушаю http://…».

    Werkzeug на 0.0.0.0 печатает и «Running on all addresses», и http://127.0.0.1 —
    поэтому «Running on» считаем, только если ВСЕ адреса там локальные.
    """
    if re.search(r"Слушаю http://(127\.0\.0\.1|localhost)[:/]", logs):
        return True
    runs = re.findall(r"Running on (?:http://)?(\S+)", logs)
    return bool(runs) and all(r.startswith(("127.0.0.1", "localhost")) for r in runs)


def wrong_port(logs, port):
    """Приложение пишет «Слушаю http://адрес:порт». → его порт, если он не тот, что опубликован."""
    m = re.findall(r"Слушаю http://\S+?:(\d+)", logs)
    return int(m[-1]) if m and int(m[-1]) != port else None


HINT_HOST = ("подсказка: внутри контейнера приложение слушает 127.0.0.1 — это «только изнутри "
             "контейнера». Нужен 0.0.0.0: переменная HOST в Dockerfile (ENV) или в CMD")


# ─── задача 1 ─────────────────────────────────────────────────────────────

def task1():
    tag = build_image()
    port = container_port(image_config(tag))
    name = "opr-lab10-check-{}-t1".format(RUN_ID)
    CLEANUP.append(lambda: quiet(["rm", "-f", "-v", name]))
    code, out = sh(["run", "-d", "--name", name, "--label", LABEL,
                    "-p", "127.0.0.1::{}".format(port), tag], timeout=60)
    if code != 0:
        raise Fail("ждали: docker run -d -p … запустит контейнер",
                   "получили: " + " / ".join(tail(out, 2)))
    try:
        host_port = published(name, port)
        if host_port is None:
            raise Fail("docker port не показал опубликованный порт {}".format(port))

        def running():
            c, o = sh(["inspect", "-f", "{{.State.Running}}", name], timeout=20)
            return c == 0 and o.strip() == "true"

        def alive():
            logs = sh(["logs", name], timeout=20)[1]
            return running() and not listens_on_localhost(logs) and not wrong_port(logs, port)

        note("контейнер без redis запущен, жду ответа /health с хоста")
        status, body = wait_http(host_port, "/health", (200, 503), 20, alive)
        _, logs = sh(["logs", name], timeout=20)
        if status in (200, 503):
            return "контейнер ответил с хоста: /health → {} (redis нет — так и должно быть)".format(
                status)
        if not running():
            c, o = sh(["inspect", "-f", "{{.State.ExitCode}}", name], timeout=20)
            raise Fail("ждали: контейнер работает и отвечает на /health",
                       "получили: контейнер завершился, код {}; конец лога: {}".format(
                           o.strip() or "?", short(" | ".join(tail(logs, 3)))),
                       "проверьте CMD: docker run --rm -it ОБРАЗ — и смотрите, что он пишет")
        details = ["ждали: GET http://127.0.0.1:{}/health → 503 (redis в этом тесте нет)".format(
                       host_port),
                   "получили: {}".format(status if status else body)]
        if listens_on_localhost(logs):
            details.append(HINT_HOST)
        elif wrong_port(logs, port):
            details.append("EXPOSE {}, а приложение слушает {}: порт берётся из PORT".format(
                port, wrong_port(logs, port)))
        elif status is not None:
            details.append("это ответ не нашего приложения? конец лога: " + short(
                " | ".join(tail(logs, 2))))
        else:
            details.append("приложение в контейнере на порту {}? EXPOSE и PORT должны "
                           "совпадать; лог: {}".format(port, short(" | ".join(tail(logs, 2)))))
        raise Fail(*details)
    finally:
        quiet(["rm", "-f", "-v", name])


def published(container, port):
    """Хост-порт, на который docker опубликовал port контейнера."""
    for _ in range(20):
        code, out = sh(["port", container, "{}/tcp".format(port)], timeout=20)
        for line in out.splitlines():
            m = re.search(r":(\d+)\s*$", line.strip())
            if code == 0 and m:
                return int(m.group(1))
        time.sleep(0.3)
    return None


# ─── задача 2 ─────────────────────────────────────────────────────────────

def task2():
    if not (HERE / "Dockerfile").is_file():
        raise Missing("Dockerfile")
    back = ensure_garbage()
    if back:
        say("  замечание: вернул удалённый мусор ({}). Задача — не удалить его, "
            "а не пустить в образ".format(", ".join(back)))
    if not (HERE / ".dockerignore").is_file():
        raise Fail("ждали: файл .dockerignore рядом с Dockerfile",
                   "получили: его нет — весь каталог уходит демону как контекст сборки: "
                   ".env с токеном, venv/, debug.log на 8 МБ")
    # 1) Что уходит демону: собираем «образ» FROM scratch с COPY . / и выгружаем его в каталог.
    #    Это и есть контекст сборки после .dockerignore, файл в файл.
    tmp = Path(tempfile.mkdtemp(prefix="opr-lab10-"))
    CLEANUP.append(lambda: shutil.rmtree(str(tmp), ignore_errors=True))
    probe = tmp / "probe.Dockerfile"
    probe.write_text("FROM scratch\nCOPY . /\n", encoding="utf-8")
    out_dir = tmp / "context"
    note("смотрю, что уходит в контекст сборки после .dockerignore")
    code, out = sh(["build", "-q", "-f", str(probe), "-o", "type=local,dest=" + str(out_dir), "."],
                   timeout=180)
    if code != 0:
        raise Fail("не получилось выгрузить контекст сборки (нужен BuildKit, он включён "
                   "в Docker Desktop и docker 23+)", "вывод: " + short(" | ".join(tail(out, 2))))
    leaked = [g for g in GARBAGE if (out_dir / g).exists()]
    size = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    shutil.rmtree(str(out_dir), ignore_errors=True)
    if leaked:
        raise Fail("ждали: в контексте сборки нет {}".format(", ".join(GARBAGE)),
                   "получили: в контекст попали {} — всего {:.1f} МБ".format(
                       ", ".join(leaked), size / 1e6),
                   "подсказка: строки в .dockerignore — пути от корня контекста: venv/, .env …")
    # 2) Что в самом образе: docker create + docker export — файловая система как есть.
    tag = build_image()
    found = scan_image(tag)
    if found["app_dirs"] is None:
        raise Fail("в образе не нашёл app.py — тот самый, что лежит рядом с check.py",
                   "приложение надо положить в образ целиком: COPY . . после WORKDIR")
    if found["junk"]:
        raise Fail("ждали: в образе нет {}".format(", ".join(GARBAGE)),
                   "получили: " + ", ".join("/" + j for j in found["junk"][:5]))
    mb = (image_config(tag).get("Size") or 0) / 1e6
    msg = "контекст {:.0f} КБ, приложение в {}, мусора нет; образ {:.0f} МБ".format(
        size / 1e3, ", ".join("/" + d if d else "/" for d in found["app_dirs"]), mb)
    if mb > 600:
        msg += " — многовато: возьмите python:3.12-slim вместо python:3.12"
    return msg


def scan_image(tag):
    """Пройти файловую систему образа. → {"app_dirs": [...] | None, "junk": [...]}."""
    want = (HERE / "app.py").read_bytes() if (HERE / "app.py").is_file() else None
    code, cid = sh(["create", "--label", LABEL, tag], timeout=60)
    cid = cid.strip().splitlines()[-1] if code == 0 and cid.strip() else ""
    if not cid:
        raise Fail("docker create не создал контейнер из образа", short(cid))
    CLEANUP.append(lambda: quiet(["rm", "-f", "-v", cid]))
    names, app_dirs = set(), []
    try:
        p = subprocess.Popen([DOCKER, "export", cid], env=ENV, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            with tarfile.open(fileobj=p.stdout, mode="r|") as tar:
                for m in tar:
                    n = m.name.lstrip("./").rstrip("/")
                    names.add(n)
                    if m.isfile() and n.rsplit("/", 1)[-1] == "app.py" and want is not None:
                        f = tar.extractfile(m)
                        if f is not None and f.read() == want:
                            app_dirs.append(n.rsplit("/", 1)[0] if "/" in n else "")
        finally:
            p.stdout.close()
            p.wait(timeout=60)
    finally:
        quiet(["rm", "-f", "-v", cid])
    junk = []
    for d in app_dirs:
        for g in GARBAGE:
            path = (d + "/" + g) if d else g
            if path in names:
                junk.append(path + ("/" if g in ("venv", "__pycache__") else ""))
    for n in sorted(names):      # .env и debug.log не должно быть нигде
        base = n.rsplit("/", 1)[-1]
        if base in (".env", "debug.log") and n not in junk:
            junk.append(n)
    return {"app_dirs": app_dirs or None, "junk": junk}


# ─── compose ──────────────────────────────────────────────────────────────

COMPOSE = {"version": None}


class Project:
    """Свой compose-проект на задачу: своё имя, свои тома, свой случайный порт."""

    def __init__(self, suffix):
        self.file = compose_file()
        if self.file is None:
            raise Missing("compose.yaml")
        self.name = "{}{}-{}".format(PREFIX, RUN_ID, suffix)
        self.env = dict(ENV)
        self.env["COMPOSE_PROJECT_NAME"] = self.name
        self.files = ["-f", str(self.file)]
        self.override = None
        self.cport = None
        self.started = False
        self.volumes = set()    # все тома, что видели у контейнеров проекта, включая безымянные

    def run(self, args, timeout=120):
        return sh(["compose", "-p", self.name] + self.files + list(args),
                  timeout=timeout, env=self.env)

    def config(self):
        code, out = self.run(["config", "--format", "json"], timeout=60)
        if code != 0:
            raise Fail("ждали: docker compose config разберёт {}".format(self.file.name),
                       "получили: " + short(" | ".join(tail(out, 2)), 160))
        try:
            return json.loads(out[out.index("{"):])
        except ValueError:
            raise Fail("docker compose config выдал не JSON: " + short(out))

    def services(self):
        cfg = self.config()
        svc = cfg.get("services") or {}
        missing = [s for s in ("app", "redis") if s not in svc]
        if missing:
            raise Fail("ждали: сервисы app и redis в {}".format(self.file.name),
                       "получили: {}".format(", ".join(sorted(svc)) or "сервисов нет"),
                       "имена важны: проверка обращается к сервису app")
        return cfg, svc

    def require_ports(self, svc):
        ports = svc["app"].get("ports") or []
        if not ports:
            raise Fail("ждали: у сервиса app есть ports — иначе с хоста до него не достучаться",
                       "получили: ports не задан",
                       "подсказка: ports: [\"8000:8000\"] — хост:контейнер")
        target = ports[0].get("target")
        self.cport = int(target)
        return ports

    def up(self, build=True):
        """Поднять. Порт студента заменяем на случайный на 127.0.0.1 — чтобы не упереться в занятый."""
        ver = COMPOSE["version"] or (0, 0, 0)
        if self.override is None and ver >= (2, 24, 4):
            tmp = Path(tempfile.mkdtemp(prefix="opr-lab10-"))
            CLEANUP.append(lambda: shutil.rmtree(str(tmp), ignore_errors=True))
            self.override = tmp / "ports.override.yaml"
            self.override.write_text(
                "services:\n  app:\n    ports: !override\n      - \"127.0.0.1::{}\"\n".format(
                    self.cport), encoding="utf-8")
            self.files = ["-f", str(self.file), "-f", str(self.override)]
        if not self.started:
            CLEANUP.append(self.down)
            self.started = True
        args = ["up", "-d"] + (["--build"] if build else [])
        code, out = self.run(args, timeout=UP_LIMIT)
        if code != 0:
            details = ["ждали: docker compose up -d отработает",
                       "получили: " + ("не уложился в {} с".format(UP_LIMIT) if code is None
                                       else short(" | ".join(tail(out, 2)), 160))]
            if "already allocated" in out or "address already in use" in out:
                details.append("порт занят на этой машине — закройте то, что его держит")
            if "container_name" in out or "is already in use by container" in out:
                details.append("уберите container_name: из compose — имя должно быть уникальным")
            raise Fail(*details)

    def host_port(self):
        for _ in range(20):
            code, out = self.run(["port", "app", str(self.cport)], timeout=30)
            m = re.search(r":(\d+)\s*$", out.strip().splitlines()[-1] if out.strip() else "")
            if code == 0 and m and m.group(1) != "0":
                return int(m.group(1))
            time.sleep(0.5)
        raise Fail("ждали: docker compose port app {} покажет порт на хосте".format(self.cport),
                   "получили: " + short(out))

    def container(self, service):
        code, out = self.run(["ps", "-a", "-q", service], timeout=30)
        ids = out.split() if code == 0 else []
        return ids[0] if ids else None

    def logs(self, service, n=None):
        """Лог сервиса без префикса «app-1 |». n — сколько последних строк, None — весь."""
        code, out = self.run(["logs", "--no-color", "--no-log-prefix", service], timeout=30)
        return out if n is None else " | ".join(tail(out, n))

    def keep_waiting(self):
        logs = self.logs("app")
        return (self.app_alive() and not listens_on_localhost(logs)
                and not wrong_port(logs, self.cport))

    def app_alive(self):
        cid = self.container("app")
        if not cid:
            return False
        code, out = sh(["inspect", "-f", "{{.State.Running}}", cid], timeout=20)
        return code == 0 and out.strip() == "true"

    def wait_health(self, svc):
        port = self.host_port()
        status, body = wait_http(port, "/health", (200,), HEALTH_WAIT, self.keep_waiting, stuck=15)
        if status == 200:
            return port
        details = ["ждали: GET /health → 200 (app видит redis)",
                   "получили: {}".format("{} {}".format(status, short(body)) if status
                                         else body)]
        logs = self.logs("app")
        env = svc["app"].get("environment") or {}
        if not self.app_alive():
            details.append("контейнер app упал; конец лога: " + short(" | ".join(tail(logs, 3))))
        elif status is None and listens_on_localhost(logs):
            details.append(HINT_HOST)
        elif status is None and wrong_port(logs, self.cport):
            details.append("в ports порт контейнера {}, а приложение слушает {}; "
                           "запись ports — ХОСТ:КОНТЕЙНЕР".format(
                               self.cport, wrong_port(logs, self.cport)))
        elif status == 503 and env.get("REDIS_HOST") in (None, "", "localhost", "127.0.0.1"):
            details.append("app ищет redis на localhost — внутри контейнера это он сам. "
                           "Задайте REDIS_HOST: имя сервиса redis")
        else:
            details.append("лог app: " + short(" | ".join(tail(logs, 3))))
        raise Fail(*details)

    def remember_volumes(self):
        """Безымянный том (VOLUME /data в образе redis) после down без -v остаётся сиротой:
        у него нет метки проекта, и down -v его потом уже не найдёт. Запоминаем заранее."""
        code, out = self.run(["ps", "-a", "-q"], timeout=30)
        for cid in (out.split() if code == 0 else []):
            c, o = sh(["inspect", "-f",
                       '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}} {{end}}{{end}}', cid],
                      timeout=20)
            if c == 0:
                self.volumes.update(o.split())

    def stop(self):
        """docker compose down без -v — как сделал бы студент."""
        self.remember_volumes()
        return self.run(["down", "-t", STOP_TIMEOUT], timeout=180)

    def down(self):
        """Уборка: данные больше не нужны, ждать штатной остановки незачем."""
        self.remember_volumes()
        self.run(["down", "-t", "1", "-v", "--rmi", "local", "--remove-orphans"], timeout=180)
        sweep_project(self.name)
        if self.volumes:
            quiet(["volume", "rm", "-f"] + sorted(self.volumes))


def hits(port):
    status, body = http_get(port, "/")
    m = re.search(r"(\d+)\s*$", body) if status == 200 else None
    return (int(m.group(1)) if m else None), status, body


def count(port, expected, when=""):
    got = []
    for want in expected:
        n, status, body = hits(port)
        got.append(str(n) if n is not None else "{} {}".format(status or "", short(body, 60)))
        if n != want:
            raise Fail("ждали: GET / {}→ {}".format(when, ", ".join(map(str, expected))),
                       "получили: " + ", ".join(got))


# ─── задачи 3, 4, 6 ───────────────────────────────────────────────────────

def task3():
    pr = Project("t3")
    cfg, svc = pr.services()
    pr.require_ports(svc)
    if "build" not in svc["app"]:
        raise Fail("ждали: у app есть build: . — образ собирается из вашего Dockerfile",
                   "получили: build не задан (image: {})".format(svc["app"].get("image", "—")))
    img = str(svc["redis"].get("image") or "")
    if "redis" not in img:
        raise Fail("ждали: redis из официального образа redis:7-alpine",
                   "получили: image: {}".format(img or "не задан"))
    note("docker compose up -d --build")
    try:
        pr.up()
        port = pr.wait_health(svc)
        count(port, [1, 2, 3])
    finally:
        pr.down()
    return "app и redis поднялись, /health → 200, счётчик 1, 2, 3"


def task4():
    pr = Project("t4")
    cfg, svc = pr.services()
    pr.require_ports(svc)
    vols = svc["redis"].get("volumes") or []
    named = [v for v in vols if v.get("type") == "volume" and v.get("source")]
    binds = [v for v in vols if v.get("type") == "bind"]
    if not named:
        details = ["ждали: у redis именованный том, например redis-data:/data, "
                   "и он объявлен в volumes: внизу файла"]
        if binds:
            details.append("получили: каталог с хоста ({} → {}); нужен именованный том — "
                           "им управляет docker, не ваша файловая система".format(
                               binds[0].get("source"), binds[0].get("target")))
        else:
            details.append("получили: тома нет — данные лежат в слое контейнера или "
                           "в безымянном томе, после down и up счёт начнётся с 1")
        raise Fail(*details)
    note("up, два запроса, down (без -v), снова up")
    try:
        pr.up()
        port = pr.wait_health(svc)
        count(port, [1, 2])
        code, out = pr.stop()
        if code != 0:
            raise Fail("docker compose down не отработал: " + short(" | ".join(tail(out, 2))))
        pr.up(build=False)
        port = pr.wait_health(svc)
        n, status, body = hits(port)
        if n != 3:
            target = named[0].get("target")
            details = ["ждали: после down и up GET / → 3 (счёт продолжается)",
                       "получили: {}".format(n if n is not None else "{} {}".format(
                           status, short(body)))]
            if target != "/data":
                details.append("том подключён к {}, а redis пишет в /data".format(target))
            else:
                details.append("redis сохраняет данные при штатной остановке; надёжнее — "
                               "command: redis-server --appendonly yes")
            raise Fail(*details)
    finally:
        pr.down()
    return "том {} пережил down: счёт продолжился с 3".format(named[0].get("source"))


def task6():
    pr = Project("t6")
    cfg, svc = pr.services()
    pr.require_ports(svc)
    problems = []
    rhc = svc["redis"].get("healthcheck") or {}
    test = rhc.get("test") or []
    test_s = " ".join(test) if isinstance(test, list) else str(test)
    if rhc.get("disable") or not ("redis-cli" in test_s and "ping" in test_s.lower()):
        problems.append("у redis нет healthcheck с redis-cli ping (сейчас: {})".format(
            short(test_s) if test_s else "нет"))
    dep = (svc["app"].get("depends_on") or {}).get("redis") or {}
    if dep.get("condition") != "service_healthy":
        problems.append("у app нет depends_on: redis: condition: service_healthy "
                        "(сейчас: {})".format(dep.get("condition") or "нет"))
    ahc = svc["app"].get("healthcheck") or {}
    if ahc.get("disable") or not ahc.get("test"):
        problems.append("у app нет healthcheck в compose — например, python -c с "
                        "urllib.request на /health: curl в python:slim нет")
    if problems:
        raise Fail(*problems)
    note("жду, пока docker compose ps покажет app healthy (до {} с)".format(HEALTHY_WAIT))
    try:
        pr.up()
        end = time.monotonic() + HEALTHY_WAIT
        state, log = "", ""
        while time.monotonic() < end:
            cid = pr.container("app")
            if cid:
                code, out = sh(["inspect", "-f", "{{json .State.Health}}", cid], timeout=20)
                try:
                    h = json.loads(out) if code == 0 else None
                except ValueError:
                    h = None
                if h:
                    state = h.get("Status", "")
                    logs = h.get("Log") or []
                    log = (logs[-1].get("Output") or "").strip() if logs else ""
                    if state in ("healthy", "unhealthy"):
                        break
            time.sleep(1)
        if state != "healthy":
            raise Fail("ждали: app в docker compose ps — healthy",
                       "получили: {}".format(state or "статуса нет"),
                       "последняя проверка: " + short(log) if log else
                       "интервал по умолчанию 30 с — поставьте interval: 5s")
    finally:
        pr.down()
    return "redis healthy → app стартует → app healthy"


# ─── задача 5: CI ─────────────────────────────────────────────────────────

class YamlError(Exception):
    def __init__(self, line, text):
        super().__init__("строка {}: {}".format(line, text))


def strip_comment(line):
    """Убрать комментарий: # в начале или после пробела, не внутри кавычек."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"" and (i == 0 or line[i - 1] in " \t:-[{,"):
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i].rstrip()
    return line.rstrip()


def scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    if text[:1] in "[{":
        try:
            value, rest = flow(text, 0)
            if not text[rest:].strip():
                return value
        except (IndexError, ValueError):
            pass
        return text
    if text in ("", "~", "null"):
        return None
    return text


def flow(text, i):
    """[a, b] и {k: v, …} в одну строку, с вложенностью. → (значение, где кончилось)."""
    close = {"[": "]", "{": "}"}[text[i]]
    items, i = [], i + 1
    while True:
        while text[i] in " ,":
            i += 1
        if text[i] == close:
            break
        if text[i] in "[{":
            value, i = flow(text, i)
            items.append(value)
            continue
        j, quote = i, None
        while quote or text[j] not in ",]}" or (text[j] == "}" and close != "}"):
            if quote and text[j] == quote:
                quote = None
            elif not quote and text[j] in "'\"" and j == i:
                quote = text[j]
            elif not quote and close == "}" and text[j] == ":" and text[j + 1] in " [{":
                break
            j += 1
        token = text[i:j].strip()
        if j < len(text) and text[j] == ":":
            j += 1
            while text[j] == " ":
                j += 1
            if text[j] in "[{":
                value, j = flow(text, j)
            else:
                k = text.index(text[j], j + 1) + 1 if text[j] in "'\"" else j
                while text[k] not in ",]}":
                    k += 1
                value, j = scalar(text[j:k]), k
            items.append((scalar(token), value))
        else:
            items.append(scalar(token))
        i = j
    if close == "}":
        return {(k if isinstance(x, tuple) else x): (v if isinstance(x, tuple) else None)
                for x in items for k, v in [x if isinstance(x, tuple) else (x, None)]}, i + 1
    return items, i + 1


def split_key(content):
    """«key: value» → (key, value) или None, если это не пара ключ-значение."""
    quote = None
    for i, ch in enumerate(content):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"" and i == 0:
            quote = ch
        elif ch == ":" and (i + 1 == len(content) or content[i + 1] in " \t"):
            key = content[:i].strip()
            if len(key) >= 2 and key[0] == key[-1] and key[0] in "'\"":
                key = key[1:-1]
            return key, content[i + 1:].strip()
        elif ch in "[{" and i == 0:
            return None
    return None


class MiniYaml:
    """Подмножество YAML, которого хватает на workflow GitHub Actions: блочные словари
    и списки, скаляры в кавычках и без, [a, b], блоки | и >. Комментарии выбрасываются."""

    def __init__(self, text):
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.i = 0

    def peek(self):
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if "\t" in raw[:len(raw) - len(raw.lstrip())]:
                raise YamlError(self.i + 1, "табуляция в отступе — в YAML только пробелы")
            s = strip_comment(raw)
            if s.strip() and s.strip() not in ("---", "..."):
                return len(s) - len(s.lstrip()), s.strip()
            self.i += 1
        return None

    def parse(self):
        top = self.peek()
        if top is None:
            return None
        doc = self.block(top[0])
        if self.peek() is not None:
            raise YamlError(self.i + 1, "лишний отступ или строка не на своём месте")
        return doc

    def block(self, indent):
        pk = self.peek()
        if pk[1] == "-" or pk[1].startswith("- "):
            return self.seq(indent)
        return self.mapping(indent)

    def mapping(self, indent):
        d = {}
        while True:
            pk = self.peek()
            if pk is None or pk[0] < indent:
                return d
            if pk[0] > indent:
                raise YamlError(self.i + 1, "отступ больше, чем у соседних ключей")
            if pk[1] == "-" or pk[1].startswith("- "):
                return d
            kv = split_key(pk[1])
            if kv is None:
                raise YamlError(self.i + 1, "ждали «ключ: значение», а тут {}".format(
                    short(pk[1], 40)))
            self.i += 1
            d[kv[0]] = self.value(kv[1], indent)

    def value(self, rest, indent):
        if re.match(r"^[|>][-+0-9]*$", rest):
            return self.literal(indent)
        if rest == "":
            pk = self.peek()
            if pk is None:
                return None
            if pk[0] > indent:
                return self.block(pk[0])
            if pk[0] == indent and (pk[1] == "-" or pk[1].startswith("- ")):
                return self.seq(indent)
            return None
        # продолжение строки без кавычек на следующих строках с большим отступом
        parts = [rest]
        while True:
            pk = self.peek()
            if pk is None or pk[0] <= indent or split_key(pk[1]) or pk[1].startswith("- "):
                break
            parts.append(pk[1])
            self.i += 1
        return scalar(" ".join(parts))

    def literal(self, indent):
        out, base = [], None
        while self.i < len(self.lines):
            raw = self.lines[self.i]
            if raw.strip() == "":
                out.append("")
                self.i += 1
                continue
            ind = len(raw) - len(raw.lstrip())
            if ind <= indent:
                break
            if base is None:
                base = ind
            out.append(raw[min(base, ind):])
            self.i += 1
        return "\n".join(out).strip("\n") + "\n"

    def seq(self, indent):
        items = []
        while True:
            pk = self.peek()
            if pk is None or pk[0] != indent or not (pk[1] == "-" or pk[1].startswith("- ")):
                return items
            rest = pk[1][1:].lstrip()
            col = indent + (len(pk[1]) - len(rest))
            if rest == "":
                self.i += 1
                items.append(self.value("", indent))
            elif split_key(rest) is not None:
                # «- key: value» — словарь, который начинается прямо на строке с дефисом
                self.lines[self.i] = " " * col + rest
                items.append(self.mapping(col))
            else:
                self.i += 1
                items.append(self.value(rest, indent))


# docker build — как команда: в начале строки или после ; && || | ( $( sudo,
# а не внутри echo "…docker build…".
BUILD_RE = re.compile(r"(?:^|[;&|(]|\bsudo)\s*docker\s+(?:buildx\s+build|build|image\s+build"
                      r"|compose\s+(?:-f\s+\S+\s+)*build|compose\s+(?:\S+\s+)*up\s.*--build)\b",
                      re.M)


def triggers(doc):
    on = doc.get("on", doc.get("true"))
    if isinstance(on, str):
        return [on]
    if isinstance(on, list):
        return [str(x) for x in on]
    if isinstance(on, dict):
        return list(on)
    return []


def check_workflow(path):
    """→ (None, описание) если годится, иначе (список проблем, None)."""
    try:
        doc = MiniYaml(path.read_text(encoding="utf-8-sig")).parse()
    except YamlError as e:
        return ["{}: не разобрал YAML, {}".format(path.name, e)], None
    except UnicodeDecodeError:
        return ["{}: файл не в UTF-8".format(path.name)], None
    if not isinstance(doc, dict):
        return ["{}: ждали словарь с ключами on: и jobs:, получили {}".format(
            path.name, "пустой файл" if doc is None else "не словарь")], None
    problems = []
    on = triggers(doc)
    if "push" not in on:
        problems.append("ждали: on: push — запуск на каждый push; получили: on: {}".format(
            ", ".join(on) if on else "нет"))
    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        problems.append("ждали: jobs: хотя бы с одной задачей; получили: {}".format(
            "нет jobs" if jobs is None else short(jobs, 40)))
        return problems, None
    best = None
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        miss = []
        ro = job.get("runs-on")
        ro_s = " ".join(map(str, ro)) if isinstance(ro, list) else str(ro or "")
        if "ubuntu" not in ro_s:
            miss.append("нет runs-on: ubuntu-latest (сейчас: {})".format(ro_s or "не задан"))
        steps = job.get("steps") if isinstance(job.get("steps"), list) else []
        co = bi = None
        for k, st in enumerate(steps):
            if not isinstance(st, dict):
                continue
            uses = str(st.get("uses") or "")
            run = str(st.get("run") or "")
            if co is None and uses.startswith("actions/checkout@"):
                co = k
            if bi is None and (uses.startswith("docker/build-push-action@") or BUILD_RE.search(run)):
                bi = k
        if not steps:
            miss.append("нет steps: со списком шагов")
        if co is None:
            miss.append("нет шага uses: actions/checkout@v4 — без него в раннере нет вашего кода")
        if bi is None:
            miss.append("нет шага сборки образа: run: docker build … "
                        "или uses: docker/build-push-action")
        elif co is not None and bi < co:
            miss.append("сборка идёт раньше checkout — собирать ещё нечего")
        if best is None or len(miss) < len(best[1]):
            best = (name, miss)
    if best is None:
        problems.append("в jobs нет ни одной задачи со steps:")
    elif best[1]:
        problems += ["в задаче {}: {}".format(best[0], m) for m in best[1]]
    if problems:
        return [path.name + ": " + p for p in problems], None
    return None, "{}: on push, задача {} на ubuntu, checkout → сборка образа".format(
        path.name, best[0])


def task5():
    files = workflows()
    if not files:
        raise Missing(".github/workflows/*.yml")
    results = [check_workflow(p) for p in files]
    for problems, ok in results:
        if ok:
            return ok
    raise Fail(*min((r[0] for r in results), key=len))


# ─── запуск ───────────────────────────────────────────────────────────────

TASKS = {1: task1, 2: task2, 3: task3, 4: task4, 5: task5, 6: task6}
NEEDS_DOCKER = {1, 2, 3, 4, 6}


def usage():
    me = Path(sys.argv[0]).name or "check.py"
    say("{}: проверка Dockerfile, .dockerignore, compose.yaml и CI.".format(LAB))
    say("  python3 {}        все задачи".format(me))
    say("  python3 {} 3      только задача 3; можно несколько: 3 4".format(me))
    say("На Windows вместо python3 — python или py.")
    for n in sorted(TASKS):
        say("  {}. {}".format(n, TITLES[n]))


def main(argv):
    if any(a in ("-h", "--help", "help") for a in argv):
        usage()
        return 0
    chosen = []
    for a in argv:
        if not a.isdigit() or int(a) not in TASKS:
            say("Нет задачи «{}». Задачи: {}.".format(a, ", ".join(map(str, sorted(TASKS)))))
            say("Пример: python3 {} 3".format(Path(sys.argv[0]).name or "check.py"))
            return 2
        if int(a) not in chosen:
            chosen.append(int(a))
    chosen = sorted(chosen) or sorted(TASKS)

    if NEEDS_DOCKER & set(chosen):
        ver = preflight()
        if ver is None:
            return 2
        COMPOSE["version"] = ver
        if ver < (2, 24, 4):
            say("Внимание: docker compose {} старый, обновите Docker Desktop. Проверка возьмёт "
                "порты из вашего compose.yaml как есть — они должны быть свободны.".format(
                    ".".join(map(str, ver))))
        sweep_leftovers()

    results = {}
    started = time.monotonic()
    try:
        for n in chosen:
            say("Задача {}. {}".format(n, TITLES[n]))
            try:
                msg = TASKS[n]()
                results[n] = True
                say("Задача {}: PASS{}".format(n, " — " + msg if msg else ""))
            except Missing as e:
                results[n] = None
                say("Задача {}: нет файла {}".format(n, e))
            except Fail as e:
                results[n] = False
                say("Задача {}: FAIL".format(n))
                for d in e.details[:SHOW]:
                    say("  " + d)
    except KeyboardInterrupt:
        say("\nПрервано. Убираю за собой…")
        return 130
    finally:
        for fn in reversed(CLEANUP):
            try:
                fn()
            except Exception:
                pass

    solved = [n for n in chosen if results.get(n) is True]
    failed = [n for n in chosen if results.get(n) is False]
    missing = [n for n in chosen if results.get(n) is None]
    summary = "Итог: решено {} из {}.".format(len(solved), len(chosen))
    if failed:
        summary += " Не прошли: {}.".format(", ".join(map(str, failed)))
    if missing:
        summary += " Нет файла: {}.".format(", ".join(map(str, missing)))
    say()
    say(summary + " Время: {:.0f} с.".format(time.monotonic() - started))
    return 0 if len(solved) == len(chosen) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
