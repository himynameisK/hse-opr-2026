# opr-2026-tasks

## Как этим пользоваться

Каждое занятие лежит в отдельном каталоге и разворачивается отдельным генератором.

```bash
make lab1                    # развернёт занятие 1 в ../opr-lab01
make lab2                    # развернёт занятие 2 в ../opr-lab02
make lab3                    # развернёт занятие 3 в ../opr-lab03
sudo make lab4               # занятие 4 — внутри Linux, в /opt/opr-lab04
make lab1 LAB1_DEST=/tmp/lab # или в указанный каталог
```

Лаба разворачивается **рядом с этим репозиторием**, а не в домашнем каталоге:
если курс лежит в `~/Загрузки/hse-opr-2026`, лаба будет в `~/Загрузки/opr-lab02`.
Точный путь скрипт печатает последней строкой — `Готово: …`.

Если `make` не установлен — а в Git Bash на Windows его нет, — то же самое одной командой:

```bash
bash lab01-git/setup.sh              # = make lab1
bash lab02-git/setup.sh              # = make lab2
bash lab03-hooks/setup.sh            # = make lab3
bash lab02-git/setup.sh /tmp/lab     # = make lab2 LAB2_DEST=/tmp/lab
```

## Windows

Все команды курса набираются в **Git Bash** (ставится вместе с Git for Windows),
не в PowerShell и не в cmd. Если у вас WSL — работайте внутри WSL и пишите именно
`bash`, а не `sh`.

Три отличия от текста заданий:

| В задании | На Windows |
| --- | --- |
| `make lab2` | `bash lab02-git/setup.sh` — ровно то же самое |
| `./check.py` | `python check.py`, а если `python` не нашёлся — `py check.py` |

Если вы клонировали репозиторий курса **до 16.09.2026**, обновите его:

```bash
git pull
```

Этого достаточно: до обновления скрипты приезжали с CRLF и `bash setup.sh` падал
на второй строке с `set: pipefail: invalid option name`. Если у вас есть свои правки
и `git pull` не прошёл — сначала уберите их, потом обновляйтесь.

## Проектная работа

Условия и список тем — в [ПРОЕКТНАЯ-РАБОТА.md](ПРОЕКТНАЯ-РАБОТА.md).
Тему выбираете сами; требования одинаковы для любой.

## Структура

```
lab01-git/          занятие 1 — привести staged-изменения в порядок
  README.md         условие для студентов
  setup.sh          разворачивает лабораторную
  fixture/          исходное и изменённое состояния проекта

lab02-git/          занятие 2 — merge-конфликт и восстановление коммита
  README.md         условие для студентов
  SUBMISSION.md     шаблон удалённой сдачи
  setup.sh          разворачивает лабораторную
  fixture/          исходные состояния учебного проекта

lab03-hooks/        занятие 3 — свои хуки и подпись вебхука
lab04-linux/        занятие 4 — права, дескрипторы, общий каталог (только Linux)
  README.md         условие для студентов
  SUBMISSION.md     шаблон сдачи, включая работу в своём репозитории
  setup.sh          разворачивает лабораторную
  fixture/          исходный проект и записанные доставки вебхука
```

## Если хочется посмотреть, как это читают в MIT

То, чем мы занимаемся, в обычной программе по computer science не преподают нигде —
ни у нас, ни за границей. Алгоритмы и теорию читают, инструменты, которыми работают
каждый день, — нет. В MIT этот пробел признали и завели отдельный курс: **The Missing
Semester of Your CS Education**. Он идёт в январские сессии до сих пор, записи открыты.

- Сайт курса: https://missing.csail.mit.edu/
- Плейлист 2026 года: https://www.youtube.com/playlist?list=PLyzOVJj3bHQunmnnTXrNbZnBaCA-ieK4L
- Плейлист 2020 года: https://www.youtube.com/playlist?list=PLyzOVJj3bHQuloKGG59rS43e29ro7I57J

Что с чем соотносится у нас:

| Наше занятие | Лекция Missing Semester |
|---|---|
| 1–3, Git | Version Control and Git |
| 4–6, Linux | Course Overview + Introduction to the Shell; Command-line Environment |
| 7–8, Bash | Command-line Environment; Debugging and Profiling |
| 9–13, Docker и поставка | Packaging and Shipping Code |

Смотреть не обязательно, на зачёт это не влияет. Но если какая-то тема не села —
посмотреть то же самое в другом изложении часто помогает быстрее, чем перечитывать
конспект. Учтите, что у них короче и без практики: разбираем руками мы, а не они.


## Требования

git 2.23+, bash, Python 3.8+ (`python3`, `python` или `py` — любой из них).
Для pull request нужен аккаунт GitHub.
