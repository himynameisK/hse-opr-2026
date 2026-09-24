#!/usr/bin/env bash
set -euo pipefail

# Не наследуем окружение вызывающего: иначе лаба уедет в чужой репозиторий.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY

HERE="$(cd "$(dirname "$0")" && pwd)"
# Разворачиваем РЯДОМ с репозиторием курса, а не в домашнем каталоге:
# так лаба лежит там же, куда вы его скачали, и её видно.
REPO="$(dirname "$HERE")"
LAB="${1:-$(dirname "$REPO")/opr-lab03}"
SHOP="$LAB/shop"

command -v git >/dev/null || { echo "git не найден" >&2; exit 1; }
PY=""
for c in python3 python py; do
  command -v "$c" >/dev/null 2>&1 || continue
  "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,8) else 1)' >/dev/null 2>&1 || continue
  PY="$c"; break
done
[ -n "$PY" ] || { echo "Python 3.8+ не найден (пробовал python3, python, py)" >&2; exit 1; }

if [[ -e "$LAB" ]]; then
  echo "Каталог уже существует: $LAB" >&2
  echo "Удалите его сами: rm -rf \"$LAB\"" >&2
  echo "Или разверните в другой: make lab3 LAB3_DEST=/tmp/opr-lab03" >&2
  echo "Без make (Git Bash на Windows): bash lab03-hooks/setup.sh /tmp/opr-lab03" >&2
  exit 1
fi

mkdir -p "$SHOP"
cd "$SHOP"
git init -q
git symbolic-ref HEAD refs/heads/main
git config user.name "OPR Course"
git config user.email "opr-course@example.invalid"
# Иначе при core.autocrlf=true у студента файлы лабы уедут в CRLF
git config core.autocrlf false
git config core.eol lf
git config commit.gpgsign false
git config tag.gpgsign false

cp "$HERE/fixture/base/"*.py .
cp "$HERE/fixture/check.py" check.py
chmod +x check.py
printf '__pycache__/\n' > .gitignore

# Каркасы обоих хуков на Python: всё, что достаётся из git, уже написано.
# Студент дописывает только условия. Шебанг — с тем интерпретатором, который
# здесь реально нашёлся: на Windows это может быть python, а не python3.
mkdir -p .githooks

{
printf '#!/usr/bin/env %s\n' "$PY"
cat <<'HOOK'
"""pre-commit. Git запускает его перед созданием коммита.
Ненулевой код возврата — коммит отменён."""
import re
import subprocess
import sys


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


# --- уже достали из git, этим и работайте -----------------------------------

# files — пути файлов, которые уходят в коммит
files = git("diff", "--cached", "--name-only", "--diff-filter=ACM").split()

# added — добавленные строки индекса, уже без ведущего '+'
added = [line[1:] for line
         in git("diff", "--cached", "--diff-filter=ACM", "-U0").splitlines()
         if line.startswith("+") and not line.startswith("+++")]

status = 0

# --- ЗАПОЛНИТЬ 1 ------------------------------------------------------------
# Отклонить .env и любые .env.* — пройдитесь по files.
# При отказе: print(..., file=sys.stderr) и status = 1


# --- ЗАПОЛНИТЬ 2 ------------------------------------------------------------
# Найти в added присваивание секрета с НЕПУСТЫМ значением.
#   поймать:     API_KEY="AKIAIOSFODNN7EXAMPLE"   TOKEN=abc12345
#   НЕ поймать:  Не коммитьте токены и пароли.
# Важно не слово, а знак = и непустое значение после него.


# ----------------------------------------------------------------------------
if status:
    print("pre-commit: коммит остановлен. Обойти осознанно: git commit --no-verify",
          file=sys.stderr)
sys.exit(status)
HOOK
} > .githooks/pre-commit

{
printf '#!/usr/bin/env %s\n' "$PY"
cat <<'HOOK'
"""commit-msg. Git передаёт сюда ОДИН аргумент: путь к файлу с сообщением.
Ненулевой код возврата — коммит отменён."""
import re
import sys

# --- уже достали, этим и работайте ------------------------------------------

message = open(sys.argv[1], encoding="utf-8").read()
first_line = message.splitlines()[0] if message.splitlines() else ""

# --- ЗАПОЛНИТЬ --------------------------------------------------------------
# Принять   «SHOP-12 Добавить расчёт скидки»
# отклонить «Добавить расчёт скидки» и «shop12 добавить скидку»
# При отказе: print(..., file=sys.stderr) и sys.exit(1)


sys.exit(0)
HOOK
} > .githooks/commit-msg

chmod +x .githooks/pre-commit .githooks/commit-msg

git add .
git commit -q -m "Начальная версия магазина и каркас pre-commit"
git tag start

echo "Готово: $SHOP"
echo "В .githooks лежат каркасы обоих хуков на Python: всё, что берётся из git,"
echo "уже написано. Дописать надо три места с пометкой ЗАПОЛНИТЬ."
echo "Не забудьте включить: git config core.hooksPath .githooks"
echo "Условие: $HERE/README.md"
