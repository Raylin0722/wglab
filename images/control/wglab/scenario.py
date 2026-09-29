#!/usr/bin/env python3
"""「模擬一天」：把實驗室一天會發生的事壓縮在幾分鐘內。

  day    給玩家的模擬（約 3 分鐘）
  check  驗收用的模擬（約 1 分鐘，由 check.py 呼叫）

狀態寫在 /run/wglab/scenario.json，控制台只顯示「進行中／完成」與經過時間。
"""
import itertools
import json
import os
import subprocess
import sys
import threading
import time

from common import CLIENT_CONF, RUN, api, dx

STATUS = f'{RUN}/scenario.json'
UPGRADE = r"""
day=$(date +%F); t0=$(date +%T); t1=$(date -d +36sec +%T)
printf '
Start-Date: %s  %s
Commandline: /usr/bin/unattended-upgrade
Upgrade: systemd:amd64 (255.4-1ubuntu8.17, 255.4-1ubuntu8.18), udev:amd64 (255.4-1ubuntu8.17, 255.4-1ubuntu8.18), libsystemd0:amd64 (255.4-1ubuntu8.17, 255.4-1ubuntu8.18)
End-Date: %s  %s
' "$day" "$t0" "$day" "$t1" >> /var/log/apt/history.log
logger -t unattended-upgrade 'Packages that will be upgraded: libsystemd0 systemd udev'
systemctl restart systemd-networkd
networkctl reconfigure ens18
"""


def printers_users():
    """會列印的機器：（容器、名稱、自己的 IP）"""
    wg = [(f'home-{x}', f'client-{x}', open(f'{CLIENT_CONF}/{x}.addr').read().strip()) for x in ('a', 'c')]
    lan = [('pc1', 'pc1', '10.31.1.101'), ('pc2', 'pc2', '10.31.1.102')]
    return wg + lan


def nsrun(svc, *args, wait=True):
    """在情境角色的容器裡做一個動作（nsact.py）。"""
    cmd = ('python3', '/opt/wglab/nsact.py', *args)
    if wait:
        return dx(svc, *cmd, timeout=40)[0]
    return dx(svc, *cmd, detach=True)


def unattended_upgrade():
    """自動更新：更新 systemd 套件時 networkd 會被重啟，介面也會重新設定。"""
    dx('wg227', 'bash', '-c', UPGRADE, timeout=60)


def add_visitor_peer():
    """有人在 wg-portal 新增了一個 peer（會觸發路由同步）；每次模擬只保留一個 visitor。"""
    from urllib.parse import quote
    try:
        for p in api('GET', '/peer/by-interface/wg0'):
            if p['DisplayName'].startswith('visitor-'):
                api('DELETE', '/peer/by-id/' + quote(p['Identifier'], safe=''))
        p = api('GET', '/peer/prepare/wg0')
        p['DisplayName'] = 'visitor-' + time.strftime('%m%d-%H%M')
        api('POST', '/peer/new', p)
    except Exception:
        pass


class Day:
    def __init__(self, mode):
        self.mode = mode
        fast = mode == 'check'
        self.duration = 70 if fast else 180
        self.plan = [  # （開始秒數、動作）
            (5 if fast else 15, add_visitor_peer),
            (10 if fast else 35, unattended_upgrade),
            (30 if fast else 60, lambda: nsrun('home-b', 'scan', open(f'{CLIENT_CONF}/b.addr').read().strip(),
                                               '10.31.22', '0.1' if fast else '0.45', wait=False)),
        ]
        self.print_gap = 3 if fast else 6
        self.stop = threading.Event()
        self.t0 = None

    def status(self, **extra):
        os.makedirs(RUN, exist_ok=True)
        el = int(time.time() - self.t0) if self.t0 else 0
        json.dump({'mode': self.mode, 'running': not self.stop.is_set(), 'started': self.t0,
                   'elapsed': min(el, self.duration), 'duration': self.duration, **extra}, open(STATUS, 'w'))

    def loop(self, gap, fn):
        while not self.stop.wait(gap):
            try:
                fn()
            except Exception:
                pass

    def run(self):
        self.t0 = time.time()
        self.status()
        users = itertools.cycle(printers_users() + printers_users()[:2])   # WireGuard 使用者印得比較多
        job = itertools.count(1)

        def do_print():
            ns, name, ip = next(users)
            nsrun(ns, 'print', name, ip, f'job-{next(job):03d}', wait=False)

        def do_browse():
            for ns in ('pc1', 'pc2'):
                nsrun(ns, 'browse', 'http://198.51.100.10/', wait=False)
            for ns in ('home-a', 'home-c'):
                nsrun(ns, 'browse', 'http://10.31.1.101/', wait=False)

        loops = [threading.Thread(target=self.loop, args=a, daemon=True) for a in
                 ((self.print_gap, do_print), (8, do_browse), (10, lambda: nsrun('pc1', 'bcast', '10.31.1.255', wait=False)))]
        for t in loops:
            t.start()
        for at, fn in self.plan:
            threading.Timer(at, fn).start()
        while time.time() - self.t0 < self.duration:
            self.status()
            time.sleep(1)
        self.stop.set()
        self.status(finished=time.time())


def running():
    try:
        s = json.load(open(STATUS))
        return s['running'] and time.time() - s['started'] < s['duration'] + 30
    except Exception:
        return False


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'day'
    if running():
        sys.exit('模擬正在進行中')
    Day(mode).run()
