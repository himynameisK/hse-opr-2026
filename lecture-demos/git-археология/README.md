# Коммиты Линуса, которые до сих пор работают

Нужна сеть один раз, чтобы склонировать репозиторий Git. **Склонируйте заранее**,
на паре это займёт несколько минут и 334 мегабайта.

```bash
git clone https://github.com/git/git.git ~/git-src
```

Сколько занимает: 7 минут.

## Что спросить у зала ДО запуска

> Git написал Линус Торвальдс в апреле 2005 года. Как вы думаете, осталась ли
> в сегодняшнем Git хоть одна строка из самого первого коммита?

Ответы делятся примерно поровну между «конечно нет, двадцать лет прошло» и
«наверное, пара строк в README». Правильный ответ удивляет обе половины.

## 1. Самый первый коммит в истории Git

```bash
cd ~/git-src
git log --reverse --format='%H%n%an <%ae>%n%ad%n%s' | head -4
```

```
e83c5163316f89bfbde7d9ab23ca2e25604af290
Linus Torvalds <torvalds@ppc970.osdl.org>
Thu Apr 7 15:13:13 2005 -0700
Initial revision of "git", the information manager from hell
```

Обратите внимание на почтовый адрес: `ppc970.osdl.org` — это машина, за которой
он тогда сидел.

## 2. Посмотрим на объект целиком

```bash
git cat-file -p e83c5163
```

```
tree 2b5bfdf7798569e0b59b16eb9602d5fa572d6038
author Linus Torvalds <torvalds@ppc970.osdl.org> 1112911993 -0700
committer Linus Torvalds <torvalds@ppc970.osdl.org> 1112911993 -0700

Initial revision of "git", the information manager from hell
```

**Строки `parent` нет.** Это корневой коммит, ему не на что ссылаться. Ровно то,
о чём говорил слайд про объект commit на прошлой лекции, только на настоящей
истории, а не на учебном примере.

## 3. Что вообще было в первой версии

```bash
git ls-tree --name-only e83c5163
git show e83c5163 --stat | tail -1
```

Одиннадцать файлов, 1244 строки. Весь Git целиком.

```
Makefile README cache.h cat-file.c commit-tree.c init-db.c
read-cache.c read-tree.c show-diff.c update-cache.c write-tree.c
```

Сегодня в репозитории 4850 файлов и больше полутора миллионов строк.

## 4. README, который стоит прочитать вслух

```bash
git show e83c5163:README | head -12
```

```
	GIT - the stupid content tracker

"git" can mean anything, depending on your mood.

 - random three-letter combination that is pronounceable, and not
   actually used by any common UNIX command.
 - stupid. contemptible and despicable. simple. Take your pick from the
   dictionary of slang.
 - "global information tracker": you're in a good mood, and it actually
   works for you. Angels sing, and a light suddenly fills the room.
```

## 5. Кульминация: строки 2005 года в сегодняшнем коде

```bash
git blame -L 1,10 read-cache.c
```

```
8bc9a0c769a (Linus Torvalds  2005-04-07 15:16:10 -0700  1) /*
8bc9a0c769a (Linus Torvalds  2005-04-07 15:16:10 -0700  2)  * GIT - The information manager from hell
8bc9a0c769a (Linus Torvalds  2005-04-07 15:16:10 -0700  3)  *
8bc9a0c769a (Linus Torvalds  2005-04-07 15:16:10 -0700  4)  * Copyright (C) Linus Torvalds, 2005
8bc9a0c769a (Linus Torvalds  2005-04-07 15:16:10 -0700  5)  */
```

Коммит `8bc9a0c769` — второй в истории, сделан **через три минуты** после первого.
Эти строки лежат в вашем Git прямо сейчас.

Сколько всего строк того дня дожило только в двух файлах:

```bash
git blame read-cache.c | grep -c '2005-04-0[78]'   # 23
git blame Makefile     | grep -c '2005-04-0[78]'   # 1
```

## 6. Заодно про темп

```bash
git log --reverse --format='%ad' --date=format:'%d %B %Y, %H:%M' | head -1
git log --author=Linus --reverse --format='%ad' --date=format:'%d %B %Y, %H:%M' | sed -n '20p'
```

С первого коммита 7 апреля 15:13 до двадцатого прошло меньше двух суток. Двадцать
коммитов за два дня, и на третий день Git уже вёл собственную историю сам.

```bash
git log --author='Linus Torvalds' --oneline | wc -l   # 1118
git shortlog -sn --all | head -3
```

У Линуса 1118 коммитов, последний в августе 2022. Мейнтейнер Junio Hamano обошёл
его почти в тридцать раз.

## Узкий вывод

Из этого следует ровно две вещи, и обе про механику, а не про Линуса.

**У корневого коммита нет родителя.** Это видно на настоящем объекте, а не на
учебном примере: `git cat-file -p` первого коммита печатает tree, author,
committer и сообщение, и больше ничего.

**История переживает код.** Файлы `cache.h` и `init-db.c` давно исчезли,
а строки из них живут в других файлах, и `git blame` показывает, кто и когда их
написал, через двадцать лет и восемьдесят тысяч коммитов.

Чего из этого НЕ следует: что Git хранит все версии всех файлов целиком. Он хранит
объекты, а blame вычисляет авторство на лету, сравнивая снимки.
