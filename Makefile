# Пусто по умолчанию: setup.sh развернёт рядом с этим репозиторием.
# Свой путь: make lab2 LAB2_DEST=/куда/надо
LAB1_DEST ?=
LAB2_DEST ?=
LAB3_DEST ?=
LAB4_DEST ?=
LAB5_DEST ?=
LAB7_DEST ?=
LAB8_DEST ?=
LAB9_DEST ?=
LAB10_DEST ?=
LAB11_DEST ?=

.PHONY: lab1 lab2 lab3 lab3-gitflow lab4 lab5 lab7 lab8 lab9 lab10 lab11
lab1:
	@bash lab01-git/setup.sh "$(LAB1_DEST)"

lab2:
	@bash lab02-git/setup.sh "$(LAB2_DEST)"

lab3:
	@bash lab03-hooks/setup.sh "$(LAB3_DEST)"

lab3-gitflow:
	@bash lab03-hooks/gitflow.sh "$(LAB3_DEST)"

# Занятие 4 разворачивается ВНУТРИ Linux и от root: нужны useradd и mount.
lab4:
	@sudo bash lab04-linux/setup.sh "$(LAB4_DEST)"

# Занятие 5 разворачивается ВНУТРИ Linux и от root: нужны /proc, /etc и systemd.
lab5:
	@sudo bash lab05-linux/setup.sh "$(LAB5_DEST)"

# Занятие 7 — bash, root не нужен.
lab7:
	@bash lab07-bash/setup.sh "$(LAB7_DEST)"

# Занятие 8 — bash, root не нужен.
lab8:
	@bash lab08-bash/setup.sh "$(LAB8_DEST)"

# Занятие 8+9 — задачи на bash, root не нужен.
lab9:
	@bash lab09-bash/setup.sh "$(LAB9_DEST)"

# Занятие 10 — Docker 1, root не нужен, нужен запущенный Docker.
lab10:
	@bash lab10-docker/setup.sh "$(LAB10_DEST)"

# Занятие 11 — Docker 2, root не нужен, нужен запущенный Docker.
lab11:
	@bash lab11-docker/setup.sh "$(LAB11_DEST)"
