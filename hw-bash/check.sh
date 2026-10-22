#!/usr/bin/env bash
# Проверка решения домашки по bash.
#
#   ./check.sh 8        проверить задачу 8: решение 8.sh лежит в этой же папке
#
# Для проверяющего:
#   ./check.sh -d ПАПКА 8   решение лежит в другой папке
#   ./check.sh -t ПАПКА 8   другой набор тестов
#   ./check.sh -v 8         показать каждый тест, а не только упавшие
#   ./check.sh -f 8         не проверять окружение (bash 4+, GNU-утилиты)
#
# Решения запускаются так, как в обычном Linux: bash 4+ и GNU-утилиты
# (coreutils, sed, grep). На macOS скрипт сам находит их в Homebrew:
#   brew install bash coreutils gnu-sed grep gawk
# Свой bash можно указать явно: SOL_BASH=/путь/к/bash ./check.sh
# Локаль решений — LC_ALL=C, как на серверах: sort сортирует
# по кодам символов, строки обрабатываются побайтно.

set -u
HERE=$(cd "$(dirname "$0")" && pwd)
SOL_DIR=. TESTS_DIR=$HERE/tests VERBOSE=0 FORCE=0
# рядом нет открытых тестов, но есть скрытые — значит, это копия для проверяющего
[ -d "$HERE/tests" ] || [ ! -d "$HERE/hidden" ] || TESTS_DIR=$HERE/hidden
ARGS=("$@")
while getopts "d:t:vfh" opt; do
  case $opt in
    d) SOL_DIR=$OPTARG ;;
    t) TESTS_DIR=$OPTARG ;;
    v) VERBOSE=1 ;;
    f) FORCE=1 ;;
    *) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  esac
done
shift $((OPTIND - 1))
if [ $# -eq 0 ]; then
  echo "Укажите номер своей задачи, например: ./check.sh 8"
  exit 2
fi

# ---------- окружение: bash 4+ и GNU-утилиты ----------
RUN_PATH=$PATH
if [ "$(uname)" = Darwin ]; then
  for bp in /usr/local /opt/homebrew; do
    [ -d "$bp/bin" ] || continue
    RUN_PATH="$bp/bin:$RUN_PATH"
    for p in findutils gawk grep gnu-sed coreutils; do
      [ -d "$bp/opt/$p/libexec/gnubin" ] && RUN_PATH="$bp/opt/$p/libexec/gnubin:$RUN_PATH"
    done
  done
fi
SOL_BASH=${SOL_BASH:-$(PATH=$RUN_PATH command -v bash)}
BASH_MAJOR=$("$SOL_BASH" -c 'echo ${BASH_VERSINFO[0]}' 2>/dev/null || echo 0)

# сам скрипт тоже переезжает в новый bash: там есть точное время ($EPOCHREALTIME)
if [ "${BASH_VERSINFO[0]}" -lt 4 ] && [ "$BASH_MAJOR" -ge 4 ] && [ -z "${CHECK_REEXEC:-}" ]; then
  CHECK_REEXEC=1 exec "$SOL_BASH" "$0" "${ARGS[@]+"${ARGS[@]}"}"
fi

is_gnu() { PATH=$RUN_PATH "$1" --version 2>/dev/null | head -1 | grep -q "$2"; }
PROBLEMS=() WARNINGS=()
[ "$BASH_MAJOR" -ge 4 ] || PROBLEMS+=("bash $("$SOL_BASH" -c 'echo $BASH_VERSION') — нужен bash 4 или новее")
is_gnu sort "GNU coreutils" || PROBLEMS+=("sort, tr, cut и прочие — не GNU coreutils")
is_gnu sed "GNU sed" || PROBLEMS+=("sed — не GNU sed")
is_gnu grep "GNU grep" || PROBLEMS+=("grep — не GNU grep")
PATH=$RUN_PATH command -v factor >/dev/null || PROBLEMS+=("нет команды factor (входит в GNU coreutils)")
is_gnu awk "GNU Awk" || WARNINGS+=("awk — не gawk: решения с расширениями gawk могут вести себя иначе")
PATH=$RUN_PATH command -v bc >/dev/null || WARNINGS+=("нет bc")

first_line() { PATH=$RUN_PATH "$1" --version 2>/dev/null | head -1 | cut -d, -f1 | grep . || echo "$1 не GNU"; }
echo "Окружение: bash $("$SOL_BASH" -c 'echo $BASH_VERSION' 2>/dev/null) ($SOL_BASH);" \
     "$(first_line sort); $(first_line sed); $(first_line awk)"
for w in ${WARNINGS[@]+"${WARNINGS[@]}"}; do echo "  предупреждение: $w"; done
if [ ${#PROBLEMS[@]} -gt 0 ]; then
  echo "Окружение не похоже на Linux, решения могут упасть не по своей вине:"
  for p in "${PROBLEMS[@]}"; do echo "  - $p"; done
  if [ "$(uname)" = Darwin ]; then
    echo "На macOS поставьте: brew install bash coreutils gnu-sed grep gawk"
  else
    echo "В Linux поставьте недостающее пакетным менеджером (например, sudo apt install coreutils sed grep gawk)."
  fi
  if [ "$FORCE" -eq 0 ]; then echo "Запустить всё равно: ./check.sh -f"; exit 2; fi
fi
echo

# ---------- запуск одного теста с лимитом времени ----------
SOL_DIR=$(cd "$SOL_DIR" 2>/dev/null && pwd) || { echo "Нет папки с решениями: $SOL_DIR"; exit 2; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir "$TMP/run"   # решения запускаются отсюда: их файлы не попадут в папку проверки
LIMIT=10

# сначала родитель (чтобы не успел ничего сделать), потом его потомки
kill_tree() {
  local c kids
  kids=$(pgrep -P "$1" 2>/dev/null)
  kill -9 "$1" 2>/dev/null
  for c in $kids; do kill_tree "$c"; done
}

now() { if [ -n "${EPOCHREALTIME:-}" ]; then echo "${EPOCHREALTIME/,/.}"; else date +%s; fi; }

# run_one ФАЙЛ АРГУМЕНТЫ… → OUT, ERR, RC, TIMED_OUT, ELAPSED
run_one() {
  local sol=$1; shift
  rm -f "$TMP/timeout"
  local t0; t0=$(now)
  ( cd "$TMP/run" && LC_ALL=C PATH=$RUN_PATH exec "$SOL_BASH" "$sol" "$@" ) </dev/null >"$TMP/out" 2>"$TMP/err" &
  local pid=$!
  ( sleep "$LIMIT"; : >"$TMP/timeout"; kill_tree "$pid" ) 2>/dev/null &
  local watcher=$!
  wait "$pid" 2>/dev/null; RC=$?
  kill_tree "$watcher"; wait "$watcher" 2>/dev/null
  ELAPSED=$(awk -v a="$t0" -v b="$(now)" 'BEGIN { printf "%.2f", b - a }')
  TIMED_OUT=0; [ -e "$TMP/timeout" ] && TIMED_OUT=1
  OUT=$(cat "$TMP/out"); ERR=$(head -c 300 "$TMP/err")
}

# длинное обрезаем, невидимое показываем: перевод строки — ⏎, \r из Windows — ␍
short() {
  local s=$1
  [ ${#s} -gt 100 ] && s="${s:0:100}… (${#1} симв.)"
  s=${s//$'\r'/␍}; s=${s//$'\n'/⏎}
  printf '%s' "$s"
}
show_args() { local a out=""; for a in "$@"; do out+="$(printf '%q' "$a") "; done; short "${out% }"; }

# ---------- тесты ----------
TASKS=("$@")

SOLVED=0 TOTAL=0
for n in "${TASKS[@]}"; do
  tests=$TESTS_DIR/$n.sh
  [ -f "$tests" ] || { echo "Задача $n: нет файла тестов $tests"; continue; }
  TOTAL=$((TOTAL + 1))
  sol=$SOL_DIR/$n.sh
  if [ ! -f "$sol" ]; then printf 'Задача %2s  —  нет файла %s.sh в %s\n' "$n" "$n" "$SOL_DIR"; continue; fi

  notes=()
  grep -q $'\r' "$sol" && notes+=("окончания строк Windows (CRLF): в Linux будет \$'\\r': command not found")
  head -1 "$sol" | grep -q '^#!' || notes+=("первая строка — не шебанг")
  [ -x "$sol" ] || notes+=("нет права на запуск: chmod +x $n.sh")

  pass=0 cnt=0 report=""
  LIMIT=10
  limit() { LIMIT=$1; }
  t() {
    local want=$1; shift
    cnt=$((cnt + 1))
    run_one "$sol" "$@"
    if [ "$TIMED_OUT" -eq 1 ]; then
      report+="    TIMEOUT  ./$n.sh $(show_args "$@")"$'\n'"             не уложилось в $LIMIT с"$'\n'
    elif [ "$OUT" == "$want" ]; then
      pass=$((pass + 1))
      [ "$VERBOSE" -eq 1 ] && report+="    PASS     ./$n.sh $(show_args "$@")   ($ELAPSED с)"$'\n'
    else
      report+="    FAIL     ./$n.sh $(show_args "$@")"$'\n'
      report+="             ждали: $(short "$want")"$'\n'"             вывод: $(short "$OUT")"$'\n'
      [ -n "$ERR" ] && report+="             stderr: $(short "$(printf '%s' "$ERR" | head -1)")"$'\n'
      [ "$RC" -ne 0 ] && report+="             код возврата: $RC"$'\n'
    fi
  }
  # shellcheck disable=SC1090
  source "$tests"

  if [ "$pass" -eq "$cnt" ]; then
    SOLVED=$((SOLVED + 1)); printf 'Задача %2s  PASS  %d/%d\n' "$n" "$pass" "$cnt"
  else
    printf 'Задача %2s  FAIL  %d/%d\n' "$n" "$pass" "$cnt"
  fi
  for w in ${notes[@]+"${notes[@]}"}; do echo "    замечание: $w"; done
  printf '%s' "$report"
done

echo
if [ "$TOTAL" -eq 1 ]; then
  n=${TASKS[0]}
  if [ ! -f "$SOL_DIR/$n.sh" ]; then
    echo "Итог: решения нет — положите $n.sh в $SOL_DIR"
  elif [ "$SOLVED" -eq 1 ]; then
    if [ "$(basename "$TESTS_DIR")" = hidden ]; then
      echo "Итог: задача $n решена — скрытые тесты пройдены: $cnt из $cnt."
    else
      echo "Итог: задача $n решена — все $cnt открытых тестов прошли. Можно сдавать $n.sh."
      echo "      При сдаче тестов будет больше: другие входы, крайние случаи, большие входы."
    fi
    [ ${#notes[@]} -eq 0 ] || echo "      Перед сдачей поправьте замечания выше."
  else
    echo "Итог: задача $n пока не решена — прошло $pass из $cnt тестов. Смотрите упавшие тесты выше."
  fi
else
  echo "Итого: решено $SOLVED из $TOTAL (решена = прошла все тесты)"
fi
[ "$SOLVED" -eq "$TOTAL" ]
