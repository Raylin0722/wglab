"""第一次啟動（或 227 被重建後）：用 wg-portal 的 API 建立 wg0 與 peer，還原「9/18 當下的 227」。"""
import os
import subprocess
import time

from common import CLIENT_CONF, api, containers, dx, log, ns

# 照 227 當時的寫法：放行轉送、MASQUERADE，以及 6/24 加上的那條 /24
POSTUP = ('iptables -A FORWARD -i wg0 -j ACCEPT; iptables -A FORWARD -o wg0 -j ACCEPT; '
          'iptables -t nat -A POSTROUTING -s 10.31.22.0/24 -o ens18 -j MASQUERADE; '
          'ip route replace 10.31.22.0/24 dev wg0')

# （名稱, 位址, 在情境裡的角色：a/b/c 是會真的連線的 client）
PEERS = [('lin-laptop', '10.31.22.3', 'a'), ('chen-desktop', '10.31.22.4', None), ('wu-laptop', '10.31.22.5', 'b'),
         ('huang-phone', '10.31.22.6', None), ('tsai-laptop', '10.31.22.8', 'c'), ('lee-ipad', '10.31.22.9', None),
         ('chang-desktop', '10.31.22.11', None), ('kuo-laptop', '10.31.22.12', None)]


def genkey():
    priv = subprocess.run(['wg', 'genkey'], capture_output=True, text=True).stdout.strip()
    pub = subprocess.run(['wg', 'pubkey'], input=priv, capture_output=True, text=True).stdout.strip()
    return priv, pub


def write_client(role, addr, priv, psk, server_pub):
    os.makedirs(CLIENT_CONF, exist_ok=True)
    with open(f'{CLIENT_CONF}/{role}.conf', 'w') as f:
        f.write(f'[Interface]\nPrivateKey = {priv}\nAddress = {addr}/24\n\n[Peer]\nPublicKey = {server_pub}\n'
                f'PresharedKey = {psk}\nEndpoint = 203.0.113.6:443\nAllowedIPs = 10.31.0.0/16\nPersistentKeepalive = 25\n')
    with open(f'{CLIENT_CONF}/{role}.addr', 'w') as f:
        f.write(addr + '\n')


def fake_apt_history():
    """過去幾次 unattended-upgrades 更新 systemd 的紀錄（每天約 14 點）。"""
    lines = []
    for d in (108, 101, 100, 60, 58, 47, 32, 25):
        day = time.strftime('%Y-%m-%d', time.localtime(time.time() - d * 86400))
        a, b = d % 9, d % 9 + 1
        lines.append(f'\nStart-Date: {day}  14:0{d % 7}:12\nCommandline: /usr/bin/unattended-upgrade\n'
                     f'Upgrade: systemd:amd64 (255.4-1ubuntu8.{a}, 255.4-1ubuntu8.{b}), '
                     f'udev:amd64 (255.4-1ubuntu8.{a}, 255.4-1ubuntu8.{b})\nEnd-Date: {day}  14:0{d % 7}:48\n')
    dx('wg227', 'sh', '-c', 'cat >> /var/log/apt/history.log', input=''.join(lines))


def seed():
    # 先拆掉 client 舊的 wg0，寫好新設定後再由接線程式重建
    for svc, (_, p, _) in containers().items():
        if svc.startswith('home-'):
            ns(p, 'ip', 'link', 'del', 'wg0')
    for f in os.listdir(CLIENT_CONF) if os.path.isdir(CLIENT_CONF) else []:
        os.remove(f'{CLIENT_CONF}/{f}')
    iface = api('GET', '/interface/prepare')
    iface.update(Identifier='wg0', DisplayName='實驗室 WireGuard', Mode='server', Addresses=['10.31.22.1/24'],
                 ListenPort=443, PostUp=POSTUP, PeerDefNetwork=['10.31.22.0/24'], PeerDefEndpoint='203.0.113.6:443',
                 PeerDefAllowedIPs=['10.31.0.0/16'], PeerDefPersistentKeepalive=25, PeerDefDns=[])
    api('POST', '/interface/new', iface)
    server_pub = api('GET', '/interface/by-id/wg0')['PublicKey']
    for name, addr, role in PEERS:
        priv, pub = genkey()
        psk = subprocess.run(['wg', 'genpsk'], capture_output=True, text=True).stdout.strip()
        p = api('GET', '/peer/prepare/wg0')
        p.update(Identifier=pub, DisplayName=name, Addresses=[f'{addr}/32'], PrivateKey=priv, PublicKey=pub, PresharedKey=psk)
        api('POST', '/peer/new', p)
        if role:
            write_client(role, addr, priv, psk, server_pub)
    fake_apt_history()
    log('wg-portal：已建立 wg0 與 8 個 peer')


def day_job(job):
    """「模擬一天」（約 3 分鐘）。"""
    import scenario
    job.log('實驗室開始運作一天（約 3 分鐘）…')
    scenario.Day('day').run()
    job.log('完成')


# 初始化進度（網頁顯示「初始化中」畫面用）。control 剛啟動時還不知道要不要初始化，先當作進行中。
INIT = {'active': True, 'step': 'boot', 'detail': ''}


def init_job(job):
    """初始化：只做讓環境「已經出過事」需要的最少動作，完整的一天等學生按「模擬一天」才跑。
    （wg0 與 peer 建好時，wg-portal 的同步已經刪掉 /24，外漏的條件本來就成立）"""
    import machines
    import scenario

    def say(*a):
        INIT['detail'] = ' '.join(str(x) for x in a)
        job.log(*a)

    INIT.update(step='ready', detail='')
    machines.wait_ready(say, timeout=120)
    INIT.update(step='evidence', detail='')
    b = open(f'{CLIENT_CONF}/b.addr').read().strip()
    say('client-b 掃描整段 WireGuard 網段（學校會記錄 UDP 137）…')
    dx('home-b', 'ping', '-c2', '-W1', '10.31.1.101', timeout=10)      # 先讓 client-b 握手，掃描才不會掉前幾個
    scenario.nsrun('home-b', 'scan', b, '10.31.22', '0.05')
    say('WireGuard 使用者與實驗室電腦各列印幾張…')
    for _ in range(2):
        for svc, name, ip in scenario.printers_users():
            scenario.nsrun(svc, 'print', name, ip, 'init')
    time.sleep(5)                                                      # 等印表機回撥
    say('完成，可以開始調查')


def loop():
    """等 wg-portal 起來；wg0 不存在就初始化（227 被重建時也會重來一次）。"""
    import jobs
    need_init = False
    while True:
        try:
            ids = [i['Identifier'] for i in api('GET', '/interface/all')]
            if 'wg0' not in ids:
                INIT.update(active=True, step='seed', detail='')
                seed()
                need_init = True
            if need_init and not jobs.busy():
                if jobs.start('init', '初始化', init_job):
                    need_init = False
            if not need_init and not (jobs.busy() and jobs.current().kind == 'init'):
                INIT['active'] = False
        except Exception:
            pass
        time.sleep(2)
