#!/usr/bin/env python3
"""Автопроверка занятия 3: хуки и подпись вебхука."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
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
    script = ROOT / "verify.py"
    if not script.exists():
        return report(False, "", "сначала создайте verify.py")
    source = script.read_text()
    ok = "compare_digest" in source
    return report(
        ok,
        "сравнение подписи идёт через hmac.compare_digest",
        "сравнивать подписи оператором == нельзя: используйте hmac.compare_digest",
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
    check_clean(),
]
sys.exit(0 if all(checks) else 1)
