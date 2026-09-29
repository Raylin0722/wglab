#!/usr/bin/env python3
"""control 的主程式：接線（plumber）、初始化 wg-portal（seed）、網頁（web）。"""
import threading

import plumber
import seed
import web
from common import log, project

if __name__ == '__main__':
    log(f'control 啟動（compose 專案：{project()}）')
    threading.Thread(target=plumber.loop, daemon=True).start()
    threading.Thread(target=seed.loop, daemon=True).start()
    web.serve()
