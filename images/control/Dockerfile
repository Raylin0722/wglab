# control：接線、初始化、「模擬一天」、驗收、網頁（出題程式只在這裡）
# 建置範圍是專案根目錄（compose.yml 裡 context: .），才拿得到玩家文件與情境角色的程式
FROM docker:28-cli AS dockercli

FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-aiohttp iproute2 wireguard-tools tcpdump curl jq ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
# 網頁終端機與 Markdown：建置時下載，執行時不需要外部網路
RUN mkdir -p /opt/wglab/web/vendor && cd /opt/wglab/web/vendor \
 && curl -fsSLo xterm.js    https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/lib/xterm.js \
 && curl -fsSLo xterm.css   https://cdn.jsdelivr.net/npm/@xterm/xterm@5.5.0/css/xterm.css \
 && curl -fsSLo addon-fit.js https://cdn.jsdelivr.net/npm/@xterm/addon-fit@0.10.0/lib/addon-fit.js \
 && curl -fsSLo marked.js   https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js
COPY images/control/wglab/ /opt/wglab/
COPY images/control/web/ /opt/wglab/web/
COPY player/ /opt/wglab/docs/
COPY images/control/lab /usr/local/bin/lab
COPY images/actor/actors.py images/actor/nsact.py /tmp/actor/
# 統一成 LF；記下出題與驗收程式的雜湊（驗收時用來偵測竄改）
RUN sed -i 's/\r$//' /opt/wglab/*.py /usr/local/bin/lab /tmp/actor/*.py \
 && chmod +x /usr/local/bin/lab \
 && cd /opt/wglab && sha256sum *.py > .manifest \
 && cd /tmp/actor && sha256sum *.py > /opt/wglab/.manifest-actor && rm -rf /tmp/actor
WORKDIR /opt/wglab
CMD ["python3", "/opt/wglab/control.py"]
