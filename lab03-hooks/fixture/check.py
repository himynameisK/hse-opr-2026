#!/usr/bin/env python3
"""Автопроверка занятия 3: хуки и подпись вебхука."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True

# На Windows вывод в пайп берёт кодировку системы (cp1251/cp866), и символы ₽ и —
# роняют проверку с UnicodeEncodeError вместо читаемого FAIL.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
ROOT = Path.cwd()
PYTHON = sys.executable
HOOKS = ROOT / ".githooks"
SECRET = "opr-2026-secret"


def run(command, cwd=ROOT, env_extra=None, stdin=None):
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if env_extra:
        environment.update(env_extra)
    return subprocess.run(
        command, cwd=cwd, env=environment, input=stdin, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok


def check_installed():
    configured = run(["git", "config", "--get", "core.hooksPath"]).stdout.strip()
    tracked = run(["git", "ls-files", ".githooks"]).stdout.split()
    ok = (
        configured == ".githooks"
        and ".githooks/pre-commit" in tracked
        and ".githooks/commit-msg" in tracked
        and os.access(HOOKS / "pre-commit", os.X_OK)
        and os.access(HOOKS / "commit-msg", os.X_OK)
    )
    return report(
        ok,
        "оба хука лежат в .githooks, закоммичены, исполняемы и включены",
        "нужны .githooks/pre-commit и .githooks/commit-msg: закоммиченные, chmod +x, "
        "и git config core.hooksPath .githooks",
    )


def sandbox():
    """Временный репозиторий с хуками студента."""
    directory = tempfile.mkdtemp()
    run(["git", "init", "-q", directory], cwd=Path(directory))
    for key, value in (("user.name", "Check"), ("user.email", "check@example.invalid"),
                       ("commit.gpgsign", "false"), ("core.hooksPath", str(HOOKS))):
        run(["git", "config", key, value], cwd=Path(directory))
    (Path(directory) / "seed.txt").write_text("seed\n")
    run(["git", "add", "seed.txt"], cwd=Path(directory))
    run(["git", "commit", "-q", "--no-verify", "-m", "SHOP-0 seed"], cwd=Path(directory))
    return Path(directory)


def commit_attempt(directory, files, message, no_verify=False):
    for name, content in files.items():
        (directory / name).write_text(content)
    run(["git", "add", "-A"], cwd=directory)
    command = ["git", "commit", "-m", message]
    if no_verify:
        command.insert(2, "--no-verify")
    before = run(["git", "rev-parse", "HEAD"], cwd=directory).stdout.strip()
    result = run(command, cwd=directory)
    after = run(["git", "rev-parse", "HEAD"], cwd=directory).stdout.strip()
    run(["git", "reset", "-q", "--hard", "HEAD"], cwd=directory)
    run(["git", "clean", "-qfd"], cwd=directory)
    return result.returncode == 0 and before != after


def check_pre_commit():
    if not os.access(HOOKS / "pre-commit", os.X_OK):
        return report(False, "", "сначала создайте исполняемый .githooks/pre-commit")
    directory = sandbox()
    try:
        blocked_env = not commit_attempt(
            directory, {".env": "SHOP_TOKEN=ghp_realtokenvalue123\n"}, "SHOP-1 Добавить конфиг")
        blocked_inline = not commit_attempt(
            directory, {"settings.py": 'API_KEY="AKIAIOSFODNN7EXAMPLE"\n'}, "SHOP-2 Настройки")
        allowed_clean = commit_attempt(
            directory, {"util.py": "def double(x):\n    return x * 2\n"}, "SHOP-3 Утилита")
        allowed_mention = commit_attempt(
            directory, {"README.md": "Не коммитьте токены и пароли.\n"}, "SHOP-4 Заметка")
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    ok = blocked_env and blocked_inline and allowed_clean and allowed_mention
    return report(
        ok,
        "pre-commit останавливает секреты и не мешает обычным коммитам",
        "pre-commit должен отклонять .env и строку вида API_KEY=\"...\", "
        "но пропускать код без секретов и текст, где слово «токен» просто упомянуто",
    )


def check_commit_msg():
    if not os.access(HOOKS / "commit-msg", os.X_OK):
        return report(False, "", "сначала создайте исполняемый .githooks/commit-msg")
    directory = sandbox()
    try:
        good = commit_attempt(directory, {"a.py": "a = 1\n"}, "SHOP-12 Добавить расчёт скидки")
        no_key = not commit_attempt(directory, {"b.py": "b = 1\n"}, "Добавить расчёт скидки")
        wrong = not commit_attempt(directory, {"c.py": "c = 1\n"}, "shop12 добавить скидку")
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    ok = good and no_key and wrong
    return report(
        ok,
        "commit-msg требует номер задачи в начале сообщения",
        "commit-msg должен принимать «SHOP-12 Текст» и отклонять сообщение без номера задачи",
    )


def check_bypass():
    if not os.access(HOOKS / "pre-commit", os.X_OK):
        return report(False, "", "сначала создайте .githooks/pre-commit")
    directory = sandbox()
    try:
        passed = commit_attempt(
            directory, {".env": "SHOP_TOKEN=ghp_realtokenvalue123\n"},
            "SHOP-5 Конфиг", no_verify=True)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    return report(
        passed,
        "хук обходится через --no-verify, и это нормально: он вежливость, а не защита",
        "с --no-verify коммит обязан пройти: хук не должен мешать git работать",
    )


def check_verify_script():
    script = ROOT / "verify.py"
    if not script.exists():
        return report(False, "", "создайте verify.py — проверку подписи X-Hub-Signature-256")
    cases = [("push-valid", True), ("pr-valid", True),
             ("pr-tampered", False), ("push-wrong-secret", False)]
    outcomes = []
    for name, expected in cases:
        body = (ROOT / "deliveries" / f"{name}.json").read_text()
        signature = (ROOT / "deliveries" / f"{name}.sig").read_text().strip()
        result = run([PYTHON, str(script)],
                     env_extra={"WEBHOOK_SECRET": SECRET, "X_HUB_SIGNATURE_256": signature},
                     stdin=body)
        outcomes.append((result.returncode == 0) == expected)
    ok = all(outcomes)
    return report(
        ok,
        "verify.py принимает обе честные доставки и отвергает подменённую и чужую",
        "verify.py читает тело из stdin, секрет из WEBHOOK_SECRET, подпись из "
        "X_HUB_SIGNATURE_256; код 0 — подпись верна, иначе не 0",
    )


def check_verify_is_constant_time():
    sources = []
    for name in ("verify.py", "notify.py"):
        script = ROOT / name
        if not script.exists():
            return report(False, "", "сначала создайте " + name)
        sources.append(script.read_text(encoding="utf-8", errors="replace"))
    ok = all("compare_digest" in source for source in sources)
    return report(
        ok,
        "сравнение подписи идёт через hmac.compare_digest",
        "сравнивать подписи оператором == нельзя: и в verify.py, и в notify.py "
        "используйте hmac.compare_digest",
    )


# --- разбор YAML своими руками -------------------------------------------
# Ставить PyYAML ради одного файла незачем, а в стандартной библиотеке его нет.
# Workflow — это отступы, пары «ключ: значение» и списки; разбираем ровно то
# подмножество, которого хватает GitHub Actions.


def _yaml_uncomment(line):
    """Отрезает # комментарий, не трогая решётку внутри кавычек."""
    out = []
    quote = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            out.append(char)
            if char == "\\" and quote == '"' and index + 1 < len(line):
                out.append(line[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            out.append(char)
        elif char == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(char)
        index += 1
    return "".join(out).rstrip()


def _yaml_scalar(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return text


def _yaml_split_flow(text):
    """Делит «a, b, {c: d}» по запятым верхнего уровня."""
    parts, current, quote, depth = [], [], None, 0
    for char in text:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def _yaml_split_pair(text):
    """Находит двоеточие, разделяющее ключ и значение. Иначе None."""
    quote, depth = None, 0
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == ":" and depth == 0 and (index + 1 == len(text) or text[index + 1] in " \t"):
            return text[:index], text[index + 1:]
    return None


def _yaml_value(text):
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        return [_yaml_value(item) for item in _yaml_split_flow(text[1:-1])]
    if text.startswith("{") and text.endswith("}"):
        mapping = {}
        for item in _yaml_split_flow(text[1:-1]):
            pair = _yaml_split_pair(item)
            if pair:
                mapping[_yaml_scalar(pair[0])] = _yaml_value(pair[1])
            elif item.strip():
                mapping[_yaml_scalar(item)] = None
        return mapping
    return _yaml_scalar(text)


class _YamlReader:
    def __init__(self, text):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.lines = text.split("\n")
        self.index = 0

    def peek(self):
        """Первая значащая строка: (отступ, текст без комментария)."""
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("%") \
                    or stripped in ("---", "..."):
                self.index += 1
                continue
            content = _yaml_uncomment(raw).strip()
            if not content:
                self.index += 1
                continue
            return len(raw) - len(raw.lstrip()), content
        return None

    def take_block_scalar(self, indent):
        """Съедает тело блочного скаляра (| и >), чтобы оно не сбило разбор."""
        chunks = []
        while self.index < len(self.lines):
            raw = self.lines[self.index]
            if raw.strip() and len(raw) - len(raw.lstrip()) <= indent:
                break
            chunks.append(raw.strip())
            self.index += 1
        return "\n".join(chunks).strip()


def _yaml_is_dash(text):
    return text == "-" or text.startswith("- ")


def _yaml_is_block_scalar(text):
    return len(text) > 0 and text[0] in "|>" and all(c in "+-0123456789" for c in text[1:])


def _yaml_node(reader, indent):
    item = reader.peek()
    if item is None or item[0] < indent:
        return None
    if _yaml_is_dash(item[1]):
        return _yaml_sequence(reader, item[0])
    return _yaml_mapping(reader, item[0])


def _yaml_sequence(reader, indent):
    result = []
    while True:
        item = reader.peek()
        if item is None or item[0] != indent or not _yaml_is_dash(item[1]):
            break
        content = item[1]
        tail = content[1:]
        offset = indent + 1 + (len(tail) - len(tail.lstrip()))
        rest = tail.strip()
        reader.index += 1
        if not rest:
            result.append(_yaml_node(reader, indent + 1))
            continue
        pair = _yaml_split_pair(rest)
        if pair:
            # «- uses: x» — отображение, которое начинается прямо за дефисом
            result.append(_yaml_mapping(reader, offset, first=pair))
        else:
            result.append(_yaml_value(rest))
    return result


def _yaml_mapping(reader, indent, first=None):
    result = {}
    pending = first
    while True:
        if pending is None:
            item = reader.peek()
            if item is None or item[0] != indent or _yaml_is_dash(item[1]):
                break
            pair = _yaml_split_pair(item[1])
            if pair is None:
                break
            reader.index += 1
            pending = pair
        key_text, value_text = pending
        pending = None
        key = _yaml_scalar(key_text)
        value_text = value_text.strip()
        if _yaml_is_block_scalar(value_text):
            result[key] = reader.take_block_scalar(indent)
        elif value_text:
            result[key] = _yaml_value(value_text)
        else:
            nested = reader.peek()
            if nested is None:
                result[key] = None
            elif _yaml_is_dash(nested[1]) and nested[0] >= indent:
                # список под ключом может стоять и без лишнего отступа
                result[key] = _yaml_sequence(reader, nested[0])
            elif nested[0] > indent:
                result[key] = _yaml_node(reader, nested[0])
            else:
                result[key] = None
    return result


def yaml_load(text):
    """Разбирает подмножество YAML: отображения, списки, скаляры, комментарии."""
    reader = _YamlReader(text.lstrip("﻿"))
    return _yaml_node(reader, 0)


# --- проверка workflow ----------------------------------------------------

WORKFLOWS = ROOT / ".github" / "workflows"
GITLEAKS_TAG = re.compile(r"v3(\.\d+)*\Z")


def _trigger_names(node):
    """on: push, on: [push, pull_request], on:\\n  push:\\n  pull_request: — одно и то же."""
    if isinstance(node, dict):
        return {str(key).strip().lower() for key in node}
    if isinstance(node, list):
        return {str(item).strip().lower() for item in node if isinstance(item, str)}
    if isinstance(node, str) and node.strip():
        return {node.strip().lower()}
    return set()


def _env_of(node):
    block = node.get("env") if isinstance(node, dict) else None
    if not isinstance(block, dict):
        return {}
    return {str(key).strip(): value for key, value in block.items()}


def _with_value(step, name):
    block = step.get("with")
    if not isinstance(block, dict):
        return None
    for key, value in block.items():
        if str(key).strip().lower() == name:
            return value
    return None


def _inspect_job(job, outer_env):
    """Что умеет джоб: checkout, глубина, экшен, токен."""
    job_env = dict(outer_env)
    job_env.update(_env_of(job))
    found = {"checkout": False, "depth": False, "gitleaks": False, "token": False,
             "depth_value": None, "wrong_tag": None}
    for step in job["steps"]:
        uses = step.get("uses") if isinstance(step, dict) else None
        if not isinstance(uses, str) or "@" not in uses:
            continue
        action, _, ref = uses.strip().partition("@")
        action, ref = action.strip().lower(), ref.strip()
        if action == "actions/checkout":
            found["checkout"] = True
            depth = _with_value(step, "fetch-depth")
            if depth is not None:
                found["depth_value"] = str(depth).strip()
            found["depth"] = found["depth"] or found["depth_value"] == "0"
        elif action == "gitleaks/gitleaks-action":
            if GITLEAKS_TAG.match(ref):
                found["gitleaks"] = True
                env = dict(job_env)
                env.update(_env_of(step))
                token = env.get("GITHUB_TOKEN")
                found["token"] = found["token"] or (isinstance(token, str) and bool(token.strip()))
            elif found["wrong_tag"] is None:
                found["wrong_tag"] = ref or "без тега"
    found["score"] = sum(1 for key in ("checkout", "depth", "gitleaks", "token") if found[key])
    return found


def check_workflow():
    path = None
    for name in ("gitleaks.yml", "gitleaks.yaml"):
        if (WORKFLOWS / name).is_file():
            path = WORKFLOWS / name
            break
    if path is None:
        return report(False, "", "создайте .github/workflows/gitleaks.yml — workflow, "
                                 "который ищет секреты в истории")

    relative = path.relative_to(ROOT).as_posix()
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    problems = []
    listed = run(["git", "ls-files", "--", relative])
    if listed.returncode != 0 or not listed.stdout.strip():
        problems.append(f"{relative} не закоммичен")
    # пустая строка, в которой остался таб, YAML не ломает — смотрим только на значащие
    if any("\t" in line[:len(line) - len(line.lstrip())]
           for line in text.splitlines() if line.strip()):
        problems.append("отступы сделаны табами — YAML понимает только пробелы")

    try:
        workflow = yaml_load(text)
    except Exception:
        workflow = None
    if not isinstance(workflow, dict):
        problems.append("файл не читается как YAML: нужны пары «ключ: значение» и отступы пробелами")
        return report(False, "", "; ".join(problems))

    triggers = set()
    for key, value in workflow.items():
        # YAML 1.1 считает «on» булевым, поэтому ключ могли написать и в кавычках
        if str(key).strip().lower() in ("on", "true"):
            triggers |= _trigger_names(value)
    missing = [name for name in ("push", "pull_request") if name not in triggers]
    if missing:
        problems.append("в on: не хватает триггеров: " + ", ".join(missing))

    # checkout и gitleaks обязаны жить в одном джобе: у соседнего джоба свой
    # рабочий каталог, и глубина клона ему ничем не поможет
    jobs = workflow.get("jobs")
    reports = [
        _inspect_job(job, _env_of(workflow))
        for job in (jobs.values() if isinstance(jobs, dict) else [])
        if isinstance(job, dict) and isinstance(job.get("steps"), list)
    ]
    if not reports:
        problems.append("в jobs: нет ни одного джоба со списком steps")
        return report(False, "", "; ".join(problems))

    best = max(reports, key=lambda found: found["score"])
    if not best["checkout"]:
        problems.append("в джобе с gitleaks нет шага actions/checkout"
                        if any(found["gitleaks"] for found in reports)
                        else "нет шага actions/checkout")
    elif not best["depth"]:
        problems.append(
            f"у actions/checkout fetch-depth: {best['depth_value']}, а нужен 0"
            if best["depth_value"] else
            "у actions/checkout нет with: fetch-depth: 0 — иначе в клоне один коммит, "
            "а секрет лежит в истории")
    if not best["gitleaks"]:
        problems.append(
            f"gitleaks-action взят с тегом {best['wrong_tag']}, а нужен v3"
            if best["wrong_tag"] else
            "в этом же джобе нет шага gitleaks/gitleaks-action@v3"
            if best["checkout"] else "нет шага gitleaks/gitleaks-action@v3")
    elif not best["token"]:
        problems.append("экшену не передан GITHUB_TOKEN через env: "
                        "(inputs у него нет, with: не поможет)")

    ok = not problems
    return report(
        ok,
        "workflow gitleaks: push и pull_request, checkout с fetch-depth: 0, экшен v3",
        "; ".join(problems),
    )


TELEGRAM_ENV = {
    "WEBHOOK_SECRET": SECRET,
    "TELEGRAM_BOT_TOKEN": "111111:TEST-TOKEN-AAA",
    "TELEGRAM_CHAT_ID": "-1001234567890",
}
TELEGRAM_KEYS = ("WEBHOOK_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def run_notify(delivery, env_extra, folder=None):
    """notify.py на записанной доставке. stderr не подмешиваем: stdout — это запрос."""
    folder = Path(folder) if folder else ROOT / "deliveries"
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    for key in TELEGRAM_KEYS:
        environment.pop(key, None)
    environment.update(env_extra)
    result = subprocess.run(
        [PYTHON, str(ROOT / "notify.py"),
         str(folder / (delivery + ".json")),
         str(folder / (delivery + ".sig"))],
        cwd=ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace",
    )
    return result.returncode, result.stdout


def multiline_delivery(directory):
    """Доставка с переводом строки в теле: такую переживает только чтение байтами."""
    body = (
        '{"action": "opened", "number": 7,\r\n'
        ' "pull_request": {"title": "SHOP-15 Хуки для магазина",\r\n'
        '  "user": {"login": "student"}, "changed_files": 3,\r\n'
        '  "additions": 61, "deletions": 4},\r\n'
        ' "repository": {"full_name": "student/opr-shop"}}'
    ).encode("utf-8")
    signature = "sha256=" + hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    (directory / "pr-multiline.json").write_bytes(body)
    # write_bytes, а не write_text: на Windows write_text подменил бы \n на \r\n.
    (directory / "pr-multiline.sig").write_bytes((signature + "\n").encode("ascii"))


def telegram_request(output):
    """Разбирает напечатанный запрос: строка «POST <url>», следом тело JSON."""
    lines = [line for line in output.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.strip().startswith("POST "):
            url = line.strip()[5:].strip().strip("\"'")
            try:
                body = json.loads("\n".join(lines[index + 1:]))
            except ValueError:
                return url, None
            return url, body if isinstance(body, dict) else None
    return None, None


def sends_to_telegram(output, token, chat_id):
    url, body = telegram_request(output)
    return (
        url == "https://api.telegram.org/bot" + token + "/sendMessage"
        and body is not None
        and str(body.get("chat_id", "")) == chat_id
        and str(body.get("text", "")).strip() != ""
    )


def check_notify():
    script = ROOT / "notify.py"
    if not script.exists():
        return report(False, "", "создайте notify.py — печать запроса в Telegram по доставке вебхука")
    code, output = run_notify("pr-valid", TELEGRAM_ENV)
    _, body = telegram_request(output)
    text = str(body.get("text", "")) if body else ""
    prints_call = (
        code == 0
        and sends_to_telegram(output, TELEGRAM_ENV["TELEGRAM_BOT_TOKEN"],
                              TELEGRAM_ENV["TELEGRAM_CHAT_ID"])
        and "student/opr-shop" in text
        and "7" in text
    )
    silent = []
    for delivery in ("pr-tampered", "push-wrong-secret"):
        code, output = run_notify(delivery, TELEGRAM_ENV)
        silent.append(code != 0 and "api.telegram.org" not in output)
    code, output = run_notify("push-valid", TELEGRAM_ENV)
    skips_push = code == 0 and "api.telegram.org" not in output
    directory = Path(tempfile.mkdtemp())
    try:
        multiline_delivery(directory)
        code, output = run_notify("pr-multiline", TELEGRAM_ENV, folder=directory)
        reads_bytes = code == 0 and sends_to_telegram(
            output, TELEGRAM_ENV["TELEGRAM_BOT_TOKEN"], TELEGRAM_ENV["TELEGRAM_CHAT_ID"])
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    ok = prints_call and all(silent) and skips_push and reads_bytes
    return report(
        ok,
        "notify.py печатает вызов sendMessage на честном pull request и молчит на остальных",
        "notify.py на pr-valid должен напечатать «POST https://api.telegram.org/bot<TOKEN>/sendMessage» "
        "и следом тело JSON с chat_id и text (в тексте — репозиторий и номер PR); "
        "на pr-tampered и push-wrong-secret — ни строчки запроса и код не 0; "
        "на push-valid — ни строчки запроса и код 0; тело доставки читается байтами "
        "(open(path, \"rb\"): при чтении текстом ломается подпись доставки с переводом строки)",
    )


def check_notify_secrets():
    script = ROOT / "notify.py"
    if not script.exists():
        return report(False, "", "сначала создайте notify.py")
    other = {"WEBHOOK_SECRET": SECRET,
             "TELEGRAM_BOT_TOKEN": "222222:OTHER-TOKEN-BBB",
             "TELEGRAM_CHAT_ID": "424242"}
    code, output = run_notify("pr-valid", other)
    follows_env = code == 0 and sends_to_telegram(
        output, other["TELEGRAM_BOT_TOKEN"], other["TELEGRAM_CHAT_ID"])
    refuses_empty = []
    for missing in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        partial = {key: value for key, value in TELEGRAM_ENV.items() if key != missing}
        code, output = run_notify("pr-valid", partial)
        refuses_empty.append(code != 0 and "api.telegram.org" not in output)
    source = script.read_text(encoding="utf-8", errors="replace")
    # Значение chat_id из README студент может честно переписать в комментарий,
    # поэтому его в исходнике не ищем: за это отвечают запуски выше.
    not_hardcoded = (TELEGRAM_ENV["TELEGRAM_BOT_TOKEN"] not in source
                     and ("environ" in source or "getenv" in source))
    ok = follows_env and all(refuses_empty) and not_hardcoded
    return report(
        ok,
        "токен и chat_id берутся из окружения, а не из репозитория",
        "TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID должны читаться из окружения: с другими "
        "значениями меняется и запрос, а без любой из них скрипт выходит с ненулевым "
        "кодом и ничего не печатает — без значения по умолчанию в коде",
    )


def check_clean():
    ok = run(["git", "status", "--porcelain"]).stdout == ""
    return report(ok, "рабочее дерево чистое", "остались незакоммиченные изменения")


checks = [
    check_installed(),
    check_pre_commit(),
    check_commit_msg(),
    check_bypass(),
    check_verify_script(),
    check_verify_is_constant_time(),
    check_notify(),
    check_notify_secrets(),
    check_workflow(),
    check_clean(),
]
sys.exit(0 if all(checks) else 1)
