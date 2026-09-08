LAB1_DEST ?= $(HOME)/opr-lab01
LAB2_DEST ?= $(HOME)/opr-lab02

.PHONY: lab1 lab2
lab1:
	@bash lab01-git/setup.sh "$(LAB1_DEST)"

lab2:
	@bash lab02-git/setup.sh "$(LAB2_DEST)"
