#!/usr/bin/env python3
"""驗收（全自動）：
  1. 檢查出題與驗收程式有沒有被改過
  2. 等實驗室就緒 → 第 1 輪（壓縮版的模擬一天，含一次自動更新）
  3. 只重開 227、router、routerlog → 等就緒 → 第 2 輪
  4. 兩輪都通過，而且重開前後設定沒變，才算通過

  lab check            只顯示每一項通過與否
  lab check --detail   顯示細節（講師用）
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time

import machines
import scenario
from common import CALLBACKS, SCHOOL, STATE, api, containers, dx, ns

HISTORY = f'{STATE}/check-history.jsonl'
PLAYER = machines.PLAYER
LIB = '/opt/wglab'

# 會影響結果的設定（在各台機器裡計算雜湊）
CONFIG = {
    'wg227': '/etc/systemd/network /etc/systemd/networkd.conf /etc/systemd/networkd.conf.d /etc/systemd/system '
             '/etc/rsyslog.conf /etc/rsyslog.d /usr/local/sbin /etc/iptables /etc/sysctl.d',
    'router': '/etc/systemd/network /etc/systemd/networkd.conf.d /etc/systemd/system /etc/iptables /etc/sysctl.d '
              '/etc/rsyslog.conf /etc/rsyslog.d /etc/ulogd.conf',
    'routerlog': '/etc/systemd/network /etc/systemd/system /etc/rsyslog.conf /etc/rsyslog.d',
}
ITEMS = ('外漏', 'WireGuard 使用者的日常使用', '自動更新之後', '紀錄')


def reach(svc, target, kind='ping'):
    # ping 3 次（約 1.5 秒內）有一次回應就算通，避免單一封包掉了誤判
    cmd = ('ping', '-c3', '-i0.5', '-W1', target) if kind == 'ping' else ('curl', '-sf', '-m4', target)
    return dx(svc, *cmd, timeout=15)[0]


def tamper():
    """出題與驗收程式跟建置時的雜湊不同 → 回傳有問題的檔案。只能偵測，擋不住刻意重建映像。"""
    bad = []
    for line in open(f'{LIB}/.manifest'):
        digest, name = line.split()
        path = f'{LIB}/{name}'
        if not os.path.exists(path) or hashlib.sha256(open(path, 'rb').read()).hexdigest() != digest:
            bad.append(f'control:{name}')
    expect = dict(reversed(l.split()) for l in open(f'{LIB}/.manifest-actor'))
    for svc in ('school', 'internet', 'home-a', 'home-b', 'home-c', 'pc1', 'pc2', 'printer'):
        ok, out = dx(svc, 'sha256sum', *[f'/opt/wglab/{n}' for n in expect])
        got = {l.split()[1].rsplit('/', 1)[1]: l.split()[0] for l in out.splitlines() if l.strip()}
        bad += [f'{svc}:{n}' for n, d in expect.items() if got.get(n) != d]
    return bad


def fingerprint():
    h = hashlib.sha256()
    for svc in ('wg227', 'router'):
        # 規則集合（去重、不看順序）：wg-portal 儲存介面時會再跑一次 PostUp（#469），規則可能重複
        # Docker 內建 DNS 的規則（DOCKER_OUTPUT 等）每次重開 port 都不同，不算學生的設定
        out = dx(svc, 'iptables-save')[1]
        h.update('\n'.join(sorted({l.split(' [')[0] for l in out.splitlines()
                                   if not l.startswith(('#', ':')) and 'DOCKER_' not in l})).encode())
    for svc, paths in CONFIG.items():
        out = dx(svc, 'sh', '-c', f'find {paths} -type f -o -type l 2>/dev/null | sort | '
                                  f'while read f; do echo "$f"; cat "$f" 2>/dev/null; readlink "$f"; done | sha256sum')[1]
        h.update(f'{svc}:{out}'.encode())
    try:
        i = api('GET', '/interface/by-id/wg0')
        h.update(json.dumps({k: i.get(k) for k in ('PostUp', 'PreUp', 'PostDown', 'Addresses')}, sort_keys=True).encode())
    except Exception:
        pass
    return h.hexdigest()[:16]


def run_round(log):
    """一輪：壓縮版的模擬一天（約 70 秒），回傳 [(項目, 通過, 細節)]。"""
    cs = containers()
    t0 = time.time()
    # 錄下這段期間所有送到 routerlog 的封包（只進入它的網路，不管學生用什麼程式、存在哪裡）
    cap = subprocess.Popen(['nsenter', '-t', str(cs['routerlog'][1]), '-n', 'tcpdump', '-l', '-n', '-A', '-i', 'eth0',
                            'dst host 10.31.1.20 and (udp or tcp)'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors='replace')
    captured = []
    threading.Thread(target=lambda: captured.extend(cap.stdout), daemon=True).start()

    day = scenario.Day('check')
    th = threading.Thread(target=day.run)
    th.start()
    probes = {}

    def probe(name, at, fn):
        threading.Timer(at, lambda: probes.setdefault(name, []).append(fn())).start()

    upgrade = [a for a, f in day.plan if f is scenario.unattended_upgrade][0]
    wg_ok = lambda: all(reach(f'home-{x}', '10.31.1.101') for x in ('a', 'c'))
    # 自動更新之後 2 秒與 15 秒：WireGuard 使用者都要連得到實驗室
    probe('networkd', upgrade + 2, wg_ok)
    probe('networkd', upgrade + 15, wg_ok)
    # 平常的使用：WireGuard 使用者連實驗室服務；實驗室電腦與 227 上網
    for at in (upgrade + 25, upgrade + 45):
        probe('usage', at, lambda: all([
            reach('home-a', 'http://10.31.1.101/', 'curl'), reach('home-c', 'http://10.31.1.101/', 'curl'),
            reach('pc1', 'http://198.51.100.10/', 'curl'), reach('wg227', 'http://198.51.100.10/', 'curl')]))
    while th.is_alive():
        th.join(10)
        log(f'  模擬中… {int(time.time() - t0)} / {day.duration} 秒')
    time.sleep(6)                       # 等最後幾次列印的回撥

    leaks = []
    raw = f'{SCHOOL}/raw.jsonl'
    for line in open(raw) if os.path.exists(raw) else []:
        r = json.loads(line)
        if r['t'] >= t0:
            leaks.append(r)
    n137 = sum(1 for r in leaks if r['proto'] == 'udp' and r['dport'] == 137)

    cb = {}
    for x in ('a', 'c'):
        f = f'{CALLBACKS}/{x}-callbacks.log'
        cb[x] = sum(1 for l in open(f) if float(l.split()[0]) >= t0) if os.path.exists(f) else 0

    cap.terminate()
    time.sleep(1)
    ports, logged, port = set(), 0, None
    for l in captured:                 # tcpdump -A：一行封包標頭，後面接內容
        m = re.search(r' > 10\.31\.1\.20\.(\d+):', l)
        if m:
            port = m[1]
        if port and 'DST=10.31.22.' in l and 'DPT=137' in l:
            logged += 1
            ports.add(port)
    listen = ns(containers()['routerlog'][1], 'ss', '-Hlnut').stdout
    listening = {p for p in ports if re.search(rf':{p}\s', listen)}

    return [
        ('外漏', not leaks, f'學校收到 {len(leaks)} 筆送往私有位址的封包（其中 UDP 137：{n137}）'),
        ('WireGuard 使用者的日常使用', all(probes.get('usage', [False])) and all(v > 0 for v in cb.values()),
         f'連線／上網：{probes.get("usage")}；印表機回撥 client-a {cb["a"]} 次、client-c {cb["c"]} 次'),
        ('自動更新之後', all(probes.get('networkd', [False])), f'更新後 2 秒、15 秒：{probes.get("networkd")}'),
        ('紀錄', logged > 0 and bool(listening),
         f'送到 routerlog、提到送往 10.31.22.x:137 的 log 封包 {logged} 個（目的 port {sorted(ports)}，有程式在收的 {sorted(listening)}）'),
    ]


def full(log, detail=False):
    """完整驗收；回傳 {'passed': bool, 'items': [{name, ok, detail}], 'tampered': [...]}。"""
    def show(title, items):
        log(title)
        for name, ok, d in items:
            log(f'  {"✓" if ok else "✗"}  {name}' + (f'｜{d}' if detail else ''))

    bad = tamper()
    if bad:
        log('偵測到出題或驗收程式被修改，拒絕驗收：' + '、'.join(bad))
        log('請在主機上重新建立環境：docker compose up -d --build --force-recreate')
        return {'passed': False, 'items': [], 'tampered': bad}

    log('等待實驗室就緒…')
    machines.wait_ready(log)
    log('第 1 輪（重開前）：壓縮版的模擬一天，約 70 秒，期間請不要修改設定')
    r1 = run_round(log)
    show('第 1 輪結果', r1)
    fp1 = fingerprint()

    if all(ok for _, ok, _ in r1):
        t = machines.restart(PLAYER, log)
        log('等待重開完成…')
        machines.wait_ready(log, since=t)
        fp2 = fingerprint()
        log('第 2 輪（重開後）：約 70 秒')
        r2 = run_round(log)
        show('第 2 輪結果', r2)
        persisted = fp1 == fp2 and all(ok for _, ok, _ in r2)
        final = [(n, a[1] and b[1], f'重開前：{a[2]}／重開後：{b[2]}') for n, a, b in zip(ITEMS, r1, r2)]
        final.append(('重開後仍有效', persisted,
                      '重開前後設定相同' if fp1 == fp2 else f'重開前後設定不同（{fp1} → {fp2}）'))
    else:
        log('第 1 輪沒有全部通過，這次不重開測試。')
        final = list(r1) + [('重開後仍有效', False, '第 1 輪沒有全部通過，未測')]

    passed = all(ok for _, ok, _ in final)
    show('最終結果', final)
    log('全部通過。' if passed else '還有沒通過的項目。')
    os.makedirs(STATE, exist_ok=True)
    with open(HISTORY, 'a') as f:
        f.write(json.dumps({'time': time.strftime('%F %T'), 'fp': fp1, 'passed': passed,
                            'items': {n: ok for n, ok, _ in final}}, ensure_ascii=False) + '\n')
    return {'passed': passed, 'items': [{'name': n, 'ok': ok, 'detail': d} for n, ok, d in final], 'tampered': []}


if __name__ == '__main__':
    import jobs
    if jobs.busy() or scenario.running():
        sys.exit('有其他工作正在進行，請稍後再驗收')
    full(lambda *a: print(*a, flush=True), detail='--detail' in sys.argv)
