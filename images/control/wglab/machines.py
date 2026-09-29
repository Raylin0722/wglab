"""玩家機器（227、router、routerlog）的重開、就緒檢查與從頭來過。"""
import datetime
import glob
import os
import subprocess
import threading
import time

from common import CALLBACKS, CLIENT_CONF, SCHOOL, STATE, api, containers, dx, ns, project, run

PLAYER = ('wg227', 'router', 'routerlog')
NAMES = {'wg227': '227', 'router': 'router', 'routerlog': 'routerlog'}


def started_at(info):
    """docker 的 StartedAt（奈秒）轉成 epoch 秒。"""
    s = info[2].rstrip('Z')
    s = s[:26] if '.' in s else s
    return datetime.datetime.fromisoformat(s).replace(tzinfo=datetime.timezone.utc).timestamp()


def restart(svcs, log):
    """只重開指定的機器（同時進行）；網路線由接線程式自動重接。"""
    cs = containers()
    log('重開：' + '、'.join(NAMES.get(s, s) for s in svcs))
    ths = [threading.Thread(target=run, args=(['docker', 'restart', '-t', '20', cs[s][0]],), kwargs={'timeout': 90})
           for s in svcs if s in cs]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    return time.time()


def _handshake(p):
    out = ns(p, 'wg', 'show', 'wg0', 'latest-handshakes').stdout.split()
    return int(out[1]) if len(out) >= 2 and out[1].isdigit() else 0


def wait_ready(log, since=0, timeout=150):
    """等到三台玩家機器開機完成、wg-portal 回應，且兩台會連線的 client 都在 since 之後重新握手。"""
    import plumber
    deadline, last, stale_since = time.time() + timeout, '', None
    while time.time() < deadline:
        cs = containers()
        why = ''
        missing = [s for s in PLAYER if s not in cs]
        if missing:
            why = '等待機器開機：' + '、'.join(NAMES[s] for s in missing)
        else:
            since_boot = max(since, max(started_at(cs[s]) for s in ('wg227',)))
            booting = [s for s in PLAYER
                       if dx(s, 'systemctl', 'is-system-running', timeout=10)[1].strip() not in ('running', 'degraded')]
            if booting:
                why = '等待開機完成：' + '、'.join(NAMES[s] for s in booting)
            else:
                try:
                    ok = any(i['Identifier'] == 'wg0' for i in api('GET', '/interface/all'))
                except Exception:
                    ok = False
                if not ok:
                    why = '等待 wg-portal 啟動'
                else:
                    stale = []
                    for h in ('home-a', 'home-c'):
                        if h not in cs:
                            stale.append(h)
                            continue
                        if _handshake(cs[h][1]) < since_boot:
                            ns(cs[h][1], 'ping', '-c1', '-W1', '10.31.22.1')   # 送點流量，讓 client 重新握手
                            stale.append(h)
                    if stale:
                        why = '等待 WireGuard client 重新連線'
                        # 227 重開後 client 要等十幾秒到一分鐘才會自己重新握手；
                        # 超過 10 秒就讓 client 重建連線（像筆電重新連 VPN），加快驗收
                        stale_since = stale_since or time.time()
                        if time.time() - stale_since > 10:
                            for h in stale:
                                if h in cs:
                                    plumber.wg_up(cs[h][1], h[-1])
                            stale_since = time.time()
                    else:
                        # 最後確認路真的通了（最多 30 秒；學生的設定讓它不通時照樣繼續，由驗收判定）
                        for _ in range(15):
                            if ns(cs['home-a'][1], 'ping', '-c1', '-W1', '10.31.1.101').returncode == 0:
                                break
                            time.sleep(1)
                        log('實驗室已就緒')
                        return True
        if why != last:
            log(why)
            last = why
        time.sleep(3)
    log('等待逾時，仍繼續（可能是 WireGuard 本身連不上）')
    return False


def reset(job):
    """從頭來過：重建 227、router、routerlog，清掉學校與列印的紀錄，wg-portal 會重新初始化。"""
    job.log('重建 227、router、routerlog（所有設定都會清掉）…')
    r = run(['docker', 'compose', '-p', project(), '-f', '/project/compose.yml', 'up', '-d', '--no-build',
             '--force-recreate', '--no-deps', *PLAYER], timeout=300)
    if r.returncode:
        job.log('重建失敗：' + (r.stderr.strip().splitlines() or ['?'])[-1])
        return {'ok': False}
    # 學校的程式會一直讀寫這兩個檔，清空內容而不刪檔
    open(f'{SCHOOL}/raw.jsonl', 'w').close()
    with open(f'{SCHOOL}/alerts.json', 'w') as f:
        f.write('[]')
    for f in glob.glob(f'{CALLBACKS}/*') + glob.glob(f'{CLIENT_CONF}/*') + glob.glob(f'{STATE}/check-history.jsonl'):
        try:
            os.remove(f)
        except OSError:
            pass
    job.log('已清除學校紀錄、列印紀錄與驗收紀錄')
    job.log('等待 wg-portal 重新初始化…')
    deadline = time.time() + 180
    while time.time() < deadline and not all(os.path.exists(f'{CLIENT_CONF}/{x}.conf') for x in 'abc'):
        time.sleep(3)
    wait_ready(job.log)
    job.log('完成。接著會自動跑一次「模擬一天」。')
    return {'ok': True}
