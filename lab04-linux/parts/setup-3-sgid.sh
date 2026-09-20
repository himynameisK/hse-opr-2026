#!/usr/bin/env bash
# Занятие 4. Готовит состояние: общую группу, двух человек в ней, одного
# постороннего и пустой каталог, в который пока может писать только root.
# Запускать ВНУТРИ своего Linux и от root: нужны useradd, chown и chmod.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LAB="${1:-/opt/opr-lab04}"

GROUP=shop
TEAM=(alice bob)
OUTSIDER=carol
SHARED=/srv/shop/shared

[ "$(id -u)" -eq 0 ] || { echo "Запускать от root: sudo bash $0" >&2; exit 1; }
for tool in useradd usermod groupadd gpasswd getent su; do
  command -v "$tool" >/dev/null || { echo "Не найден $tool" >&2; exit 1; }
done
command -v python3 >/dev/null || {
  echo "Не найден python3 — им запускается проверка." >&2
  echo "Поставьте: apt-get update && apt-get install -y python3" >&2
  exit 1
}

# Общая группа: она и будет пропуском в каталог.
getent group "$GROUP" >/dev/null || groupadd "$GROUP"

# Основная группа у каждого своя (alice:alice, bob:bob), shop — дополнительная.
# Именно так заводят людей в одной команде, и именно поэтому одного членства
# в группе для общего каталога не хватит.
for user in "${TEAM[@]}"; do
  if getent passwd "$user" >/dev/null; then
    usermod -aG "$GROUP" "$user"
  else
    useradd --create-home --shell /bin/bash --groups "$GROUP" "$user"
  fi
  # Повторный запуск должен возвращать исходное состояние целиком. Если на
  # прошлом заходе shop сделали основной группой, откатываем: группу файлам
  # обязан отдавать каталог, а не пользователь.
  if [ "$(id -gn "$user")" != "$user" ] && getent group "$user" >/dev/null; then
    usermod -g "$user" "$user"
  fi
done

# Посторонний: заведён, но в shop не состоит и не должен.
getent passwd "$OUTSIDER" >/dev/null || useradd --create-home --shell /bin/bash "$OUTSIDER"
gpasswd -d "$OUTSIDER" "$GROUP" >/dev/null 2>&1 || true

# Каталог создаётся заново: если вы его уже настраивали, настройки сброшены —
# начинайте с чистого root:root 755.
rm -rf "$SHARED"
mkdir -p "$SHARED"
chown root:root "$SHARED"
chmod 755 "$SHARED"
chmod 755 "$(dirname "$SHARED")"   # в /srv/shop нужен проход для всех

mkdir -p "$LAB"

echo "Готово: каталог $SHARED, группа $GROUP, в ней ${TEAM[*]}."
echo "Ещё заведена $OUTSIDER — она посторонняя, в $GROUP её нет и быть не должно."
echo "Каталог сейчас root:root 755 — писать в него может только root. Это и чините."
echo "Проверка (от root): $LAB/check.py"
echo "Условие: $HERE/README.md"