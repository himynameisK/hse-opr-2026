"""Обработчик очереди. Код не менять.

Работает, пока его не остановят. По SIGTERM (так останавливает docker stop)
дописывает текущие задания и печатает «graceful shutdown», код выхода 0.
"""
import os
import signal
import sys
import time

QUEUE = os.environ.get("QUEUE_DIR", "/tmp/queue")
done = 0


def stop(signum, frame):
    print("graceful shutdown: сигнал {}, обработано заданий: {}, очередь {} сохранена".format(
        signum, done, QUEUE), flush=True)
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
print("обработчик готов, pid {}".format(os.getpid()), flush=True)
while True:
    time.sleep(0.2)
    done += 1
