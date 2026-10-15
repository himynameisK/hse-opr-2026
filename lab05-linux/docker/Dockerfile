# Занятие 5 для тех, у кого не оказалось виртуальной машины.
#
# Внутри — systemd как PID 1, поэтому делаются все четыре заявки, включая
# четвёртую. Это не замена виртуалке: на занятии 6 она понадобится всё равно.
#
# Собрать и запустить (из корня репозитория курса):
#
#   docker build -t opr-lab05 lab05-linux/docker
#   docker run -d --name lab05 --privileged --cgroupns=host \
#     -v /sys/fs/cgroup:/sys/fs/cgroup:rw -v "$PWD":/course:ro opr-lab05
#   docker exec -it lab05 bash
#
# Дальше внутри контейнера как в виртуалке:
#
#   bash /course/lab05-linux/setup.sh
#   /opt/opr-lab05/check.py
#
# --privileged и cgroupns=host нужны именно systemd: без них он не поднимется
# и контейнер остановится сразу. Остановить и убрать за собой:
#
#   docker rm -f lab05
FROM debian:12

# python3 — заявки 1 и 3; tmux — 2 и 4; passwd даёт useradd и su;
# procps и psmisc — ps и pstree; iproute2 — ss; systemd-sysv ставит /sbin/init.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      systemd systemd-sysv python3 procps psmisc tmux passwd iproute2 \
 && rm -rf /var/lib/apt/lists/*

# Иначе docker stop ждёт десять секунд и бьёт SIGKILL: systemd завершается
# по SIGRTMIN+3, а не по SIGTERM.
STOPSIGNAL SIGRTMIN+3

CMD ["/sbin/init"]
