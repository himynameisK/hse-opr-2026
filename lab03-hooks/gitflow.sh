#!/usr/bin/env bash
set -euo pipefail

# Тренажёр на обратный мердж. Разворачивает репозиторий в состоянии
# «релиз уехал в main, а в develop его не вернули». Чинить руками.

unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
LAB="${1:-$(dirname "$REPO")/opr-lab03}"
GF="$LAB/gitflow"

command -v git >/dev/null || { echo "git не найден" >&2; exit 1; }

if [[ -e "$GF" ]]; then
  echo "Каталог уже существует: $GF" >&2
  echo "Удалите его сами: rm -rf \"$GF\"" >&2
  exit 1
fi

mkdir -p "$GF"; cd "$GF"
git init -q; git symbolic-ref HEAD refs/heads/main
git config user.name "OPR Course"
git config user.email "opr-course@example.invalid"
git config core.autocrlf false; git config core.eol lf
git config commit.gpgsign false
git config merge.conflictstyle diff3

c() { git add -A; git commit -q -m "$1"; }

# 1.1 в проде
cat > pay.py <<'EOF'
def pay(card, amount):
    return card.id, amount
EOF
echo "1.1.0" > VERSION
printf '# Changelog\n\n## 1.1.0\n- платежи\n' > CHANGELOG.md
c "payments v1.1"; git tag v1.1
git branch develop

# в develop поехала фича
git switch -q develop
echo 'def add_to_cart(item): pass' > cart.py
c "feature: корзина"

# от develop отрезали релиз и стабилизировали его
git switch -q -c release/1.2
cat > pay.py <<'EOF'
def pay(card, amount):
    if card is None:
        return None
    return card.id, amount
EOF
echo "1.2.0" > VERSION
printf '# Changelog\n\n## 1.2.0\n- починили падение на пустой карте\n\n## 1.1.0\n- платежи\n' > CHANGELOG.md
c "fix: NPE when card is None"

# релиз уехал в main и получил тег
git switch -q main
git merge -q --no-ff release/1.2 -m "Merge release/1.2 into main"
git tag v1.2

# ...а обратно в develop его не влили. Здесь и живёт ошибка.
git switch -q develop
echo 'def promo(code): pass' > promo.py
echo "1.3.0-dev" > VERSION
c "feature: промокоды"

git rev-parse main > .opr-main-tip
git rev-parse develop > .opr-develop-tip
printf '.opr-main-tip\n.opr-develop-tip\n' > .git/info/exclude

git switch -q develop
cat <<EOF

Развёрнуто: $GF

  main      v1.1 ──────── Merge release/1.2 (тег v1.2, фикс внутри)
  develop   v1.1 ── корзина ── промокоды          ← фикса НЕТ
  release/1.2 на месте

Задача: закрыть долг — вернуть релиз в develop, не трогая main
и не переписывая историю.

  cd "$GF"
  git show develop:pay.py     # убедитесь, что проверки на None нет
  git log --oneline develop..main   # это и есть долг

Конфликт по VERSION будет: и релиз, и develop правили версию.
Он ожидаем, разрешайте в пользу develop.

Проверка:  cd "$LAB/shop" && ./check.py --gitflow
EOF
