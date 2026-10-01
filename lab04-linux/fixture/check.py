#!/usr/bin/env python3
"""Автопроверка занятия 4: четыре заявки дежурной смены."""
import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


if os.geteuid() != 0:
    print("Проверку запускать от root: ей нужен su, чтобы работать за opr.")
    print("  sudo /opt/opr-lab04/check.py")
    sys.exit(2)


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok

# ═══════════════ задание: script ═══════════════
ROOT = Path(__file__).resolve().parent
STUDENT = "opr"
WORDS = {"t1": "ok-1", "t2": "ok-2", "t3": "ok-3"}
PATHS = {"t1": "./t1/script.sh", "t2": "./t2/script.sh", "t3": "./t3/config/script.sh"}
CACHE = Path("/srv/cache")
KEEP = ("data/report-2026-09.csv", "data/report-2026-08.csv", "data/service.conf")


class Outcome:
    """Что ответил запуск: код возврата и оба потока как есть."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr




def as_user(user, command):
    """Выполняет команду от имени пользователя. Возвращает (код возврата, вывод)."""
    result = subprocess.run(
        ["su", "-", user, "-c", "umask 022; " + command],
        cwd="/", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return result.returncode, result.stdout.strip()


def as_student(command, cwd=None):
    """Запускает строку через bash от имени opr.

    От root проверять нельзя: root обходит права на каталоги, и часть поломок
    просто не воспроизводится.
    """
    runuser = shutil.which("runuser") or "/usr/sbin/runuser"
    if os.path.exists(runuser):
        argv = [runuser, "-u", STUDENT, "--", "/bin/bash", "-c", command]
    else:
        argv = ["su", STUDENT, "-s", "/bin/bash", "-c", command]
    environment = os.environ.copy()
    environment["LC_ALL"] = "C.UTF-8"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    # Читаем байтами: в текстовом режиме Python сам превратит \r\n в \n,
    # а нам как раз надо видеть возврат каретки в выводе.
    try:
        done = subprocess.run(
            argv, cwd=str(cwd or ROOT), env=environment, timeout=20,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        return Outcome(124, "", "за 20 секунд не завершился — похоже, скрипт зациклился")
    return Outcome(
        done.returncode,
        done.stdout.decode("utf-8", "replace"),
        done.stderr.decode("utf-8", "replace"),
    )


def complaint(result):
    """Последняя строка ошибки — то, что студент и сам увидит в терминале."""
    lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    if not lines:
        return f"ничего не сказал, код возврата {result.returncode}"
    return lines[-1][:200]


def check_environment_script():
    problems = []
    if os.geteuid() != 0:
        problems.append("проверку запускают от root: sudo ./check.py")
    try:
        pwd.getpwnam(STUDENT)
    except KeyError:
        problems.append(f"нет пользователя {STUDENT}: разверните лабу заново через setup.sh")
    missing = [name for name in sorted(WORDS) if not (ROOT / name).exists()]
    if missing:
        problems.append("пропали каталоги: " + ", ".join(missing))
    ok = not problems
    return report(
        ok,
        f"окружение на месте: проверка идёт от root, запускает всё от {STUDENT}, "
        "все каталоги заявок целы",
        "; ".join(problems),
    )


def printed_word(result):
    """Перевод строки отрезаем, возврат каретки — нет: он и есть поломка номер два."""
    return result.stdout.strip(" \t\n")


def check_plain(name):
    """Заявки 1-3 сдаются одинаково: скрипт печатает своё слово."""
    word = WORDS[name]
    script = PATHS[name]
    result = as_student(script)
    ok = result.returncode == 0 and printed_word(result) == word
    printed = printed_word(result).replace("\r", "^M")
    return report(
        ok,
        f"{script} запускается от {STUDENT} и печатает {word}",
        f"{script} от имени {STUDENT} не напечатал {word}: "
        + (f"вместо этого «{printed}»" if printed else f"«{complaint(result)}»"),
    )


def check_inodes():
    """Заявка 4: на /srv/cache кончились inode, а байты свободны."""
    if not CACHE.is_dir():
        return report(False, "", f"нет каталога {CACHE} — заявка 4 не развернулась. "
                                 "Нужен loop-mount: в ВМ и WSL он есть, "
                                 "в контейнере нужен флаг --privileged")
    info = os.statvfs(CACHE)
    if info.f_files > 4096:
        return report(False, "", f"{CACHE} это уже не тот раздел: inode в нём "
                                 f"{info.f_files}, а было 256. Раздел пересоздавать "
                                 "не надо — надо понять, что именно их съело")
    lost = [k for k in KEEP if not (CACHE / k).is_file()]
    if lost:
        return report(False, "", "вместе с мусором удалены нужные данные: "
                                 + ", ".join(lost)
                                 + " — чистить надо было выборочно")
    probe = CACHE / ".probe-opr"
    code, _ = as_user(STUDENT, f"touch {probe}")
    ok = code == 0
    if ok:
        try: probe.unlink()
        except OSError: pass
    return report(
        ok,
        f"на {CACHE} снова создаются файлы, а отчёты и конфиг целы "
        f"(свободно inode: {info.f_favail} из {info.f_files})",
        f"на {CACHE} по-прежнему не создать файл: свободно inode "
        f"{info.f_favail} из {info.f_files}. Место при этом есть — "
        f"посмотрите df и df -i рядом",
    )


checks = [
    check_environment_script(),
    check_plain("t1"),
    check_plain("t2"),
    check_plain("t3"),
    check_inodes(),
]
sys.exit(0 if all(checks) else 1)
