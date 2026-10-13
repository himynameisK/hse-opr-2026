#!/usr/bin/env python3
"""Автопроверка занятия 5: четыре заявки дежурной смены."""
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

# Без этого на машине с LANG=C русский текст в FAIL падает UnicodeEncodeError
# вместо того, чтобы читаться.
for _s in (sys.stdout, sys.stderr):
    try: _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass


if os.geteuid() != 0:
    print("Проверку запускать от root: ей нужны чужие /proc, systemctl и /var/lock.")
    print("  sudo /opt/opr-lab05/check.py")
    sys.exit(2)


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok


def skip(why):
    """Заявка, которую на этой машине сделать нельзя. Не зачёт и не провал:
    на код возврата не влияет, чтобы студент в контейнере не видел FAIL
    за то, чего от него не зависит."""
    print(f"ПРОПУСК: {why}")
    return True


STATE = Path("/var/lib/opr-lab05/state")


def load_state():
    """Что записали части setup.sh: пути, pid служб, размер и sha256 эталона."""
    state = {}
    try:
        text = STATE.read_text(encoding="utf-8")
    except OSError:
        return {}
    for line in text.splitlines():
        key, sign, value = line.partition("=")
        if sign:
            state[key.strip()] = value.strip()
    return state


def proc_fields(pid):
    """Состояние, PPID и время старта из /proc/<pid>/stat.

    Имя процесса в скобках может содержать пробелы, поэтому режем по последней
    «) », а не по первому пробелу.
    """
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fields = raw.rsplit(") ", 1)[-1].split()
    if len(fields) < 20:
        return None
    return {"state": fields[0], "ppid": fields[1], "starttime": fields[19]}


def starttime(pid):
    """Время старта процесса: по нему проверка отличит тот самый процесс
    от нового, которому достался освободившийся pid."""
    fields = proc_fields(pid)
    return fields["starttime"] if fields else None


def deleted_fd(pid, log):
    """Номер дескриптора, которым процесс держит удалённый журнал. Иначе None."""
    try:
        names = os.listdir(f"/proc/{pid}/fd")
    except OSError:
        return None
    for name in sorted(names, key=lambda item: int(item) if item.isdigit() else -1):
        try:
            target = os.readlink(f"/proc/{pid}/fd/{name}")
        except OSError:
            continue
        if target == log + " (deleted)":
            return name
    return None


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ═══════════════ окружение ═══════════════

def check_state(state):
    missing = [k for k in ("log", "restored", "pid", "starttime", "size", "sha256")
               if k not in state]
    return report(
        not missing,
        "состояние занятия на месте: setup.sh отработал",
        f"не читается {STATE}" if not state
        else "в состоянии занятия нет ключей: " + ", ".join(missing)
             + " — разверните лабу заново через reset.sh",
    )


# ═══════════════ заявка 1: журнал, которого нет ═══════════════

def check_holder(state):
    if not {"pid", "log", "starttime"} <= set(state):
        return report(False, "", "сначала запустите setup.sh")
    pid, log = state["pid"], state["log"]
    current = starttime(pid)
    if current is None:
        return report(False, "", f"процесса {pid} больше нет: службу убили, и вместе "
                                 f"с последним дескриптором ушло содержимое журнала. "
                                 f"Восстанавливать нечего — запустите reset.sh, "
                                 f"журнал будет другим")
    if current != state["starttime"]:
        return report(False, "", f"pid {pid} занят другим процессом: тот, что держал "
                                 f"журнал открытым, уже умер. Запустите reset.sh")
    number = deleted_fd(pid, log)
    if number is None:
        return report(False, "", f"процесс {pid} жив, но {log} у него больше не открыт: "
                                 f"дескриптор закрыт, данные освобождены. "
                                 f"Запустите reset.sh")
    return report(
        True,
        f"служба жива (pid {pid}), удалённый журнал всё ещё открыт на дескрипторе {number}",
        "",
    )


def check_restored_size(state):
    if not {"restored", "size"} <= set(state):
        return report(False, "", "сначала запустите setup.sh")
    restored, size = Path(state["restored"]), int(state["size"])
    if restored.is_symlink():
        return report(False, "", f"{restored} — символическая ссылка, а не копия: когда "
                                 f"служба закроет дескриптор, читать по ней будет нечего. "
                                 f"Нужен обычный файл")
    if not restored.is_file():
        return report(False, "", f"нет файла {restored}: восстановите туда содержимое "
                                 f"журнала через /proc/<pid>/fd/<номер>")
    actual = restored.stat().st_size
    return report(
        actual == size,
        f"{restored} на месте, обычный файл, размер совпал ({size} байт)",
        f"в {restored} {actual} байт, а в журнале было {size}: "
        + ("скопировалось не всё" if actual < size else "в копию попало лишнее"),
    )


def check_restored_content(state):
    if not {"restored", "sha256"} <= set(state):
        return report(False, "", "сначала запустите setup.sh")
    restored = Path(state["restored"])
    if restored.is_symlink() or not restored.is_file():
        return report(False, "", f"нет обычного файла {restored}: сверять нечего")
    actual = sha256_of(restored)
    return report(
        actual == state["sha256"],
        "содержимое совпало с эталоном побайтово: sha256 тот же",
        f"sha256 не сошёлся: у вас {actual[:16]}…, ожидается {state['sha256'][:16]}…; "
        f"содержимое изменилось по дороге — копируйте файл целиком, а не через "
        f"редактор и не через буфер обмена",
    )


# ═══════════════ заявка 2: история панели tmux ═══════════════

def check_scrollback(state):
    answer = Path(state.get("answer", "/var/tmp/opr-lab05/checksum.txt"))
    expected = state.get("answer_sha256")
    if not expected:
        return report(False, "", "в состоянии занятия нет эталона контрольной суммы: "
                                 "разверните лабу заново через reset.sh")
    if answer.is_symlink() or not answer.is_file():
        return report(False, "", f"нет файла {answer}: контрольная сумма лежит в истории "
                                 f"панели одной из сессий tmux — её надо найти "
                                 f"и записать сюда")
    text = answer.read_text(encoding="utf-8", errors="replace")
    tokens = re.findall(r"[0-9a-fA-F]{8,}", text)
    for token in tokens:
        if hashlib.sha256(token.lower().encode()).hexdigest() == expected:
            return report(True, f"контрольная сумма из истории панели лежит в {answer}", "")
    if not tokens:
        return report(False, "", f"в {answer} нет ничего похожего на контрольную сумму: "
                                 f"нужна строка из истории панели, а не пересказ")
    return report(False, "", f"в {answer} сумма не та: это не то значение, которое "
                             f"печатал вчерашний пересчёт. Сессий четыре, и история "
                             f"панели читается целиком: tmux capture-pane -p -S - -t ИМЯ")


# ═══════════════ заявка 3: зомби ═══════════════

def zombies_of(ppid):
    """Записи в состоянии Z, у которых указанный процесс числится родителем."""
    found = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        fields = proc_fields(entry.name)
        if fields and fields["state"] == "Z" and fields["ppid"] == str(ppid):
            found.append(entry.name)
    return found


def check_zombies(state):
    pid = state.get("collector_pid")
    user = state.get("collector_user", "opr")
    script = state.get("report")
    if not pid or not pid.isdigit() or not script:
        return report(False, "", "в состоянии занятия нет сборщика: "
                                 "разверните лабу заново через reset.sh")
    left = zombies_of(pid)
    if left:
        return report(False, "", f"зомби на месте: {len(left)} записей с родителем {pid} "
                                 f"(ps -u {user} -o pid,ppid,stat,args). По самим зомби "
                                 f"kill не работает — процесса за записью уже нет, "
                                 f"умирать некому. Разбираться надо с тем, "
                                 f"кто не забрал их коды возврата")
    # Симптом заявки — не сами зомби, а то, что у пользователя перестало
    # запускаться что-либо ещё: места в таблице процессов заняты.
    try:
        done = subprocess.run(["su", "-s", "/bin/bash", user, "-c", script],
                              timeout=60, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True)
    except subprocess.TimeoutExpired:
        return report(False, "", f"{script} от имени {user} не завершился за минуту")
    if done.returncode != 0 or "ok-3" not in done.stdout:
        last = [l for l in done.stdout.splitlines() if l.strip()]
        return report(False, "", f"{script} от имени {user} по-прежнему не работает "
                                 f"(код {done.returncode}): "
                                 + (last[-1][:160] if last else "ok-3 не напечатан"))
    alive = starttime(pid) == state.get("collector_starttime")
    return report(
        True,
        f"таблица процессов {user} свободна, выгрузка снова запускается"
        + (f"; сборщик (pid {pid}) при этом жив — коды возврата кто-то всё-таки забрал"
           if alive else f"; сборщика (pid {pid}) остановили, записи его детей забрал PID 1"),
        "",
    )


# ═══════════════ заявка 4: API из tmux в systemd ═══════════════

def ancestors(pid):
    """Цепочка родителей до PID 1 включительно."""
    chain = []
    seen = set()
    while pid and pid != "0" and pid not in seen:
        seen.add(pid)
        fields = proc_fields(pid)
        if not fields:
            break
        chain.append(pid)
        pid = fields["ppid"]
    return chain[1:]


def cmdline(pid):
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()


def processes_with(needle):
    found = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit() and needle in cmdline(entry.name):
            found.append(entry.name)
    return found


def unit_of(pid):
    """Юнит, в чьей cgroup живёт процесс. Имя юнита студент выбирает сам,
    поэтому спрашиваем не systemd про имя, а процесс про свою cgroup."""
    try:
        raw = Path(f"/proc/{pid}/cgroup").read_text(encoding="utf-8")
    except OSError:
        return None
    found = re.findall(r"([A-Za-z0-9@_.-]+\.service)", raw)
    return found[-1] if found else None


def answers(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def check_api(state):
    api = state.get("api")
    port = state.get("api_port", "8080")
    if not api:
        return report(False, "", "в состоянии занятия нет API: "
                                 "разверните лабу заново через reset.sh")
    if not Path("/run/systemd/system").is_dir():
        return skip("заявка 4 — PID 1 здесь не systemd, юнитов и автозапуска нет. "
                    "Она делается в виртуальной машине или в WSL с systemd; "
                    "остальные три от этого не зависят, и шести PASS достаточно")
    running = processes_with(api)
    if not running:
        return report(False, "", f"{api} не работает нигде: его надо не погасить, "
                                 f"а переселить — API должно отвечать на порту {port}")
    in_tmux = [pid for pid in running
               if any("tmux" in cmdline(parent) for parent in ancestors(pid))]
    units = [unit for unit in (unit_of(pid) for pid in running) if unit]
    problems = []
    if in_tmux:
        problems.append(f"API всё ещё работает внутри tmux (pid {', '.join(in_tmux)}): "
                        f"эта копия перезагрузку не переживёт, а порт займёт")
    if not units:
        problems.append("ни один процесс API не живёт в cgroup юнита: "
                        "systemd про него не знает")
    if not answers(port):
        problems.append(f"на 127.0.0.1:{port} никто не отвечает")
    unit = units[0] if units else None
    if unit:
        _, enabled = systemctl("is-enabled", unit)
        if enabled != "enabled":
            problems.append(f"{unit} не в автозапуске (is-enabled: {enabled or 'пусто'}): "
                            f"после следующей перезагрузки история повторится")
        _, restart = systemctl("show", "-p", "Restart", "--value", unit)
        if restart not in ("on-failure", "always", "on-abnormal"):
            problems.append(f"у {unit} Restart={restart or 'no'}: упав ночью, "
                            f"API так и останется лежать до утра")
    return report(
        not problems,
        f"API отвечает на порту {port}, живёт юнитом {unit}, включён в автозапуск "
        f"и поднимется сам после падения; копии в tmux больше нет",
        "; ".join(problems),
    )


def systemctl(*args):
    done = subprocess.run(["systemctl", *args], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    return done.returncode, done.stdout.strip()


state = load_state()
checks = [
    check_state(state),
    check_holder(state),
    check_restored_size(state),
    check_restored_content(state),
    check_scrollback(state),
    check_zombies(state),
    check_api(state),
]
sys.exit(0 if all(checks) else 1)
