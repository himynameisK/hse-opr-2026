#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True


def git(*args):
    return subprocess.run(
        ["git", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )


def fail(message):
    print(f"FAIL: {message}")
    return False


def load(module, names):
    """Импортирует модуль студента. Любая ошибка превращается в понятный FAIL."""
    import importlib

    try:
        loaded = importlib.import_module(module)
        importlib.reload(loaded)
        return [getattr(loaded, name) for name in names], None
    except SyntaxError as error:
        line = (error.text or "").strip()
        if line.startswith(("<<<<<<<", "=======", ">>>>>>>")):
            return None, f"в {module}.py остались маркеры конфликта — уберите их и закоммитьте заново"
        return None, f"{module}.py не разбирается: строка {error.lineno}, {error.msg}"
    except Exception as error:
        return None, f"{module}.py не удалось загрузить: {type(error).__name__}: {error}"


def check_merge():
    if git("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return fail("слияние ещё не завершено")
    if git("merge-base", "--is-ancestor", "main", "HEAD").returncode != 0:
        return fail("main ещё не слит в текущую ветку")
    loaded, error = load("order", ["total"])
    if error:
        return fail(error)
    (total,) = loaded
    items = [{"price": 1000, "quantity": 2}]
    cases = [
        ((), {}, 2000, "без скидки и доставки"),
        ((), {"discount_percent": 10}, 1800, "только скидка"),
        ((), {"delivery": 500}, 2500, "только доставка"),
        ((), {"discount_percent": 10, "delivery": 500}, 2300,
         "скидка на товары, доставка сверху и БЕЗ скидки"),
    ]
    for args, kwargs, want, what in cases:
        try:
            got = total(items, *args, **kwargs)
        except TypeError as bad:
            return fail(f"total не принимает нужные параметры ({bad})")
        if got != want:
            return fail(f"{what}: ожидалось {want}, получилось {got}")
    print("PASS: конфликт разрешён, скидка и доставка работают вместе")
    return True


def check_recovery():
    # Проверяем РЕЗУЛЬТАТ, а не текст сообщения: способ вернуть исправление
    # может быть любым — cherry-pick, apply, restore --source.
    loaded, error = load("money", ["format_money"])
    if error:
        return fail(error)
    (format_money,) = loaded
    for value, want in ((12345, "123.45 ₽"), (-12345, "-123.45 ₽"), (-5, "-0.05 ₽")):
        got = format_money(value)
        if got != want:
            return fail(f"format_money({value}) вернул {got!r}, ожидалось {want!r}")
    # И убеждаемся, что исправление именно ВОССТАНОВЛЕНО из истории,
    # а не набрано заново: содержимое money.py должно совпасть с потерянным коммитом.
    # Ищем ТОЛЬКО в reflog ветки main: там лежит потерянный коммит.
    # Собственные коммиты студента туда не попадают, поэтому переписать файл
    # руками и выдать за восстановление не получится.
    lost = git("log", "-g", "--format=%H", "main")
    blob_now = git("rev-parse", "HEAD:money.py").stdout.strip()
    found = False
    for commit in dict.fromkeys(lost.stdout.split()):
        if git("rev-parse", f"{commit}:money.py").stdout.strip() == blob_now:
            found = True
            break
    if not found:
        return fail(
            "money.py работает, но это не тот объект, что был в потерянном коммите — "
            "найдите коммит через git reflog и перенесите его, а не переписывайте файл руками"
        )
    print("PASS: потерянное исправление восстановлено")
    return True


def check_semantic():
    for branch in ("feature/naming", "feature/receipt"):
        if git("merge-base", "--is-ancestor", branch, "HEAD").returncode != 0:
            return fail(f"ветка {branch} ещё не слита в текущую")
    # Переименование трогать нельзя: чинить надо вызывающего, а не автора правки.
    catalog = Path("catalog.py").read_text(encoding="utf-8") if Path("catalog.py").exists() else ""
    if "def format_item" not in catalog:
        return fail(
            "в catalog.py больше нет format_item — переименование отменять нельзя, "
            "чинить надо вызов в receipt.py"
        )
    if "def item_title" in catalog:
        return fail(
            "в catalog.py вернули старое имя item_title — это отмена чужой работы, "
            "условие требует починить вызывающего"
        )
    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-p", "test_*.py"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if tests.returncode != 0:
        lines = [line for line in tests.stdout.strip().splitlines() if line.strip()]
        cause = next((line.strip() for line in reversed(lines)
                      if "Error" in line or "assert" in line.lower()), lines[-1] if lines else "")
        return fail(f"слияние прошло чисто, но тесты падают: {cause}")
    loaded, error = load("receipt", ["build"])
    if error:
        return fail(error)
    (build,) = loaded
    items = [{"name": "Кружка", "price": 1000, "quantity": 2}]
    want = "Кружка x2 — 20.00 ₽\nИтого: 20.00 ₽"
    got = build(items)
    if got != want:
        return fail(f"чек собирается неверно: получилось {got!r}")
    print("PASS: семантический конфликт найден и исправлен, тесты зелёные")
    return True


NOISE = {".DS_Store", "Thumbs.db", "desktop.ini"}


def check_clean():
    lines = []
    for line in git("status", "--porcelain").stdout.splitlines():
        name = line[3:].strip().strip('"')
        if Path(name).name in NOISE or name.endswith("/") and Path(name.rstrip("/")).name in NOISE:
            continue
        lines.append(line)
    if lines:
        return fail("остались незакоммиченные изменения: " + ", ".join(l[3:] for l in lines[:3]))
    print("PASS: рабочее дерево чистое")
    return True


results = [check_merge(), check_recovery(), check_semantic(), check_clean()]
sys.exit(0 if all(results) else 1)
