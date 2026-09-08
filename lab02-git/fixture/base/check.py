#!/usr/bin/env python3
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


def check_merge():
    if git("rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return fail("слияние ещё не завершено")
    if git("merge-base", "--is-ancestor", "main", "HEAD").returncode != 0:
        return fail("main ещё не слит в текущую ветку")
    try:
        from order import total

        items = [{"price": 1000, "quantity": 2}]
        assert total(items) == 2000
        assert total(items, discount_percent=10) == 1800
        assert total(items, delivery=500) == 2500
        assert total(items, discount_percent=10, delivery=500) == 2300
    except (AssertionError, ImportError, TypeError) as error:
        return fail(f"скидка и доставка работают вместе неверно ({error})")
    print("PASS: конфликт разрешён, скидка и доставка работают вместе")
    return True


def check_recovery():
    history = git("log", "--format=%s", "HEAD")
    if "Исправить формат отрицательных сумм" not in history.stdout:
        return fail("потерянное исправление не найдено в истории текущей ветки")
    try:
        from money import format_money

        assert format_money(12345) == "123.45 ₽"
        assert format_money(-12345) == "-123.45 ₽"
    except (AssertionError, ImportError) as error:
        return fail(f"отрицательная сумма форматируется неверно ({error})")
    print("PASS: потерянное исправление восстановлено")
    return True


def check_clean():
    if git("status", "--porcelain").stdout:
        return fail("есть незакоммиченные изменения")
    print("PASS: рабочее дерево чистое")
    return True


results = [check_merge(), check_recovery(), check_clean()]
sys.exit(0 if all(results) else 1)
