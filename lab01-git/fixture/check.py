#!/usr/bin/env python3
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

sys.dont_write_bytecode = True
ROOT = Path.cwd()
PYTHON = sys.executable


def run(command, cwd=ROOT):
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def git(*arguments):
    return run(["git", *arguments])


def report(ok, success, failure):
    print(f"{'PASS' if ok else 'FAIL'}: {success if ok else failure}")
    return ok


commits_result = git("rev-list", "--reverse", "start..HEAD")
all_commits = commits_result.stdout.splitlines() if commits_result.returncode == 0 else []


def paths_of(commit):
    return set(git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).stdout.splitlines())


# Отдельный коммит, в котором нет ничего, кроме .gitignore, допускается и не считается задачей.
commits = [commit for commit in all_commits if paths_of(commit) != {".gitignore"}]


def check_two_commits():
    if len(commits) != 2:
        return report(False, "", "после start должно быть ровно два содержательных коммита (отдельный коммит с .gitignore допускается)")
    subjects = [git("show", "-s", "--format=%s", commit).stdout.strip() for commit in all_commits]
    ok = all(subject.lower() not in {"wip", "fix", "lab1"} and len(subject) >= 12 for subject in subjects)
    return report(
        ok,
        "создано два самостоятельных коммита",
        "сообщения двух коммитов должны объяснять изменения",
    )


def check_separation():
    if len(commits) != 2:
        return report(False, "", "сначала создайте два коммита")
    groups = [
        {"pricing.py", "test_pricing.py"},
        {"money.py", "test_money.py"},
    ]
    seen = []
    for commit in commits:
        paths = paths_of(commit)
        paths.discard(".gitignore")
        seen.append(paths)
    ok = len(seen) == 2 and seen[0] in groups and seen[1] in groups and seen[0] != seen[1]
    return report(
        ok,
        "каждый коммит содержит одну задачу и её тест",
        "не смешивайте pricing с money; тест должен лежать с соответствующим кодом",
    )


def tests_pass_at(commit):
    with tempfile.TemporaryDirectory() as directory:
        archive = subprocess.run(
            ["git", "archive", commit], cwd=ROOT, stdout=subprocess.PIPE
        )
        if archive.returncode != 0:
            return False
        archive_path = Path(directory) / "tree.tar"
        archive_path.write_bytes(archive.stdout)
        with tarfile.open(archive_path) as bundle:
            bundle.extractall(directory)
        test = run([PYTHON, "-m", "unittest", "discover", "-p", "test_*.py"], directory)
        return test.returncode == 0


def check_tests():
    ok = len(commits) == 2 and all(tests_pass_at(commit) for commit in all_commits)
    return report(
        ok,
        "тесты проходят после каждого коммита",
        "проверьте каждый промежуточный коммит, а не только итоговый",
    )


def check_local_files():
    tracked = set(git("ls-files").stdout.splitlines())
    ignored_env = git("check-ignore", "-q", ".env.local").returncode == 0
    ignored_log = git("check-ignore", "-q", "debug.log").returncode == 0
    ok = not ({".env.local", "debug.log"} & tracked) and ignored_env and ignored_log
    return report(
        ok,
        "локальные файлы не попали в историю и игнорируются",
        "уберите .env.local и debug.log из индекса и добавьте их в .gitignore",
    )


def check_clean():
    ok = git("status", "--porcelain").stdout == ""
    return report(ok, "рабочее дерево чистое", "остались незакоммиченные изменения")


checks = [
    check_two_commits(),
    check_separation(),
    check_tests(),
    check_local_files(),
    check_clean(),
]
sys.exit(0 if all(checks) else 1)
