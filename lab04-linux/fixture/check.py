#!/usr/bin/env python3
"""Автопроверка занятия 4: права, файловые дескрипторы, общий каталог."""
import grp
import hashlib
import os
import pwd
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


if os.geteuid() != 0:
    print("Проверку запускать от root: ей нужен su, чтобы работать за opr,")
    print("за alice, за bob и за carol.  sudo /opt/opr-lab04/check.py")
    sys.exit(2)


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok

# ═══════════════ задание: script ═══════════════
ROOT = Path(__file__).resolve().parent
STUDENT = "opr"
WORDS = {"s1": "ok-1", "s2": "ok-2", "s3": "ok-3", "s4": "ok-4", "s5": "ok-5"}


class Outcome:
    """Что ответил запуск: код возврата и оба потока как есть."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr




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
        "все пять каталогов целы",
        "; ".join(problems),
    )


def printed_word(result):
    """Перевод строки отрезаем, возврат каретки — нет: он и есть поломка номер два."""
    return result.stdout.strip(" \t\n")


def check_plain(name):
    """s1, s2, s4, s5 — сдаются одинаково: ./sN/script.sh печатает своё слово."""
    word = WORDS[name]
    script = f"./{name}/script.sh"
    result = as_student(script)
    ok = result.returncode == 0 and printed_word(result) == word
    printed = printed_word(result).replace("\r", "^M")
    return report(
        ok,
        f"{script} запускается от {STUDENT} и печатает {word}",
        f"{script} от имени {STUDENT} не напечатал {word}: "
        + (f"вместо этого «{printed}»" if printed else f"«{complaint(result)}»"),
    )


def reseed_noexec_word():
    """Кладёт в s3/script.sh свежее слово: run.sh обязан его запускать, а не знать."""
    target = (ROOT / "s3" / "script.sh").resolve()
    if not target.is_file():
        return None, ("s3/script.sh больше никуда не ведёт: раздел с noexec пропал "
                      "(так бывает после перезагрузки) — разверните лабу заново через setup.sh")
    # Запрет на execve обязан быть на месте. Если ссылку подменили обычным файлом,
    # задача про noexec просто исчезла, и проверять в s3 больше нечего.
    if as_student("exec " + shlex.quote(str(target))).returncode == 0:
        return None, ("s3/script.sh больше не лежит на разделе с noexec: похоже, ссылку "
                      "заменили обычным файлом. Копию делает run.sh в момент запуска, "
                      "а не вы вместо ссылки — разверните лабу заново через setup.sh")
    data = target.read_bytes()
    word = "ok-3-" + secrets.token_hex(2)
    fresh, count = re.subn(rb"ok-3(-[0-9a-f]{4})?", word.encode("ascii"), data)
    if not count:
        return None, ("в s3/script.sh не осталось слова ok-3: верните файл как был "
                      "(разверните лабу заново через setup.sh)")
    with open(target, "r+b") as handle:
        handle.write(fresh)
        handle.truncate()
    return word, None


def check_noexec():
    runner = ROOT / "s3" / "run.sh"
    if not runner.is_file():
        return report(False, "", "нет s3/run.sh — скрипт, который запускает s3/script.sh "
                                 "и печатает его слово")
    word, trouble = reseed_noexec_word()
    if word is None:
        return report(False, "", trouble)
    result = as_student("./run.sh", cwd=ROOT / "s3")
    ok = result.returncode == 0 and printed_word(result) == word
    printed = printed_word(result).replace("\r", "^M")
    if not ok and printed.startswith("ok-3"):
        detail = (f"напечатал «{printed}», а script.sh в этот раз печатает «{word}»: "
                  "значит run.sh печатает слово сам или запускает старую копию — "
                  "копировать и запускать надо внутри run.sh")
    elif printed:
        detail = f"напечатал «{printed}», а ждали «{word}»"
    else:
        detail = f"«{complaint(result)}»"
    return report(
        ok,
        f"s3/run.sh запускает script.sh с раздела noexec и печатает его слово ({word})",
        "cd s3 && ./run.sh от имени " + STUDENT + " не сработал: " + detail,
    )


# ═══════════════ задание: proc ═══════════════
# В голом контейнере локаль может быть C, и тогда русский вывод падает
# с UnicodeEncodeError вместо читаемого FAIL.

def check_environment_sgid():
    problems = []
    if not SHARED.is_dir():
        problems.append(f"нет каталога {SHARED}")
    try:
        grp.getgrnam(GROUP)
    except KeyError:
        problems.append(f"нет группы {GROUP}")
    for user in USERS:
        try:
            pwd.getpwnam(user)
        except KeyError:
            problems.append(f"нет пользователя {user}")
            continue
        if not in_group(user, GROUP):
            problems.append(f"{user} не состоит в группе {GROUP}")
        elif primary_group(user) == GROUP:
            # Иначе наследование группы у файлов вышло бы само собой, и SGID
            # на каталоге было бы ни при чём: проверка потеряла бы смысл.
            problems.append(f"у {user} сделали {GROUP} основной группой — верните "
                            f"как было (usermod -g {user} {user}) или разверните "
                            f"занятие заново: группу файлам должен отдавать "
                            f"каталог, а не пользователь")
    ok = not problems
    return report(
        ok,
        f"каталог {SHARED} на месте, alice и bob состоят в группе {GROUP}",
        "; ".join(problems),
    )


def check_create_and_read():
    problem = not_ready()
    if problem:
        return report(False, "", problem)
    clear_shared()
    created, read_foreign = {}, {}
    for user in USERS:
        code, _ = as_user(
            user, f"printf 'строка от {user}\\n' > {SHARED}/{user}.txt")
        created[user] = code == 0 and (SHARED / f"{user}.txt").is_file()
    for reader, author in (("bob", "alice"), ("alice", "bob")):
        if not created.get(author):
            read_foreign[reader] = False
            continue
        code, output = as_user(reader, f"cat {SHARED}/{author}.txt")
        read_foreign[reader] = code == 0 and f"строка от {author}" in output
    ok = all(created.values()) and all(read_foreign.values())
    cannot_create = [user for user in USERS if not created[user]]
    return report(
        ok,
        "alice и bob создают файлы в общем каталоге и читают файлы друг друга",
        f"не может создать файл в каталоге: {', '.join(cannot_create)} — сейчас "
        f"{SHARED} это {described(SHARED)}, а группе {GROUP} нужны rwx"
        if cannot_create else
        "файл, созданный одним, не читается другим: группе нужен доступ и в каталог, "
        "и к файлам в нём",
    )


def check_group_inherited():
    problem = not_ready()
    if problem:
        return report(False, "", problem)
    clear_shared()
    code, _ = as_user("alice", f"printf 'наследование\\n' > {SHARED}/inherit.txt")
    created = SHARED / "inherit.txt"
    if code != 0 or not created.is_file():
        return report(False, "", "alice не может создать файл в каталоге — "
                                 "сначала добейтесь PASS на предыдущей проверке")
    actual = group_of(created)
    ok = actual == GROUP
    reason = (
        f"каталог принадлежит группе {group_of(SHARED)}, а должен {GROUP}: "
        f"наследуется та группа, что стоит на каталоге"
        if group_of(SHARED) != GROUP else
        f"на каталоге нет бита SGID (сейчас {described(SHARED)}), и новый файл "
        f"забирает основную группу того, кто его создал"
    )
    return report(
        ok,
        f"файл, созданный в каталоге, достаётся группе {GROUP}, а не создателю",
        f"файл alice получил группу {actual}, а должен {GROUP} — {reason}",
    )


def check_foreign_files_survive():
    problem = not_ready()
    if problem:
        return report(False, "", problem)
    clear_shared()
    for user in USERS:
        code, _ = as_user(user, f"printf 'файл {user}\\n' > {SHARED}/{user}.txt")
        if code != 0 or not (SHARED / f"{user}.txt").is_file():
            return report(False, "", f"{user} не может создать файл в каталоге — "
                                     "сначала добейтесь PASS на предыдущей проверке")
    kept, removed = {}, {}
    for actor, author in (("bob", "alice"), ("alice", "bob")):
        code, _ = as_user(actor, f"rm -f {SHARED}/{author}.txt")
        kept[actor] = code != 0 and (SHARED / f"{author}.txt").is_file()
    for user in USERS:
        code, _ = as_user(user, f"rm -f {SHARED}/{user}.txt")
        removed[user] = code == 0 and not (SHARED / f"{user}.txt").exists()
    ok = all(kept.values()) and all(removed.values())
    lost = [f"{author}.txt" for actor, author in (("bob", "alice"), ("alice", "bob"))
            if not kept[actor]]
    info = SHARED.stat()
    owner = user_name(info.st_uid)
    if not lost:
        failure = ("свой собственный файл должен удаляться, а он не удалился: "
                   f"у группы {GROUP} должны остаться rwx на каталоге")
    elif not info.st_mode & stat.S_ISVTX:
        failure = (f"чужой файл удалился: {', '.join(lost)} — в общем каталоге нужен "
                   "sticky-бит, иначе право на запись в каталог разрешает стереть "
                   "что угодно")
    elif owner in USERS:
        # Классическая ловушка: sticky стоит, а каталог отдали одному из двоих.
        failure = (f"чужой файл удалился: {', '.join(lost)} — sticky-бит на месте, "
                   f"но каталог принадлежит пользователю {owner}, а владельцу "
                   f"каталога sticky удалять не мешает. Каталог должен остаться "
                   f"за root (сейчас {described(SHARED)})")
    else:
        failure = (f"чужой файл удалился: {', '.join(lost)} — сейчас "
                   f"{SHARED} это {described(SHARED)}")
    return report(ok, "чужой файл удалить не выходит, свой удаляется", failure)


def check_outsider():
    problem = not_ready()
    if problem:
        return report(False, "", problem)
    try:
        pwd.getpwnam(OUTSIDER)
    except KeyError:
        return report(False, "", f"нет пользователя {OUTSIDER} — она в занятии за "
                                 f"постороннюю; разверните заново: sudo bash setup.sh")
    if in_group(OUTSIDER, GROUP):
        return report(False, "", f"{OUTSIDER} оказалась в группе {GROUP} — она "
                                 f"посторонняя, уберите её оттуда или разверните "
                                 f"занятие заново")
    clear_shared()
    code, _ = as_user("alice", f"printf 'секрет\\n' > {SHARED}/alice.txt")
    if code != 0 or not (SHARED / "alice.txt").is_file():
        return report(False, "", "alice не может создать файл в каталоге — "
                                 "сначала добейтесь PASS на предыдущих проверках")
    listed, _ = as_user(OUTSIDER, f"ls {SHARED}")
    read, _ = as_user(OUTSIDER, f"cat {SHARED}/alice.txt")
    wrote, _ = as_user(OUTSIDER, f"printf 'я тут был\\n' > {SHARED}/{OUTSIDER}.txt")
    managed = []
    if listed == 0:
        managed.append("смотрит список файлов")
    if read == 0:
        managed.append("читает чужой файл")
    if wrote == 0:
        managed.append("создаёт свои файлы")
    ok = not managed
    return report(
        ok,
        f"{OUTSIDER} в группе {GROUP} не состоит и в каталог не попадает",
        f"{OUTSIDER} в группе {GROUP} не состоит, а всё равно {', '.join(managed)} — "
        f"сейчас {SHARED} это {described(SHARED)}, и последняя тройка битов не "
        f"должна давать посторонним ничего",
    )



checks = [
    # script
    check_plain("s1"),
    check_plain("s2"),
    check_noexec(),
    check_plain("s4"),
    check_plain("s5"),
    # sgid
    check_environment_sgid(),
    check_create_and_read(),
    check_group_inherited(),
    check_foreign_files_survive(),
    check_outsider(),
]
clear_shared()
sys.exit(0 if all(checks) else 1)
