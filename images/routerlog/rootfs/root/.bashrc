[ -f /etc/skel/.bashrc ] && . /etc/skel/.bashrc
PS1='\[\e[1;36m\]root@routerlog\[\e[0m\]:\w# '
cat <<'EOF'
────────────────────────────────────────────────────────
 routerlog · log 主機（10.31.1.20）
   準備拿來收實驗室的 log，但還沒設定任何接收服務
   目前的 rsyslog 只記錄本機訊息；工具有 rsyslog、tcpdump
────────────────────────────────────────────────────────
EOF
