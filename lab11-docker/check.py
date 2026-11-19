#!/usr/bin/env python3
"""Занятие 11 · Docker 2: проверка задач «сломанные контейнеры».

    python3 check.py           все задачи
    python3 check.py 3         только задача 3; можно несколько номеров: 3 5 6
    python3 check.py --clean   убрать всё, что могла оставить прерванная проверка
    На Windows: python check.py или py check.py

Что делает: копирует каталог задачи во временный, собирает образ, запускает
контейнер или compose-проект и проверяет поведение — отвечает ли сервис,
что лежит в образе, что видно в docker history, inspect и logs. Ваши файлы
в задачи/ не меняются. Всё, что проверка создала (контейнеры, сети, тома,
образы), называется opr11-tN-… и удаляется в конце, даже по Ctrl+C.
Порты на хосте выбирает Docker, поэтому проверку можно запускать параллельно.

Нужно: запущенный Docker (Docker Desktop или dockerd), docker compose v2,
BuildKit (buildx). Python 3.8+, только стандартная библиотека. Root не нужен.
"""

import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

LAB = "Занятие 11 · Docker 2"

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
TASKS_DIR = HERE / "задачи"
RID = secrets.token_hex(3)          # у каждого прогона свои имена
WIDTH = 160
MB = 1024 * 1024

# Переменные, которые меняют поведение docker compose и сборки у студента.
DROP_ENV = ("COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_PROFILES", "COMPOSE_ENV_FILES",
            "DOCKER_BUILDKIT", "BUILDX_BUILDER", "COMPOSE_BAKE")


class Fail(Exception):
    """Задача не прошла; args[0] — список строк с подробностями."""


# ─────────────────────────── запуск команд ───────────────────────────

def base_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in DROP_ENV}
    env["DOCKER_BUILDKIT"] = "1"
    env["DOCKER_CLI_HINTS"] = "false"
    if extra:
        env.update(extra)
    return env


class Result:
    def __init__(self, code, out, err, timed_out=False):
        self.code, self.out, self.err, self.timed_out = code, out, err, timed_out

    @property
    def both(self):
        return self.out + self.err


def run(args, timeout=120, cwd=None, env=None):
    try:
        p = subprocess.run(args, cwd=None if cwd is None else str(cwd), env=env or base_env(),
                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        dec = lambda b: (b or b"").decode("utf-8", "replace")
        return Result(124, dec(e.stdout), dec(e.stderr) + "\n(не уложилось в {} с)".format(timeout),
                      True)
    except OSError as e:
        return Result(127, "", str(e))
    return Result(p.returncode, p.stdout.decode("utf-8", "replace"),
                  p.stderr.decode("utf-8", "replace"))


def docker(*args, **kw):
    return run(["docker"] + [str(a) for a in args], **kw)


def short(text, width=WIDTH):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width] + "…"


def tail(text, n=8, indent="    | "):
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    if not lines:
        return [indent + "(пусто)"]
    return [indent + (l if len(l) <= WIDTH else l[:WIDTH] + "…") for l in lines[-n:]]


# ─────────────────────────── уборка ───────────────────────────

class Janitor:
    """Всё, что создала проверка одной задачи; clean() удаляет."""

    def __init__(self, n):
        self.n = n
        self.prefix = "opr11-t{}-{}".format(n, RID)
        self.count = 0
        self.containers, self.images, self.volumes, self.projects, self.dirs = [], [], [], [], []
        self.notes = []

    def name(self, what=""):
        self.count += 1
        return "{}-{}{}".format(self.prefix, what or "c", self.count)

    def tmpdir(self):
        d = Path(tempfile.mkdtemp(prefix=self.prefix + "-"))
        self.dirs.append(d)
        return d

    def track_compose(self, project, ctx):
        """Запомнить тома и собранные образы контейнеров проекта, пока они есть."""
        r = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + project)
        ids = r.out.split()
        if not ids:
            return
        r = docker("inspect", *ids)
        try:
            info = json.loads(r.out)
        except ValueError:
            return
        for c in info:
            for m in c.get("Mounts") or []:
                if m.get("Type") == "volume" and m.get("Name") and m["Name"] not in self.volumes:
                    self.volumes.append(m["Name"])
            img = (c.get("Config") or {}).get("Image", "")
            if img.startswith(project) and img not in self.images:
                self.images.append(img)

    def clean(self):
        for project, ctx in self.projects:
            self.track_compose(project, ctx)
            docker("compose", "-p", project, "down", "-v", "--remove-orphans", "--rmi", "local",
                   "-t", "2", cwd=ctx, timeout=120)
            # на случай, если compose.yaml сломан и down не смог его прочесть
            r = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + project)
            if r.out.split():
                docker("rm", "-f", "-v", *r.out.split())
            r = docker("network", "ls", "-q", "--filter",
                       "label=com.docker.compose.project=" + project)
            if r.out.split():
                docker("network", "rm", *r.out.split())
        if self.containers:
            docker("rm", "-f", "-v", *self.containers, timeout=60)
        for v in self.volumes:
            r = docker("volume", "inspect", v)
            if r.code != 0:
                continue
            try:
                labels = json.loads(r.out)[0].get("Labels") or {}
            except (ValueError, IndexError):
                labels = {}
            mine = (v.startswith("opr11-t") or "com.docker.volume.anonymous" in labels
                    or re.fullmatch(r"[0-9a-f]{64}", v)
                    or any(labels.get("com.docker.compose.project") == p for p, _ in self.projects))
            if mine:
                docker("volume", "rm", "-f", v)
            else:
                self.notes.append("том {} создан не проверкой — не трогаю, удалите сами, "
                                  "если он не нужен: docker volume rm {}".format(v, v))
        if self.images:
            docker("rmi", "-f", *self.images, timeout=120)
        for d in self.dirs:
            shutil.rmtree(str(d), ignore_errors=True)


def clean_everything():
    """--clean: всё с именами opr11-tN-…, что осталось от прерванных проверок."""
    pat = re.compile(r"^opr11-t\d+-[0-9a-f]{6}")
    removed = 0
    r = docker("ps", "-a", "--format", "{{.ID}} {{.Names}} {{.Label \"com.docker.compose.project\"}}")
    ids = [l.split()[0] for l in r.out.splitlines()
           if len(l.split()) > 1 and any(pat.match(x) for x in l.split()[1:])]
    if ids:
        docker("rm", "-f", "-v", *ids)
        removed += len(ids)
    r = docker("network", "ls", "--format", "{{.Name}}")
    nets = [n for n in r.out.split() if pat.match(n)]
    if nets:
        docker("network", "rm", *nets)
        removed += len(nets)
    r = docker("volume", "ls", "--format", "{{.Name}}")
    vols = [v for v in r.out.split() if pat.match(v)]
    if vols:
        docker("volume", "rm", "-f", *vols)
        removed += len(vols)
    r = docker("images", "--format", "{{.Repository}}:{{.Tag}}")
    imgs = [i for i in r.out.split() if pat.match(i)]
    if imgs:
        docker("rmi", "-f", *imgs)
        removed += len(imgs)
    print("Убрано объектов Docker: {}.".format(removed))
    return 0


# ─────────────────────────── кирпичики проверок ───────────────────────────

def build(j, ctx, extra=(), env=None, tag=None, timeout=900):
    tag = tag or j.prefix
    if tag not in j.images:
        j.images.append(tag)
    r = docker("build", "--progress=plain", "--load", "-t", tag, *extra, str(ctx),
               timeout=timeout, env=base_env(env))
    if r.code != 0:
        raise Fail(["образ не собирается (docker build, код {}):".format(r.code)] + tail(r.both, 12))
    return r.both


def start(j, image, *opts, cmd=()):
    name = j.name()
    j.containers.append(name)
    r = docker("run", "-d", "--name", name, *opts, image, *cmd)
    if r.code != 0:
        raise Fail(["контейнер не запустился (docker run):"] + tail(r.both, 6))
    return name


def state(name):
    r = docker("inspect", "-f", "{{json .State}}", name)
    try:
        return json.loads(r.out)
    except ValueError:
        return {}


def logs(name):
    return docker("logs", name).both


def host_port(name, port):
    for _ in range(20):
        r = docker("port", name, "{}/tcp".format(port))
        for line in r.out.splitlines():
            line = line.strip()
            if line.startswith("0.0.0.0:") or line.startswith("127.0.0.1:"):
                return "127.0.0.1:" + line.rsplit(":", 1)[1]
            if line.startswith("[::]:"):
                return "127.0.0.1:" + line.rsplit(":", 1)[1]
        if not state(name).get("Running"):
            break
        time.sleep(0.3)
    return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get(url, timeout=3):
    """→ (код, тело, ошибка); код None — соединения не вышло."""
    try:
        with _OPENER.open(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), None
    except Exception as e:  # URLError, сброс соединения, таймаут
        reason = getattr(e, "reason", e)
        return None, "", "{}: {}".format(type(reason).__name__, reason)


def wait_http(name, url, want, total=20):
    """Ждать ответа 200 с want в теле. → (код, тело, ошибка) последней попытки."""
    end = time.monotonic() + total
    last = (None, "", "не пробовали")
    while time.monotonic() < end:
        last = http_get(url)
        if last[0] == 200 and want in last[1]:
            return last
        if name and not state(name).get("Running", False):
            time.sleep(0.5)
            last = http_get(url) if last[0] is None else last
            return last
        time.sleep(0.4)
    return last


def died(name):
    st = state(name)
    if st.get("Running"):
        return []
    return ["контейнер завершился (код {}). Последние строки docker logs:".format(
        st.get("ExitCode"))] + tail(logs(name))


PROBE_HTTP = """
import sys, urllib.request as u, urllib.error as e
try:
    r = u.urlopen(sys.argv[1], timeout=4); print(r.status); print(r.read().decode())
except e.HTTPError as x:
    print(x.code); print(x.read().decode())
except Exception as x:
    print('ERR'); print(type(x).__name__, x)
"""


def exec_http(target, url, compose=None):
    """HTTP-запрос изнутри контейнера. target — имя контейнера или (проект, сервис, каталог)."""
    if compose:
        project, service, ctx = compose
        r = docker("compose", "-p", project, "exec", "-T", service, "python3", "-c", PROBE_HTTP, url,
                   cwd=ctx, timeout=30)
    else:
        r = docker("exec", target, "python3", "-c", PROBE_HTTP, url, timeout=30)
    lines = r.out.splitlines()
    if r.code != 0 or not lines:
        return None, "", short(r.both or "exec не удался")
    if lines[0] == "ERR":
        return None, "", " ".join(lines[1:])
    return int(lines[0]), "\n".join(lines[1:]), None


def fresh_copy(j, n):
    src = task_dir(n)
    dst = j.tmpdir() / "ctx"
    shutil.copytree(str(src), str(dst), symlinks=True)
    return dst


def task_dir(n):
    found = sorted(TASKS_DIR.glob("{}-*".format(n)))
    return found[0] if found else None


def compose(project, ctx, *args, timeout=240):
    return docker("compose", "-p", project, *args, cwd=ctx, timeout=timeout)


def compose_project(j, ctx):
    project = j.prefix
    j.projects.append((project, ctx))
    r = compose(project, ctx, "config", "-q", timeout=60)
    if r.code != 0:
        raise Fail(["compose.yaml не читается (docker compose config):"] + tail(r.both, 8))
    return project


def compose_ids(project, service):
    r = docker("ps", "-aq", "--filter", "label=com.docker.compose.project=" + project,
               "--filter", "label=com.docker.compose.service=" + service)
    return r.out.split()


def compose_logs(project, ctx, service, n=8):
    return tail(compose(project, ctx, "logs", "--no-color", "--no-log-prefix", service,
                        timeout=60).both, n)


def edit(path, old, new, n):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise Fail(["в {} нет строки «{}» — этот файл менять нельзя, верните его: "
                    "из каталога курса bash lab11-docker/reset.sh {} (ваш вариант сохранится в бэкап/)".format(path.name, old, n)])
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def steps(log):
    """Шаги из docker build --progress=plain: {номер: [описание, cached, строки]}."""
    out = {}
    for line in log.splitlines():
        m = re.match(r"^#(\d+) (.*)$", line)
        if not m:
            continue
        k, text = m.group(1), m.group(2)
        st = out.setdefault(k, ["", False, []])
        if not st[0] and text.startswith("["):
            st[0] = re.sub(r"^\[[^\]]*\]\s*", "", text).strip()
        elif text.strip() == "CACHED":
            st[1] = True
        else:
            st[2].append(text)
    return out


# ─────────────────────────── задачи ───────────────────────────

def task1(j, ctx):
    build(j, ctx)
    image = j.prefix
    c = start(j, image, "-p", "127.0.0.1::8000")
    addr = host_port(c, 8000)
    if not addr:
        raise Fail(["у контейнера нет опубликованного порта 8000."] + died(c))
    code, body, err = wait_http(c, "http://{}/".format(addr), "работает", total=10)
    if code == 200 and "работает" in body:
        return ["с хоста по опубликованному порту: «{}»".format(body.strip())]
    lines = ["с хоста по опубликованному порту {} ответа нет: {}".format(
        addr, err or "код {} «{}»".format(code, short(body)))]
    if died(c):
        raise Fail(lines + died(c))
    icode, ibody, ierr = exec_http(c, "http://127.0.0.1:8000/")
    if icode == 200:
        lines.append("а изнутри контейнера по http://127.0.0.1:8000/ служба отвечает: «{}»".format(
            ibody.strip()))
    else:
        lines.append("изнутри контейнера по http://127.0.0.1:8000/ тоже нет ответа: {}".format(ierr))
    lines.append("docker logs:")
    raise Fail(lines + tail(logs(c), 4))


def task2(j, ctx):
    tag = j.prefix
    b1 = build(j, ctx, ["--no-cache"])
    installs = [s[0] for s in steps(b1).values() if any("Successfully installed" in l for l in s[2])]
    if not installs:
        raise Fail(["при сборке без кеша pip ничего не установил: в выводе docker build нет "
                    "«Successfully installed». Зависимости должны ставиться при сборке из "
                    "requirements.txt."])
    want = "версия ведомости: 1.0; tabulate 0.9.0"
    r = docker("run", "--rm", tag, timeout=60)
    if want not in r.out:
        raise Fail(["образ печатает не то: ждали строку «{}».".format(want)] + tail(r.both, 6))

    edit(ctx / "app.py", 'REPORT_VERSION = "1.0"', 'REPORT_VERSION = "1.0-{}"'.format(RID), 2)
    b2 = build(j, ctx)
    s2 = steps(b2)
    problems = []
    for desc in installs:
        same = [s for s in s2.values() if s[0] == desc]
        if not same or not same[0][1] or any("Successfully installed" in l for l in same[0][2]):
            problems.append("после правки app.py шаг «{}» выполнился заново, а не CACHED: "
                            "зависимости ставились ещё раз".format(short(desc, 90)))
    if not problems and "Successfully installed" in b2:
        problems.append("после правки app.py pip снова что-то установил (Successfully installed)")
    if problems:
        raise Fail(problems)
    r = docker("run", "--rm", tag, timeout=60)
    if "1.0-{}".format(RID) not in r.out:
        raise Fail(["после правки app.py образ печатает старую версию ведомости — "
                    "новый код в образ не попал:"] + tail(r.both, 3))

    edit(ctx / "requirements.txt", "tabulate==0.9.0", "tabulate==0.8.10", 2)
    b3 = build(j, ctx)
    r = docker("run", "--rm", tag, timeout=60)
    if "tabulate 0.8.10" not in r.out:
        raise Fail(["в requirements.txt поменяли tabulate==0.9.0 на 0.8.10 и пересобрали — "
                    "а в образе по-прежнему другая версия: зависимости берутся не из "
                    "requirements.txt:"] + tail(r.both, 3))
    return ["после правки кода шаг установки CACHED, после правки requirements.txt — "
            "ставится заново"]


def task3(j, ctx):
    build(j, ctx)
    image = j.prefix
    cases = [
        ([], "Привет, студент!"),
        (["--name", "Ivan"], "Привет, Ivan!"),
        (["--anon"], "Привет, незнакомец!"),
        (["--name", "Анна Мария", "--shout"], "ПРИВЕТ, АННА МАРИЯ!"),
    ]
    bad = []
    for args, want in cases:
        name = j.name()
        j.containers.append(name)
        r = docker("run", "--rm", "--name", name, image, *args, timeout=60)
        got = r.out.strip()
        if got != want:
            shown = " ".join(a if " " not in a else '"{}"'.format(a) for a in args)
            bad.append("docker run --rm образ {}".format(shown).rstrip())
            bad.append("    ждали: «{}»".format(want))
            bad.append("    вывод: «{}»".format(short(got)) if got else "    вывод: (пусто)")
            err = [l for l in r.err.splitlines()
                   if l.strip() and "docker run --help" not in l]
            if err:
                msg = err[0]
                if "exec: " in msg:     # от длинной ошибки runc нужен только хвост
                    msg = "docker: … " + msg[msg.index("exec: "):]
                bad.append("    stderr: {}".format(short(msg)))
    if bad:
        raise Fail(bad)
    return ["без аргументов — умолчание, с аргументами — они доходят до greet.py"]


def image_files(path):
    """Файлы из архива docker save: (слой или None, имя, член архива, открытый файл).

    Слой — каталог образа из docker save (tar внутри tar, может быть сжат gzip);
    для остального (manifest, config с history и Env) слой None.
    Удалённые в верхних слоях файлы тоже здесь: слои скачиваются целиком.
    """
    with tarfile.open(str(path), "r:") as outer:
        for m in outer:
            if not m.isfile():
                continue
            f = outer.extractfile(m)
            head = f.read(512)
            f.seek(0)
            layer = m.name.split("/")[-1].replace("layer.tar", m.name.split("/")[0])[:12]
            if head[:2] == b"\x1f\x8b" or head[257:262] == b"ustar":
                try:
                    with tarfile.open(fileobj=f, mode="r:*") as inner:
                        for im in inner:
                            if im.isfile():
                                yield layer, "/" + im.name.lstrip("./"), im, inner.extractfile(im)
                    continue
                except (tarfile.TarError, OSError, EOFError):
                    f.seek(0)
            yield None, m.name, m, f


def save_image(j, image):
    tmp = j.tmpdir() / "image.tar"
    r = docker("save", "-o", tmp, image, timeout=300)
    if r.code != 0:
        raise Fail(["docker save не удался: " + short(r.both)])
    return tmp


def find_in_image(path, needles):
    """Где в архиве docker save встречаются needles: [(метка, где)]."""
    found = []
    keep = max(len(x) for x in needles.values())
    for layer, name, _, f in image_files(path):
        where = ("файл {} (слой {})".format(name, layer) if layer
                 else "метаданные образа ({})".format(name))
        prev = b""
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            data = prev + chunk
            for label, needle in needles.items():
                if needle in data and (label, where) not in found:
                    found.append((label, where))
            prev = data[-keep:]
    return found


def task4(j, ctx):
    s_build = "opr11build" + secrets.token_hex(10)
    s_run = "opr11run" + secrets.token_hex(10)
    h = lambda p, s: hashlib.sha256((p + s).encode()).hexdigest()[:16]
    image = j.prefix
    # --no-cache: секрет сборки не входит в ключ кеша, и шаг с прошлым токеном взялся бы из кеша
    build(j, ctx, ["--no-cache", "--build-arg", "API_TOKEN=" + s_build,
                           "--secret", "id=api_token,env=OPR11_BUILD_TOKEN"],
                  env={"OPR11_BUILD_TOKEN": s_build})
    problems = []

    r = docker("history", "--no-trunc", "--format", "{{.CreatedBy}}", image)
    for line in r.out.splitlines():
        if s_build in line:
            problems.append("токен сборки виден в docker history --no-trunc: «{}»".format(
                short(line.replace(s_build, "<ТОКЕН>"), 110)))
            break
    r = docker("image", "inspect", image)
    if s_build in r.out:
        try:
            cfg = json.loads(r.out)[0].get("Config") or {}
            where = [k for k, v in cfg.items() if s_build in json.dumps(v)]
        except (ValueError, IndexError):
            where = []
        problems.append("токен сборки виден в docker image inspect{}".format(
            ": Config." + ", Config.".join(where) if where else ""))
    tmp = save_image(j, image)
    for label, where in find_in_image(tmp, {"build": s_build.encode(), "run": s_run.encode()}):
        if "метаданные" in where and problems:
            continue    # история и конфиг уже названы выше
        problems.append("токен {} лежит в образе: {}".format(
            "сборки" if label == "build" else "запуска", where))
    tmp.unlink()

    c = start(j, image, "-e", "API_TOKEN=" + s_run, "-p", "127.0.0.1::8000")
    addr = host_port(c, 8000)
    code, body, err = wait_http(c, "http://{}/".format(addr), "catalog", total=15) if addr \
        else (None, "", "порт не опубликован")
    if code != 200:
        problems.append("сервис не отвечает: {}".format(err or "код {}".format(code)))
        problems += died(c)
    else:
        try:
            got = json.loads(body)
        except ValueError:
            got = {}
        if got.get("catalog") != h("каталог:", s_build):
            problems.append("каталог собран не с тем токеном, что передан при сборке "
                            "(prepare.py не получил токен конвейера)")
        if got.get("token") != h("ключ:", s_run):
            problems.append("сервис работает не с тем токеном, что передан при запуске "
                            "через docker run -e API_TOKEN=…")
    if problems:
        raise Fail(problems)
    return ["токена нет ни в history, ни в inspect, ни в слоях; сборка и запуск получают его снаружи"]


GO_TOOLS = re.compile(r"(^|/)(go|gofmt)$")


def task5(j, ctx):
    limit = 30
    build(j, ctx)
    image = j.prefix
    # Размер — сумма файлов во всех слоях: столько скачивает docker pull.
    # Файл, удалённый следующей инструкцией, всё равно лежит в своём слое.
    tmp = save_image(j, image)
    total, tools, goroot = 0, [], False
    for layer, name, m, _ in image_files(tmp):
        if layer is None:
            continue
        total += m.size
        if GO_TOOLS.search(name) and (m.mode & 0o111) and len(tools) < 3:
            tools.append(name)
        goroot = goroot or name.startswith("/usr/local/go/")
    tmp.unlink()
    problems = []
    if total >= limit * MB:
        problems.append("слои образа весят {:.1f} МБ, а должно быть меньше {} МБ".format(
            total / MB, limit))
    if tools or goroot:
        problems.append("в слоях образа есть компилятор Go: {}".format(
            ", ".join(tools) if tools else "/usr/local/go"))
    c = start(j, image, "-p", "127.0.0.1::8080")
    addr = host_port(c, 8080)
    code, body, err = wait_http(c, "http://{}/ping".format(addr), "pong 1.4.2", total=15) if addr \
        else (None, "", "порт 8080 не опубликован")
    if not (code == 200 and "pong 1.4.2" in body):
        problems.append("GET /ping не отвечает «pong 1.4.2»: {}".format(
            err or "код {} «{}»".format(code, short(body))))
        problems += died(c)
    if problems:
        raise Fail(problems)
    return ["слои образа — {:.1f} МБ, компилятора нет, /ping отвечает".format(total / MB)]


def task6(j, ctx):
    project = compose_project(j, ctx)
    note = "заметка-" + RID

    def up(when):
        r = compose(project, ctx, "up", "-d", "--wait", "--wait-timeout", "60")
        j.track_compose(project, ctx)
        if r.code != 0:
            raise Fail(["docker compose up ({}) не удался:".format(when)] + tail(r.both, 8))

    def cli(*args):
        end = time.monotonic() + 30
        last = None
        while time.monotonic() < end:
            last = compose(project, ctx, "exec", "-T", "redis", "redis-cli", *args, timeout=30)
            if last.code == 0 and "LOADING" not in last.out:
                return last.out.strip()
            time.sleep(0.5)
        raise Fail(["redis-cli {} не отвечает:".format(" ".join(args))] + tail(last.both, 4)
                   + ["логи redis:"] + compose_logs(project, ctx, "redis"))

    up("первый")
    if cli("SET", "opr11:note", note) != "OK":
        raise Fail(["SET в redis не прошёл"])
    r = compose(project, ctx, "down", "-t", "10")
    if r.code != 0:
        raise Fail(["docker compose down не удался:"] + tail(r.both, 4))
    up("после down")
    got = cli("GET", "opr11:note")
    if got != note:
        raise Fail(["записали заметку, сделали docker compose down и up — заметки нет "
                    "(GET вернул «{}»)".format(got)])
    r = compose(project, ctx, "down", "-v", "-t", "10")
    up("после down -v")
    got = cli("GET", "opr11:note")
    if got:
        raise Fail(["после docker compose down -v и up заметка всё ещё на месте — down -v "
                    "должен стирать данные проекта, а они хранятся где-то вне томов compose"])
    return ["после down/up заметка на месте, после down -v — стёрта"]


def task7(j, ctx):
    project = compose_project(j, ctx)
    r = compose(project, ctx, "up", "-d", "--build", "--wait", "--wait-timeout", "150", timeout=400)
    j.track_compose(project, ctx)
    build_failed = r.code != 0 and "exited" not in r.both and "unhealthy" not in r.both \
        and "failed" in r.both.lower() and not compose_ids(project, "app")
    if build_failed:
        raise Fail(["docker compose up не удался:"] + tail(r.both, 8))
    end = time.monotonic() + 30
    code, body, err = None, "", ""
    while time.monotonic() < end:
        code, body, err = exec_http(None, "http://localhost:8000/health",
                                    compose=(project, "app", ctx))
        if code == 200:
            break
        ids = compose_ids(project, "app")
        st = state(ids[0]) if ids else {}
        if not st.get("Running") and not st.get("Restarting"):
            break
        time.sleep(1)
    ids = compose_ids(project, "app")
    st = state(ids[0]) if ids else {}
    restarts = 0
    if ids:
        rr = docker("inspect", "-f", "{{.RestartCount}}", ids[0])
        restarts = int(rr.out.strip() or 0) if rr.out.strip().isdigit() else 0
    applog = compose(project, ctx, "logs", "--no-color", "--no-log-prefix", "app", timeout=60).both
    problems = []
    if not ids:
        problems.append("контейнера app нет — compose его не создал:")
        problems += tail(r.both, 6)
    elif code != 200:
        problems.append("/health не ответил 200 «ok»: {}".format(
            err or "код {} «{}»".format(code, short(body))))
        if not st.get("Running"):
            problems.append("app в статусе {} (код {}). docker compose logs app:".format(
                st.get("Status"), st.get("ExitCode")))
            problems += tail(applog, 6)
    if ids and (restarts or "не могу подключиться" in applog):
        problems.append("app падал при старте{}: «{}»".format(
            ", перезапусков: {}".format(restarts) if restarts else "",
            short(next((l for l in applog.splitlines() if "не могу подключиться" in l),
                       "см. docker compose logs app"), 120)))
        problems.append("нужно, чтобы app стартовал с первого раза, когда база уже готова")
    if problems:
        raise Fail(problems)
    return ["app стартовал с первого раза, /health — ok"]


PROBE_TCP = """
import socket, sys
for target in sys.argv[1:]:
    host, port = target.rsplit(':', 1)
    try:
        socket.create_connection((host, int(port)), timeout=2).close()
        print('OPEN', target)
    except Exception as x:
        print('CLOSED', target, type(x).__name__, x)
"""


def task8(j, ctx):
    project = compose_project(j, ctx)
    r = compose(project, ctx, "up", "-d", "--build", "--wait", "--wait-timeout", "90", timeout=400)
    j.track_compose(project, ctx)
    for svc in ("front", "api", "db"):
        if not compose_ids(project, svc):
            raise Fail(["сервиса {} нет — имена front, api, db менять нельзя:".format(svc)]
                       + tail(r.both, 6))
    problems = []
    end = time.monotonic() + 15
    want = "front → api → db: PONG"
    code, body, err = None, "", ""
    while time.monotonic() < end:
        code, body, err = exec_http(None, "http://localhost:8000/", compose=(project, "front", ctx))
        if code == 200 and want in body:
            break
        time.sleep(1)
    if not (code == 200 and want in body):
        problems.append("front не отдаёт «{}»: {}".format(
            want, err or "код {} «{}»".format(code, short(body.strip()))))

    db = compose_ids(project, "db")[0]
    info = json.loads(docker("inspect", db).out)[0]
    nets = (info.get("NetworkSettings") or {}).get("Networks") or {}
    targets = ["db:6379"] + ["{}:6379".format(n["IPAddress"]) for n in nets.values()
                             if n.get("IPAddress")]
    published = [p for p, b in ((info.get("NetworkSettings") or {}).get("Ports") or {}).items()
                 if b]
    if published:
        problems.append("у db опубликованы порты на хост ({}): через хост до базы "
                        "дотянется кто угодно, в том числе front".format(", ".join(published)))
    r = docker("compose", "-p", project, "exec", "-T", "front", "python3", "-c", PROBE_TCP,
               *targets, cwd=ctx, timeout=60)
    opened = [l.split()[1] for l in r.out.splitlines() if l.startswith("OPEN")]
    if r.code != 0 and not r.out:
        problems.append("не получилось зайти в front: " + short(r.both))
    for t in opened:
        problems.append("из front открывается соединение с базой: {}".format(
            t if not t.startswith("db:") else "по имени db:6379"))
    if problems:
        raise Fail(problems)
    return ["front → api → db работает, из front база недоступна ни по имени, ни по IP"]


PROBE_UID = """
import os
me = os.getpid()
for p in sorted(os.listdir('/proc'), key=lambda s: int(s) if s.isdigit() else 0):
    if not p.isdigit() or int(p) == me:
        continue
    try:
        st = open('/proc/%s/status' % p).read()
        cmd = open('/proc/%s/cmdline' % p, 'rb').read().replace(b'\\0', b' ').decode().strip()
    except OSError:
        continue
    uid = [l.split()[1:3] for l in st.splitlines() if l.startswith('Uid:')][0]
    print(p, uid[0], uid[1], cmd)
"""


def task9(j, ctx):
    build(j, ctx)
    image = j.prefix
    vol = j.prefix + "-data"
    j.volumes.append(vol)
    docker("volume", "create", vol)
    problems = []
    for label, opts in (("без тома", []), ("с новым томом на /app/data", ["-v", vol + ":/app/data"])):
        c = start(j, image, "-p", "127.0.0.1::8000", *opts)
        addr = host_port(c, 8000)
        if not addr:
            problems.append("{}: сервис не запустился.".format(label))
            problems += died(c)
            break
        code1, body1, err1 = wait_http(c, "http://{}/".format(addr), "посещений", total=15)
        code2, body2, err2 = http_get("http://{}/".format(addr))
        m1 = re.search(r"посещений: (\d+)", body1)
        m2 = re.search(r"посещений: (\d+)", body2)
        if not (code1 == 200 and code2 == 200 and m1 and m2 and int(m2.group(1)) == int(m1.group(1)) + 1):
            problems.append("{}: счётчик не работает: {}".format(
                label, err1 or err2 or short((body1 + " / " + body2).strip())))
            problems += died(c)
            break
        r = docker("exec", "-u", "0", c, "python3", "-c", PROBE_UID)
        roots = [l.split(None, 3) for l in r.out.splitlines() if l.split()[1:3].count("0")]
        if r.code != 0:
            problems.append("не получилось посмотреть процессы: " + short(r.both))
        for p in roots:
            problems.append("{}: процесс PID {} работает от uid 0: {}".format(
                label, p[0], short(p[3] if len(p) > 3 else "?", 80)))
        if roots:
            break
    if problems:
        raise Fail(problems)
    return ["процессы не от root, запись в /app/data работает и на новом томе"]


def timed_stop(c, t=5):
    t0 = time.monotonic()
    docker("stop", "-t", str(t), c, timeout=t + 30)
    return time.monotonic() - t0, state(c).get("ExitCode")


def task10(j, ctx):
    build(j, ctx)
    image = j.prefix
    c = start(j, image, "-p", "127.0.0.1::8000")
    addr = host_port(c, 8000)
    oid = "opr11-" + RID
    code, body, err = wait_http(c, "http://{}/order?id={}".format(addr, oid), "принят", total=15) \
        if addr else (None, "", "порт не опубликован")
    if code != 200:
        raise Fail(["сервис не отвечает: {}".format(err or "код {}".format(code))] + died(c))
    want = "заказ {} принят".format(oid)
    end = time.monotonic() + 5
    out = ""
    while time.monotonic() < end:
        out = logs(c)
        if want in out:
            break
        time.sleep(0.3)
    problems = []
    if want not in out:
        problems.append("сделали GET /order?id={}, а в docker logs нет строки «{}». "
                        "docker logs:".format(oid, want))
        problems += tail(out, 4)
    dt, ec = timed_stop(c)
    if ec != 0 or dt > 4:
        problems.append("docker stop -t 5 занял {:.1f} с, код выхода {}{}".format(
            dt, ec, " — контейнер не остановился сам и был убит" if ec == 137 else ""))
    if problems:
        raise Fail(problems)
    return ["журнал виден в docker logs, docker stop — {:.1f} с, код 0".format(dt)]


def task11(j, ctx):
    build(j, ctx)
    image = j.prefix
    c = start(j, image)
    end = time.monotonic() + 15
    while time.monotonic() < end and "обработчик готов" not in logs(c):
        if not state(c).get("Running"):
            raise Fail(["контейнер не работает:"] + died(c))
        time.sleep(0.3)
    if "обработчик готов" not in logs(c):
        raise Fail(["за 15 с обработчик не напечатал «обработчик готов». docker logs:"]
                   + tail(logs(c), 4))
    problems = []
    r = docker("exec", c, "sh", "-c", 'test -d "${QUEUE_DIR:-/tmp/queue}"')
    if r.code != 0:
        problems.append("каталог очереди (QUEUE_DIR) не создан перед стартом обработчика")
    dt, ec = timed_stop(c)
    out = logs(c)
    if dt > 4:
        problems.append("docker stop -t 5 занял {:.1f} с: контейнер ждали весь тайм-аут".format(dt))
    if ec != 0:
        problems.append("код выхода {}{}".format(ec, " — контейнер убит SIGKILL" if ec == 137 else ""))
    if "graceful shutdown" not in out:
        problems.append("в docker logs нет «graceful shutdown» — обработчик не узнал, "
                        "что его останавливают. docker logs:")
        problems += tail(out, 3)
    if problems:
        raise Fail(problems)
    return ["docker stop — {:.1f} с, «graceful shutdown», код 0".format(dt)]


TASKS = {
    1: ("Порт проброшен, а сервис не отвечает", task1),
    2: ("Каждая сборка ставит зависимости заново", task2),
    3: ("Утилита не принимает аргументы", task3),
    4: ("Токен утёк вместе с образом", task4),
    5: ("Маленький сервис в огромном образе", task5),
    6: ("После перезапуска данные пропали", task6),
    7: ("Сервис падает при первом запуске", task7),
    8: ("Витрина не видит api, зато видит базу", task8),
    9: ("Сервис работает от root", task9),
    10: ("docker logs молчит", task10),
    11: ("docker stop ждёт, а потом убивает", task11),
}
COMPOSE_TASKS = (6, 7, 8)


# ─────────────────────────── запуск ───────────────────────────

def preflight(chosen):
    if not shutil.which("docker"):
        print("Не найдена команда docker. Поставьте Docker Desktop (macOS, Windows) "
              "или Docker Engine (Linux), см. README.")
        return False
    r = docker("info", "--format", "{{.ServerVersion}}", timeout=30)
    if r.code != 0 or not r.out.strip():
        text = r.both.lower()
        print("Docker не отвечает: {}".format(short(r.both, 200) or "docker info не сработал"))
        if "permission denied" in text:
            print("Нет прав на сокет Docker. Linux: sudo usermod -aG docker $USER, "
                  "затем выйти из сеанса и войти снова. Через sudo проверку не запускайте.")
        else:
            print("Запустите Docker Desktop (или на Linux: sudo systemctl start docker), "
                  "дождитесь, пока docker info заработает, и повторите.")
        return False
    if docker("buildx", "version", timeout=30).code != 0:
        print("Нет BuildKit (docker buildx): он нужен для docker build --secret и --progress=plain.")
        print("Docker Desktop: обновите. Linux: поставьте пакет docker-buildx-plugin.")
        return False
    if any(n in COMPOSE_TASKS for n in chosen) and docker("compose", "version", timeout=30).code != 0:
        print("Нет docker compose v2 (команда docker compose, через пробел). "
              "Linux: пакет docker-compose-plugin.")
        return False
    return True


def usage():
    me = Path(sys.argv[0]).name or "check.py"
    print("{}: проверка задач «сломанные контейнеры».".format(LAB))
    print("  python3 {}           все задачи".format(me))
    print("  python3 {} 3         только задача 3; можно несколько: 3 5 6".format(me))
    print("  python3 {} --clean   убрать то, что оставила прерванная проверка".format(me))
    print("На Windows вместо python3 — python или py.")
    for n, (title, _) in TASKS.items():
        print("  {:>2}. {}".format(n, title))


def on_term(signum, frame):
    raise KeyboardInterrupt


def main(argv):
    if any(a in ("-h", "--help", "help") for a in argv):
        usage()
        return 0
    if "--clean" in argv:
        return clean_everything() if preflight([]) else 2
    chosen = []
    for a in argv:
        if not a.isdigit() or int(a) not in TASKS:
            print("Нет задачи «{}». Задачи: {}.".format(a, ", ".join(map(str, TASKS))))
            return 2
        if int(a) not in chosen:
            chosen.append(int(a))
    chosen = chosen or list(TASKS)
    if not preflight(chosen):
        return 2
    try:
        signal.signal(signal.SIGTERM, on_term)
    except (ValueError, AttributeError):
        pass

    results = {}
    started = time.monotonic()
    for n in chosen:
        d = task_dir(n)
        if d is None:
            print("Задача {}: нет каталога задачи/{}-… — верните: из каталога курса bash lab11-docker/reset.sh {}".format(n, n, n))
            results[n] = None
            continue
        j = Janitor(n)
        t0 = time.monotonic()
        tty = sys.stdout.isatty()
        if tty:
            print("Задача {}: {} …".format(n, TASKS[n][0]), end="", flush=True)
        try:
            info = TASKS[n][1](j, fresh_copy(j, n))
            ok, lines = True, info
        except Fail as e:
            ok, lines = False, list(e.args[0])
        except KeyboardInterrupt:
            print("\nПрервано. Убираю за собой…", flush=True)
            j.clean()
            print("Убрано.")
            return 130
        try:
            j.clean()
        except KeyboardInterrupt:
            j.clean()
        print("{}Задача {}: {} ({:.0f} с){}".format("\r" if tty else "", n,
                                                  "PASS" if ok else "FAIL",
                                                  time.monotonic() - t0, " " * 40 if tty else ""))
        for line in lines + j.notes:
            print("  " + line)
        results[n] = ok

    solved = [n for n in chosen if results[n] is True]
    failed = [n for n in chosen if results[n] is False]
    summary = "Итог: решено {} из {}.".format(len(solved), len(chosen))
    if failed:
        summary += " Не прошли: {}.".format(", ".join(map(str, failed)))
    print()
    print(summary + " Время: {:.0f} с.".format(time.monotonic() - started))
    return 0 if len(solved) == len(chosen) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
