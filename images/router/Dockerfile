# router：實驗室閘道（這裡用 Linux 代替原本的 MikroTik）
FROM ubuntu:24.04
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN echo 'iptables-persistent iptables-persistent/autosave_v4 boolean false' | debconf-set-selections \
 && echo 'iptables-persistent iptables-persistent/autosave_v6 boolean false' | debconf-set-selections \
 && apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus iproute2 iptables iptables-persistent rsyslog ulogd2 \
      iputils-ping tcpdump conntrack curl less nano vim-tiny procps psmisc \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl mask systemd-resolved.service getty.target console-getty.service systemd-logind.service \
      apt-daily.timer apt-daily-upgrade.timer
COPY rootfs/ /
COPY ulogd.sh /tmp/
RUN find /etc/systemd /etc/iptables /etc/sysctl.d /usr/local/sbin /root -type f -exec sed -i 's/\r$//' {} + \
 && sh /tmp/ulogd.sh && rm /tmp/ulogd.sh \
 && chmod +x /usr/local/sbin/* \
 && systemctl enable systemd-networkd rsyslog ulogd2 netfilter-persistent
# 時區：UTC+8（台灣）
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/* \
 && ln -sf /usr/share/zoneinfo/Asia/Taipei /etc/localtime && echo Asia/Taipei > /etc/timezone
ENV TZ=Asia/Taipei
CMD ["/sbin/init"]
