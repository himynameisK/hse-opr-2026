"""Утилита-приветствие. Код не менять.

    greet.py --name Ivan          Привет, Ivan!
    greet.py --anon               Привет, незнакомец!
    greet.py --name Ivan --shout  ПРИВЕТ, IVAN!
Ровно одно из --name и --anon обязательно.
"""
import argparse

p = argparse.ArgumentParser(prog="greet")
who = p.add_mutually_exclusive_group(required=True)
who.add_argument("--name", help="кого приветствовать")
who.add_argument("--anon", action="store_true", help="приветствовать без имени")
p.add_argument("--shout", action="store_true", help="заглавными буквами")
a = p.parse_args()

text = "Привет, {}!".format("незнакомец" if a.anon else a.name)
print(text.upper() if a.shout else text)
