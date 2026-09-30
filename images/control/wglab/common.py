"""control 共用的小工具：找同一個 compose 專案裡的容器、在容器裡執行指令、呼叫 wg-portal API。"""
import base64
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request

STATE = '/var/lib/wglab'                 # control 自己的狀態（client 設定、驗收紀錄）
CLIENT_CONF = f'{STATE}/clients'
SCHOOL = '/school'                       # 學校的原始紀錄（與 school 共用的 volume）
CALLBACKS = '/clients'                   # 列印回撥紀錄（與 home-*、pc*、printer 共用）
RUN = '/run/wglab'

# seed 重建 wg-portal 與 client 設定期間持有；plumber 建 client 的 wg0 前也要拿到，
# 避免用到上一輪留下、或寫到一半的設定（Mac 上曾出現 home-b 用舊的伺服器金鑰）
CLIENT_LOCK = threading.Lock()

WGP = 'http://wg227:8888/api/v1'
WGP_AUTH = 'admin@lab.local:wglab-api-token-7f3c9a1e5b2d8046'


def run(cmd, timeout=30, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


_project = None


def project():
    global _project
    if not _project:
        me = socket.gethostname()
        _project = run(['docker', 'inspect', '-f', '{{index .Config.Labels "com.docker.compose.project"}}', me]).stdout.strip()
    return _project


def containers():
    """{service: (容器 ID, PID)}，只列正在執行的。"""
    out = run(['docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={project()}']).stdout.split()
    if not out:
        return {}
    info = json.loads(run(['docker', 'inspect', *out]).stdout or '[]')
    res = {}
    for c in info:
        svc = c['Config']['Labels'].get('com.docker.compose.service')
        if svc and c['State']['Running'] and c['State']['Pid']:
            res[svc] = (c['Id'], c['State']['Pid'], c['State']['StartedAt'])
    return res


def cid(service):
    c = containers().get(service)
    return c[0] if c else None


def pid(service):
    c = containers().get(service)
    return c[1] if c else 0


def dx(service, *cmd, input=None, timeout=30, detach=False):
    """在某台機器（容器）裡執行指令；detach=True 時不等結果。"""
    c = cid(service)
    if not c:
        return (False, '') if not detach else None
    args = ['docker', 'exec'] + (['-i'] if input is not None else []) + [c, *cmd]
    if detach:
        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    r = run(args, timeout=timeout, input=input)
    return r.returncode == 0, r.stdout


def ns(p, *cmd, timeout=15):
    """只進入某個 PID 的 network namespace 執行（不碰那台機器的檔案系統）。"""
    return run(['nsenter', '-t', str(p), '-n', *cmd], timeout=timeout)


def api(method, path, body=None, timeout=10):
    req = urllib.request.Request(f'{WGP}{path}', method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(WGP_AUTH.encode()).decode())
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return json.loads(data) if data else None


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def conf_server_key(who):
    """client 設定檔裡的伺服器公鑰；沒有設定檔時回傳 None。"""
    try:
        for line in open(f'{CLIENT_CONF}/{who}.conf'):
            if line.startswith('PublicKey'):
                return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return None


def wg_stale(p, who):
    """client 需要（重新）建立 wg0：有設定檔，但沒有 wg0，或 wg0 用的伺服器金鑰跟設定檔不同。"""
    want = conf_server_key(who)
    if not want or not os.path.exists(f'{CLIENT_CONF}/{who}.addr'):
        return False
    return ns(p, 'wg', 'show', 'wg0', 'peers').stdout.split() != [want]
