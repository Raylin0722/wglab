#!/usr/bin/env bash
# 打包給玩家的檔案（不含講師資料）
set -eu
cd "$(dirname "$0")"
tar czf wglab-player.tar.gz .gitattributes .dockerignore compose.yml images player topology.html README.md
echo "已產生 wglab-player.tar.gz"
