# Пусто по умолчанию: setup.sh развернёт рядом с этим репозиторием.
# Свой путь: make lab2 LAB2_DEST=/куда/надо
LAB1_DEST ?=
LAB2_DEST ?=
LAB3_DEST ?=
LAB4_DEST ?=

.PHONY: lab1 lab2 lab3 lab3-gitflow lab4
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
