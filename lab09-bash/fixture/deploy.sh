#!/bin/bash
# Выкладка релиза. Писалось быстро, «обычно работает».
# Запуск: ./deploy.sh КАТАЛОГ

DEST=$1
LOGDIR=logs

cd $DEST

VERSION=$(cat VERSION | tr -d '\n')
echo "выкладываю версию $VERSION"

rm -rf $DEST/releases/old

for f in $(ls $LOGDIR/*.log); do
  gzip -f $f
done

cat $LOGDIR/report.txt | grep -c ERROR > /tmp/deploy.tmp
STATUS=$(cat /tmp/deploy.tmp)

if [ $STATUS = 0 ]; then
  echo "ошибок в отчёте нет"
else
  echo "ошибок в отчёте: $STATUS"
fi

echo "готово: $VERSION"
