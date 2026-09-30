"""接線：實驗室裡的機器都沒有 Docker 網路，這裡用 veth 把它們接起來，並設定情境角色的位址。
每條線中間是 control 裡的一個 bridge（像一台小交換器）：兩端各用一段 veth 接到 bridge。
某台機器重開時只有它那段線會消失，另一端機器的網卡不受影響（跟真的網路線一樣）。
每 2 秒檢查一次，缺哪段就補哪段。227、router、routerlog 的位址由它們自己的 systemd-networkd 設定。
"""
import os
import time

from common import CLIENT_CONF, CLIENT_LOCK, containers, log, ns, run, wg_stale

# （機器, 網卡名稱）⇄（機器, 網卡名稱）
LINKS = [
    (('router', 'wan'), ('school', 's-lab')),
    (('school', 's-inet'), ('internet', 'i-school')),
    (('internet', 'i-a'), ('home-a', 'eth0')),
    (('internet', 'i-b'), ('home-b', 'eth0')),
    (('internet', 'i-c'), ('home-c', 'eth0')),
    (('router', 'r-227'), ('wg227', 'ens18')),
    (('router', 'r-log'), ('routerlog', 'eth0')),
    (('router', 'r-pc1'), ('pc1', 'eth0')),
    (('router', 'r-pc2'), ('pc2', 'eth0')),
    (('router', 'svc'), ('printer', 'eth0')),
]

# 情境角色的網路設定：（網卡, 位址）清單、default gateway
ACTORS = {
    'school':   ([('s-lab', '203.0.113.1/24'), ('s-inet', '198.51.100.1/24')], None),
    'internet': ([('br0', '198.51.100.10/24')], '198.51.100.1'),
    'home-a':   ([('eth0', '198.51.100.21/24')], '198.51.100.1'),
    'home-b':   ([('eth0', '198.51.100.22/24')], '198.51.100.1'),
    'home-c':   ([('eth0', '198.51.100.23/24')], '198.51.100.1'),
    'pc1':      ([('eth0', '10.31.1.101/24')], '10.31.1.254'),
    'pc2':      ([('eth0', '10.31.1.102/24')], '10.31.1.254'),
    'printer':  ([('eth0', '10.31.3.254/24')], '10.31.3.1'),
}


def has_if(p, name):
    return ns(p, 'ip', 'link', 'show', 'dev', name).returncode == 0


def ensure_bridge(i):
    br = f'wlb{i}'
    if run(['ip', 'link', 'show', 'dev', br]).returncode:
        run(['ip', 'link', 'add', br, 'type', 'bridge'])
        run(['ip', 'link', 'set', br, 'up'])
    return br


def plug(i, side, svc, ifname, p):
    """把某台機器的網卡接到第 i 條線的 bridge：control 端留一段 veth 在 bridge 上，另一段移進機器。"""
    br, local, tmp = ensure_bridge(i), f'wl{i}{side}', f'wt{i}{side}'
    run(['ip', 'link', 'del', local])          # 舊的那段（機器重開後，另一半已經不見了）
    ns(p, 'ip', 'link', 'del', ifname)
    r = run(['ip', 'link', 'add', local, 'type', 'veth', 'peer', 'name', tmp])
    if r.returncode:
        log('接線失敗', svc, ifname, r.stderr.strip())
        return False
    run(['ip', 'link', 'set', local, 'master', br])
    run(['ip', 'link', 'set', local, 'up'])
    run(['ip', 'link', 'set', tmp, 'netns', str(p)])
    ns(p, 'ip', 'link', 'set', tmp, 'name', ifname)
    ns(p, 'ip', 'link', 'set', ifname, 'up')
    return True


def wg_up(p, who):
    """在家的 WireGuard 使用者：依 control 產生的設定建立 wg0。"""
    if not CLIENT_LOCK.acquire(blocking=False):     # 初始化正在改設定，下一輪再建
        return
    try:
        _wg_up(p, who)
    finally:
        CLIENT_LOCK.release()


def _wg_up(p, who):
    conf, addr = f'{CLIENT_CONF}/{who}.conf', f'{CLIENT_CONF}/{who}.addr'
    if not (os.path.exists(conf) and os.path.exists(addr)):
        return
    stripped = f'/run/wglab/{who}.wg'
    os.makedirs('/run/wglab', exist_ok=True)
    with open(conf) as f, open(stripped, 'w') as o:
        o.writelines(l for l in f if not l.startswith('Address'))
    ns(p, 'ip', 'link', 'del', 'wg0')
    ns(p, 'ip', 'link', 'add', 'wg0', 'type', 'wireguard')
    ns(p, 'wg', 'setconf', 'wg0', stripped)
    os.remove(stripped)
    ns(p, 'ip', 'addr', 'add', open(addr).read().strip() + '/24', 'dev', 'wg0')
    ns(p, 'ip', 'link', 'set', 'wg0', 'up')
    ns(p, 'ip', 'route', 'replace', '10.31.0.0/16', 'dev', 'wg0')
    log(f'{who} 的 WireGuard 已連上')


def configure(svc, p):
    addrs, gw = ACTORS[svc]
    ns(p, 'ip', 'link', 'set', 'lo', 'up')
    for k in ('all', 'default'):
        ns(p, 'sysctl', '-qw', f'net.ipv4.conf.{k}.rp_filter=0')
    if svc == 'school':
        ns(p, 'sysctl', '-qw', 'net.ipv4.ip_forward=1')
    if svc == 'internet':
        ns(p, 'ip', 'link', 'add', 'br0', 'type', 'bridge')
        ns(p, 'ip', 'link', 'set', 'br0', 'up')
        for i in ('i-school', 'i-a', 'i-b', 'i-c'):
            ns(p, 'ip', 'link', 'set', i, 'master', 'br0')
    for dev, a in addrs:
        ns(p, 'ip', 'addr', 'replace', a, 'dev', dev)
        ns(p, 'ip', 'link', 'set', dev, 'up')
    if gw:
        ns(p, 'ip', 'route', 'replace', 'default', 'via', gw)
    if svc.startswith('home-') and wg_stale(p, svc[5:]):
        wg_up(p, svc[5:])


def reconcile(force=False):
    cs = containers()
    dirty = set(ACTORS) if force else set()
    for i, link in enumerate(LINKS):
        for side, (svc, ifname) in zip('ab', link):
            if svc not in cs or has_if(cs[svc][1], ifname):
                continue
            if plug(i, side, svc, ifname, cs[svc][1]):
                other = link[1] if side == 'a' else link[0]
                log(f'接線 {svc}:{ifname}（⇄ {other[0]}:{other[1]}）')
                dirty.add(svc)
    # client 設定剛產生（或重新產生）時，WireGuard 也要重建；wg0 還在但用舊金鑰的也一樣
    for x in 'abc':
        svc = f'home-{x}'
        if svc in cs and wg_stale(cs[svc][1], x):
            dirty.add(svc)
    for svc in dirty & set(ACTORS):
        if svc in cs:
            configure(svc, cs[svc][1])


def loop():
    first = True
    while True:
        try:
            reconcile(force=first)
            first = False
        except Exception as e:
            log('接線錯誤', e)
        time.sleep(2)
