#!/bin/sh
# 產生 /etc/ulogd.conf：NFLOG group 1 → syslog（kern）；外掛路徑依 CPU 架構不同
set -e
sed -i 's/\r$//' /usr/local/sbin/iptables
P=$(dirname "$(find /usr/lib -name ulogd_inppkt_NFLOG.so | head -1)")
cat > /etc/ulogd.conf <<EOF
# 容器內 iptables -j LOG 不會寫進 kernel log，所以 LOG 會被轉成 NFLOG group 1，由 ulogd 寫進 syslog
[global]
logfile="syslog"
loglevel=5
plugin="$P/ulogd_inppkt_NFLOG.so"
plugin="$P/ulogd_raw2packet_BASE.so"
plugin="$P/ulogd_filter_IFINDEX.so"
plugin="$P/ulogd_filter_IP2STR.so"
plugin="$P/ulogd_filter_PRINTPKT.so"
plugin="$P/ulogd_output_SYSLOG.so"
stack=log1:NFLOG,base1:BASE,ifi1:IFINDEX,ip2str1:IP2STR,print1:PRINTPKT,sys1:SYSLOG

[log1]
group=1

[sys1]
facility=LOG_KERN
level=LOG_WARNING
EOF
