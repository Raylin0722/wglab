# 情境角色：學校、網際網路、在家的 WireGuard 使用者、pc1、pc2、印表機
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 iproute2 wireguard-tools iputils-ping curl procps \
 && rm -rf /var/lib/apt/lists/*
COPY actors.py nsact.py /opt/wglab/
RUN sed -i 's/\r$//' /opt/wglab/*.py
ENTRYPOINT ["python3", "/opt/wglab/actors.py"]
