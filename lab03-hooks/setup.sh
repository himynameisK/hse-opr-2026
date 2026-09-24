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

# Каркас pre-commit: вся возня с индексом уже написана, студент дописывает
# два места. commit-msg он пишет сам с нуля — тот посильный.
mkdir -p .githooks
cat > .githooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
# Git запускает этот скрипт перед созданием коммита.
# Ненулевой код возврата — коммит отменён.
set -uo pipefail

status=0

# --- 1. Файлы, которых в истории быть не должно ------------------------------
# ЗАПОЛНИТЬ: отклонить .env (и .env.local, .env.prod — любые .env.*)
while IFS= read -r file; do
	case "$(basename "$file")" in
		# сюда шаблон имени, а в теле: echo ... >&2; status=1
		*) ;;
	esac
done < <(git diff --cached --name-only --diff-filter=ACM)

# --- 2. Секрет в добавленных строках -----------------------------------------
# Берём только добавленные строки индекса. '^[+]' именно в скобках: так шаблон
# верен во всех реализациях grep. '+++' — служебная строка дифа, её убираем.
added=$(git diff --cached --diff-filter=ACM -U0 | grep -E '^[+]' | grep -v '^[+][+][+]' || true)

# ЗАПОЛНИТЬ: шаблон присваивания секрета с НЕПУСТЫМ значением.
#   поймать:     API_KEY="AKIAIOSFODNN7EXAMPLE"   TOKEN=abc123   SECRET='...'
#   НЕ поймать:  Не коммитьте токены и пароли.
# Подсказка: важно не слово, а знак = и непустое значение после него.
pattern=''

if [[ -n "$pattern" ]] && printf '%s\n' "$added" | grep -qE "$pattern"; then
	echo "pre-commit: похоже на секрет в добавленных строках:" >&2
	printf '%s\n' "$added" | grep -E "$pattern" >&2
	status=1
fi

if [[ $status -ne 0 ]]; then
	echo "pre-commit: коммит остановлен. Обойти осознанно: git commit --no-verify" >&2
fi
exit $status
HOOK
chmod +x .githooks/pre-commit

git add .
git commit -q -m "Начальная версия магазина и каркас pre-commit"
git tag start

echo "Готово: $SHOP"
echo "В .githooks лежит каркас pre-commit — в нём два места с пометкой ЗАПОЛНИТЬ."
echo "commit-msg пишете сами. Включить хуки: git config core.hooksPath .githooks"
echo "Условие: $HERE/README.md"
