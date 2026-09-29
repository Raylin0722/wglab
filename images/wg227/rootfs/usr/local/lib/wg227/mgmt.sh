#!/bin/sh
# 練習環境專用：eth0 是 Docker 的管理網路，只給 wg-portal 網頁（:8888）用。
# 227 真正的網卡是 ens18（由 systemd-networkd 設定，經 router 上網）。
ip route del default dev eth0 2>/dev/null
echo 'nameserver 127.0.0.1' > /etc/resolv.conf
grep -q '# lab hosts' /etc/hosts || cat >> /etc/hosts <<'EOF'
# lab hosts
10.31.1.254 router
10.31.1.20  routerlog
10.31.3.254 printer
EOF
nft delete table inet mgmt_guard 2>/dev/null
nft -f - <<'EOF'
table inet mgmt_guard {
  chain guard_out {
    type filter hook output priority 0; policy accept;
    oifname "eth0" tcp sport 8888 accept
    oifname "eth0" drop
  }
  chain guard_fwd {
    type filter hook forward priority 0; policy accept;
    oifname "eth0" drop
    iifname "eth0" drop
  }
}
EOF
