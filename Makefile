LAB1_DEST ?= $(HOME)/opr-lab01
LAB2_DEST ?= $(HOME)/opr-lab02
LAB3_DEST ?= $(HOME)/opr-lab03

.PHONY: lab1 lab2 lab3
lab1:
	@bash lab01-git/setup.sh "$(LAB1_DEST)"

lab2:
	@bash lab02-git/setup.sh "$(LAB2_DEST)"

lab3:
	@bash lab03-hooks/setup.sh "$(LAB3_DEST)"
