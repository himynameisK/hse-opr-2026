#!/usr/bin/env python3
"""Автопроверка занятия 9: семь закладок в скрипте выкладки."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "deploy.sh"


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok


def sandbox(**kwargs):
    """Свежая копия данных и скрипта: каждый сценарий начинается с чистого листа."""
    box = Path(tempfile.mkdtemp(prefix="opr-lab09-"))
    app = box / "app"
    (app / "logs").mkdir(parents=True)
    (app / "releases" / "old").mkdir(parents=True)
    if kwargs.get("version", True):
        (app / "VERSION").write_text("2.4.1\n", encoding="utf-8")
    if kwargs.get("report", True):
        (app / "logs" / "report.txt").write_text(
            "ERROR база недоступна\nINFO всё хорошо\n", encoding="utf-8")
    (app / "logs" / "app.log").write_text("строка\n", encoding="utf-8")
    if kwargs.get("spaced", True):
        (app / "logs" / "my report.log").write_text("строка\n", encoding="utf-8")
    (app / "releases" / "old" / "release.txt").write_text("старый\n", encoding="utf-8")
    shutil.copy2(SCRIPT, box / "deploy.sh")
    os.chmod(box / "deploy.sh", 0o755)
    return box, app


def run(box, arg, timeout=30, stdin=None):
    try:
        done = subprocess.run(["/bin/bash", str(box / "deploy.sh")] + ([arg] if arg is not None else []),
                              cwd=str(box), timeout=timeout, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return done.returncode, done.stdout
    except subprocess.TimeoutExpired:
        return 124, "за 30 секунд не завершился"


def tail(text, n=1):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    return " / ".join(lines[-n:])[:160] if lines else "(тишина)"


# ── 1. strict mode ──────────────────────────────────────────────
def check_strict():
    text = SCRIPT.read_text(encoding="utf-8", errors="replace")
    has_e = re.search(r"^\s*set\s+-[a-z]*e", text, re.M)
    has_u = re.search(r"^\s*set\s+-[a-z]*u", text, re.M)
    has_pipe = re.search(r"^\s*set\s+-o\s+pipefail|^\s*set\s+-[a-z]*o\s+pipefail", text, re.M)
    missing = [n for n, v in (("-e", has_e), ("-u", has_u), ("pipefail", has_pipe)) if not v]
    return report(not missing,
                  "strict mode включён: -e, -u и pipefail на месте",
                  "в скрипте нет " + ", ".join(missing) +
                  " — без них ошибки проходят молча (set -euo pipefail)")


# ── 2. каталога нет ─────────────────────────────────────────────
def check_missing_dir():
    box, _ = sandbox()
    code, out = run(box, str(box / "нет-такого"))
    left = sorted(p.name for p in box.iterdir()) 
    shutil.rmtree(box, ignore_errors=True)
    return report(code != 0,
                  "несуществующий каталог: скрипт отказывается работать, код не ноль",
                  f"каталога нет, а скрипт вернул {code} и пошёл дальше: cd без проверки "
                  f"оставляет его в текущем каталоге. Последнее сказанное: {tail(out)}")


# ── 3. пустой аргумент ──────────────────────────────────────────
def check_empty_arg():
    box, app = sandbox()
    code, out = run(box, "")
    alive = (app / "releases" / "old" / "release.txt").exists()
    shutil.rmtree(box, ignore_errors=True)
    if code == 0:
        return report(False, "", "с пустым аргументом скрипт отработал как ни в чём не бывало "
                                 "(код 0). rm -rf с пустой переменной — это rm -rf /releases/old")
    return report(alive, "пустой аргумент: скрипт останавливается и ничего не удаляет",
                  "скрипт упал, но успел снести данные: проверять надо ДО удаления")


# ── 4. нет файла VERSION ────────────────────────────────────────
def check_version():
    box, app = sandbox(version=False)
    code, out = run(box, str(app))
    shutil.rmtree(box, ignore_errors=True)
    return report(code != 0,
                  "пропавший VERSION замечен: скрипт останавливается",
                  f"VERSION нет, cat упал, а скрипт продолжил с пустой версией и вернул {code}. "
                  f"Это конвейер без pipefail. Сказал: {tail(out)}")


# ── 5. имена с пробелами ────────────────────────────────────────
def check_spaces():
    box, app = sandbox()
    code, out = run(box, str(app))
    logs = app / "logs"
    gz = sorted(p.name for p in logs.glob("*.gz"))
    shutil.rmtree(box, ignore_errors=True)
    if code != 0:
        return report(False, "", f"обычный прогон упал с кодом {code}: {tail(out)}")
    ok = "my report.log.gz" in gz and "app.log.gz" in gz
    return report(ok, "сжаты оба журнала, включая «my report.log»",
                  f"сжато только {gz or 'ничего'} — имя с пробелом развалилось на два аргумента. "
                  f"for f in $(ls ...) так всегда и ломается")


# ── 6. временный файл ───────────────────────────────────────────
def check_tmp():
    box, app = sandbox()
    # Снимок всего /tmp: ловим и фиксированные имена, и забытые mktemp.
    before = set(Path("/tmp").iterdir())
    code, out = run(box, str(app))
    left = {p for p in Path("/tmp").iterdir() if p not in before
            and not p.name.startswith("opr-lab09-")}
    for p in left:
        try:
            p.unlink() if p.is_file() else shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass
    shutil.rmtree(box, ignore_errors=True)
    if code != 0:
        return report(False, "", f"обычный прогон упал с кодом {code}: {tail(out)}")
    return report(not left,
                  "после работы мусора в /tmp не осталось",
                  "в /tmp остались " + ", ".join(sorted(p.name for p in left)) +
                  " — временный файл никто не убрал. mktemp плюс trap ... EXIT")


# ── 7. пустая переменная и хитрый код возврата grep ────────────
def check_empty_test():
    # (а) отчёта нет — это ошибка, скрипт обязан остановиться
    box, app = sandbox(report=False)
    code, out = run(box, str(app))
    shutil.rmtree(box, ignore_errors=True)
    if "unary operator" in out:
        return report(False, "", "сравнение разваливается на пустой переменной: "
                                 "[ $STATUS = 0 ] без кавычек превращается в [ = 0 ]")
    if code == 0:
        return report(False, "", "report.txt нет, а скрипт вернул 0: ошибка прошла незамеченной")

    # (б) отчёт есть, но ERROR в нём нет — это НЕ ошибка, grep -c просто вернёт 1
    box, app = sandbox()
    (app / "logs" / "report.txt").write_text("INFO всё хорошо\n", encoding="utf-8")
    code, out = run(box, str(app))
    shutil.rmtree(box, ignore_errors=True)
    if code != 0:
        return report(False, "", f"отчёт без единого ERROR уронил скрипт (код {code}): "
                                 f"grep -c возвращает 1, когда совпадений ноль, и со set -e "
                                 f"это выглядит как авария. Сказал: {tail(out)}")
    return report(True, "отсутствующий отчёт замечен, а отчёт без ошибок скрипт не пугает", "")


checks = [
    check_strict(),
    check_missing_dir(),
    check_empty_arg(),
    check_version(),
    check_spaces(),
    check_tmp(),
    check_empty_test(),
]
print()
print(f"Сдано {sum(checks)} из {len(checks)}")
sys.exit(0 if all(checks) else 1)
