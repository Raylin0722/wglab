[ -f /etc/skel/.bashrc ] && . /etc/skel/.bashrc
PS1='\[\e[1;33m\]root@router\[\e[0m\]:\w# '
cat <<'EOF'
────────────────────────────────────────────────────────
 router · 實驗室閘道（這裡用 Linux 代替原本的 MikroTik）
   wan 203.0.113.6（學校網路）· lan 10.31.1.254 · guest 10.31.2.254 · svc 10.31.3.1
   網路設定：/etc/systemd/network/（systemd-networkd）
   防火牆：iptables；存檔用 netfilter-persistent save（開機載入 /etc/iptables/rules.v4）
   syslog：rsyslog，目前只存在本機
 注意：這個環境的 iptables -j LOG 會自動改成 NFLOG，由 ulogd 寫進 syslog，效果相同
────────────────────────────────────────────────────────
EOF
