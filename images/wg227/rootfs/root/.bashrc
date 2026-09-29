[ -f /etc/skel/.bashrc ] && . /etc/skel/.bashrc
PS1='\[\e[1;32m\]root@wg227\[\e[0m\]:\w# '
cat <<'EOF'
────────────────────────────────────────────────────────
 227 · WireGuard 伺服器（Ubuntu 24.04）
   ens18 10.31.1.27/24 · wg0 由 wg-portal v2.2.3 管理（systemctl status wg-portal）
   wg-portal 網頁：http://localhost:8888
   eth0 是練習環境的管理網路（只給網頁用），不是實驗室網路的一部分
 注意：這個環境的 iptables -j LOG 會自動改成 NFLOG，由 ulogd 寫進 syslog，效果相同
────────────────────────────────────────────────────────
EOF
