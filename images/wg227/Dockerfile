# 227：WireGuard 伺服器（Ubuntu 24.04 + systemd-networkd + wg-portal v2.2.3）
FROM wgportal/wg-portal:v2.2.3 AS wgportal

FROM ubuntu:24.04
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus iproute2 iptables nftables wireguard-tools \
      iputils-ping tcpdump conntrack curl jq rsyslog ulogd2 \
      less nano vim-tiny procps psmisc ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && systemctl mask systemd-resolved.service getty.target console-getty.service systemd-logind.service \
      apt-daily.timer apt-daily-upgrade.timer
COPY --from=wgportal /app/wg-portal /usr/local/bin/wg-portal
COPY rootfs/ /
COPY ulogd.sh /tmp/
# 檔案若是從 Windows 取得可能是 CRLF，統一成 LF；iptables LOG → NFLOG → ulogd → syslog
RUN find /etc/systemd /etc/wg-portal /usr/local/sbin /usr/local/lib/wg227 /root -type f -exec sed -i 's/\r$//' {} + \
 && sh /tmp/ulogd.sh && rm /tmp/ulogd.sh \
 && chmod +x /usr/local/sbin/* /usr/local/lib/wg227/* \
 && systemctl enable systemd-networkd rsyslog ulogd2 lab-mgmt wg-portal wgportal-after-networkd
CMD ["/sbin/init"]
