# routerlog：準備拿來收 log 的主機（還沒設定任何接收服務）
FROM ubuntu:24.04
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus iproute2 rsyslog iputils-ping tcpdump curl less nano vim-tiny procps psmisc \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl mask systemd-resolved.service getty.target console-getty.service systemd-logind.service \
      apt-daily.timer apt-daily-upgrade.timer
COPY rootfs/ /
RUN find /etc/systemd /root -type f -exec sed -i 's/\r$//' {} + \
 && systemctl enable systemd-networkd rsyslog
CMD ["/sbin/init"]
