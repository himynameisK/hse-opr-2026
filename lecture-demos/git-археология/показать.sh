#!/usr/bin/env bash
# Демонстрация: коммиты Линуса 2005 года в сегодняшнем Git.
set -uo pipefail
REPO="${1:-$HOME/git-src}"
[ -d "$REPO/.git" ] || { echo "Нет репозитория: $REPO"; echo "Сначала: git clone https://github.com/git/git.git $REPO"; exit 1; }
cd "$REPO"
FIRST=e83c5163316f89bfbde7d9ab23ca2e25604af290

echo "1. Самый первый коммит в истории Git:"
git log --reverse --format='   %H%n   %an <%ae>%n   %ad%n   %s' | head -4
echo; echo "2. Объект целиком — обратите внимание, строки parent нет:"
git cat-file -p $FIRST | sed 's/^/   /'
echo; echo "3. Весь Git на тот момент:"
git ls-tree --name-only $FIRST | tr '\n' ' ' | fold -s -w 74 | sed 's/^/   /'
echo "   $(git show $FIRST --stat | tail -1 | sed 's/^ *//')"
echo "   сегодня: $(git ls-files | wc -l | tr -d ' ') файлов"
echo; echo "4. README из того коммита:"
git show $FIRST:README | head -4 | sed 's/^/   /'
echo; echo "5. А теперь сегодняшний код:"
git blame -L 1,5 read-cache.c | sed 's/^/   /'
echo
echo "   строк от 7 апреля 2005 живо в read-cache.c: $(git blame read-cache.c 2>/dev/null | grep -c '2005-04-0[78]')"
echo "   коммит 8bc9a0c769 сделан через три минуты после первого"
