#!/usr/bin/env python3
"""Автопроверка занятия 3: хуки и проверки на стороне GitHub."""
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


def _repo_arg():
    """--repo ПУТЬ: где лежит клон вашего боевого репозитория.
    Задания 2 и 3 делаются там, а не здесь: Actions живут на GitHub."""
    for i, a in enumerate(sys.argv):
        if a == "--repo":
            nxt = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
            if not nxt or nxt.startswith("-"):
                print("FAIL: после --repo нужен путь к клону вашего репозитория, "
                      "например: ./check.py --repo ~/my-project")
                sys.exit(1)
            return Path(nxt).expanduser()
        if a.startswith("--repo="):
            value = a.split("=", 1)[1]
            if not value:
                print("FAIL: после --repo= нужен путь к клону вашего репозитория")
                sys.exit(1)
            return Path(value).expanduser()
    return None


REPO = _repo_arg()
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

WORKFLOWS = (REPO or ROOT) / ".github" / "workflows"
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

    base = REPO or ROOT
    relative = path.relative_to(base).as_posix()
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    problems = []
    listed = run(["git", "ls-files", "--", relative], cwd=base)
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
















def check_telegram():
    """Уведомление в Telegram: файл на месте, триггер переключён на push,
    токен и chat_id берутся из секретов, а не зашиты в файл."""
    path = WORKFLOWS / "telegram.yml"
    if not path.exists():
        return report(False, "", "создайте .github/workflows/telegram.yml — "
                                 "готовый файл есть в условии, его надо положить и поправить")
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = yaml_load(text)
    except Exception as error:
        return report(False, "", f"telegram.yml не читается как YAML: {error}")

    # Ключ on: в YAML 1.1 читается как булево True — учитываем оба написания.
    triggers = set()
    for key, value in (data.items() if isinstance(data, dict) else []):
        if str(key).strip().lower() in ("on", "true"):
            triggers |= _trigger_names(value)
    if "push" not in triggers:
        return report(False, "", "в telegram.yml триггер всё ещё pull_request: "
                                 "задание — переключить его на push")

    зашит = re.search(r'(?<!secrets\.)\b\d{8,}:[A-Za-z0-9_-]{30,}', text)
    if зашит:
        return report(False, "", "токен бота зашит прямо в файл — он должен приходить "
                                 "из secrets.TELEGRAM_BOT_TOKEN")
    нужны = [n for n in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
             if f"secrets.{n}" not in text]
    if нужны:
        return report(False, "", "в telegram.yml не хватает обращений к секретам: "
                                 + ", ".join(нужны))
    return report(True, "telegram.yml: триггер push, токен и chat_id из секретов", "")


def check_clean():
    ok = run(["git", "status", "--porcelain"]).stdout == ""
    return report(ok, "рабочее дерево чистое", "остались незакоммиченные изменения")


# --- необязательный тренажёр: обратный мердж ------------------------------

GITFLOW = ROOT.parent / "gitflow"


def _gf(*args):
    return run(["git", *args], cwd=GITFLOW)


def check_gitflow():
    if not (GITFLOW / ".git").is_dir():
        return report(False, "", f"не вижу тренажёр в {GITFLOW} — "
                                 "разверните: bash lab03-hooks/gitflow.sh")

    expected = (GITFLOW / ".opr-main-tip")
    if expected.is_file():
        want = expected.read_text().strip()
        have = _gf("rev-parse", "main").stdout.strip()
        if want != have:
            return report(False, "", "main изменился. Долг закрывают со стороны develop, "
                                     "main трогать не надо: верните его на " + want[:8])

    old_dev = (GITFLOW / ".opr-develop-tip")
    if old_dev.is_file():
        base = old_dev.read_text().strip()
        if _gf("merge-base", "--is-ancestor", base, "develop").returncode != 0:
            return report(False, "", "историю develop переписали: прежний коммит "
                                     f"{base[:8]} больше не её предок. Обратный мердж "
                                     "делается мерджем, а не rebase")

    if _gf("status", "--porcelain").stdout.strip():
        return report(False, "", "в тренажёре остались незакоммиченные изменения — "
                                 "долг не закрыт, пока мердж не зафиксирован")

    debt = _gf("log", "--oneline", "develop..main").stdout.strip()
    if debt:
        merged_branch = _gf("merge-base", "--is-ancestor",
                            "release/1.2", "develop").returncode == 0
        if merged_branch:
            return report(False, "", "влита сама release/1.2, а не тег v1.2: "
                                     "merge-коммит из main так и остался вне develop. "
                                     "Слейте v1.2 — через тег приезжает и то, что попало "
                                     "в main мимо релиза")
        return report(False, "", "долг не закрыт: в main есть "
                                 f"{len(debt.splitlines())} коммит(ов), которых нет в develop. "
                                 "Посмотрите git log --oneline develop..main")

    pay = _gf("show", "develop:pay.py").stdout
    if "if card is None" not in pay:
        return report(False, "", "в develop:pay.py нет проверки на None — "
                                 "фикс из релиза до develop не доехал")

    parents = _gf("rev-list", "--parents", "-n", "1", "develop").stdout.split()
    if len(parents) < 3:
        return report(False, "", "вершина develop — не merge-коммит. "
                                 "Фикс перенесли копией (cherry-pick?), а связь между "
                                 "ветками не записана: git снова не будет знать, что релиз влит")

    return report(True, "обратный мердж сделан: долг закрыт, история цела, "
                        "фикс в develop", "")


if "--gitflow" in sys.argv:
    sys.exit(0 if check_gitflow() else 1)


checks = [
    check_installed(),
    check_pre_commit(),
    check_commit_msg(),
    check_bypass(),
    check_clean(),
]

if REPO is None:
    print()
    print("Задания 2 и 3 делаются в вашем репозитории на GitHub, не здесь.")
    print("Когда положите туда оба workflow, проверьте их так:")
    print("    ./check.py --repo ПУТЬ-К-КЛОНУ-ВАШЕГО-РЕПОЗИТОРИЯ")
elif REPO.resolve() == ROOT.resolve():
    print()
    print("FAIL: --repo указывает на учебную лабу. Нужен ПУТЬ К ВАШЕМУ репозиторию "
          "на GitHub — тому, куда вы пушите и где работают Actions.")
    checks.append(False)
elif not (REPO / ".git").is_dir():
    print()
    print(f"FAIL: в {REPO} нет репозитория git — проверьте путь")
    checks.append(False)
else:
    checks.append(check_telegram())
    checks.append(check_workflow())

sys.exit(0 if all(checks) else 1)
