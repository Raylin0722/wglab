#!/usr/bin/env python3
"""情境角色：每個模式跑在自己的容器裡（網路由 control 接好）。

  web       假網際網路上的網站 198.51.100.10:80
  labweb    實驗室內的服務（pc1:80）
  school    學校資安監控：抓出口送往私有位址的封包，並提供異常查詢網頁 203.0.113.1:80
  printer   印表機 WSD：接受訂閱，列印時回撥 client 的 :5357
  listen    WireGuard client 收印表機回撥（:5357）
"""
import ipaddress
import json
import os
import socket
import struct
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = '/data'                      # 共用的 volume（學校紀錄、列印回撥紀錄）
HIDDEN = STATE
PRIVATE = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]


def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')


def serve(port, handler, host=''):
    ThreadingHTTPServer((host, port), handler).serve_forever()


class Quiet(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, body, ctype='text/html; charset=utf-8', code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


# ---------------------------------------------------------------- web / labweb
def run_web(title):
    class H(Quiet):
        def do_GET(self):
            self.reply(f'<h1>{title}</h1><p>{now()}</p>')
    serve(80, H)


# ---------------------------------------------------------------- school
def run_school():
    """在 s-lab 上看所有從實驗室出口進來的封包；目的地是私有位址的就記下來（學校不會轉送它們）。"""
    os.makedirs(HIDDEN, exist_ok=True)
    raw = f'{HIDDEN}/raw.jsonl'           # 每一筆外漏封包
    alerts = f'{HIDDEN}/alerts.json'      # 異常查詢網頁顯示的內容
    lock = threading.Lock()
    if not os.path.exists(alerts):
        json.dump([], open(alerts, 'w'))

    def sniff():
        s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.ntohs(0x0800))   # 不綁網卡：線重接後仍收得到
        window = []                        # 最近 5 分鐘的 UDP 137（時間、目的地）
        last_alert = 0
        while True:
            pkt, addr = s.recvfrom(65535)
            if addr[0] != 's-lab' or addr[2] == socket.PACKET_OUTGOING:
                continue
            ip = pkt[14:]
            if len(ip) < 20 or ip[0] >> 4 != 4:
                continue
            ihl = (ip[0] & 15) * 4
            proto = ip[9]
            src, dst = socket.inet_ntoa(ip[12:16]), socket.inet_ntoa(ip[16:20])
            if not any(ipaddress.ip_address(dst) in n for n in PRIVATE):
                continue
            dport = struct.unpack('!H', ip[ihl + 2:ihl + 4])[0] if proto in (6, 17) and len(ip) >= ihl + 4 else 0
            t = time.time()
            rec = {'t': round(t, 3), 'time': now(), 'src': src, 'dst': dst,
                   'proto': {6: 'tcp', 17: 'udp', 1: 'icmp'}.get(proto, str(proto)), 'dport': dport}
            with lock, open(raw, 'a') as f:
                f.write(json.dumps(rec) + '\n')
            if proto == 17 and dport == 137:
                window = [(wt, wd) for wt, wd in window if t - wt < 300] + [(t, dst)]
                if len({d for _, d in window}) >= 50 and t - last_alert > 600:
                    last_alert = t
                    with lock:
                        a = json.load(open(alerts))
                        a.append({'time': now(), 'ip': src, 'type': 'Virus', 'reason': 'U137:flow', 'note': '疑似中毒'})
                        json.dump(a, open(alerts, 'w'), ensure_ascii=False)

    threading.Thread(target=sniff, daemon=True).start()

    class H(Quiet):
        def do_GET(self):
            a = json.load(open(alerts))
            rows = ''.join(f'<tr><td>{x["time"]}</td><td>{x["ip"]}</td><td>{x["type"]}</td><td>{x["reason"]}</td><td>{x["note"]}</td></tr>'
                           for x in reversed(a)) or '<tr><td colspan=5>目前沒有異常紀錄</td></tr>'
            self.reply(f'''<!doctype html><meta charset=utf-8><title>校園網路異常查詢</title>
<h1>校園網路異常查詢</h1><p>查詢時間：{now()}</p>
<table border=1 cellpadding=6><tr><th>偵測時間</th><th>IP</th><th>類型</th><th>原因</th><th>說明</th></tr>{rows}</table>''')
    serve(80, H)


# ---------------------------------------------------------------- printer (WSD)
def run_printer():
    """極簡的 WSD：POST /subscribe 登記回撥網址；POST /print 開始列印，之後依序回撥三次。"""
    subs = {}
    log = f'{STATE}/printer.log'

    def callback(url, job, peer):
        for ev in ('JobStarted', 'JobProgress', 'JobCompleted'):
            time.sleep(0.8)
            try:
                req = urllib.request.Request(url, data=json.dumps({'job': job, 'event': ev}).encode(), method='POST')
                urllib.request.urlopen(req, timeout=3).read()
                ok = 'ok'
            except Exception as e:
                ok = f'fail ({type(e).__name__})'
            with open(log, 'a') as f:
                f.write(f'{now()} job={job} from={peer} callback={url} event={ev} {ok}\n')

    class H(Quiet):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            peer = self.client_address[0]
            if self.path == '/subscribe':
                subs[body['client']] = body['callback']
                self.reply('{"ok":true}', 'application/json')
            elif self.path == '/print':
                url = subs.get(body.get('client'))
                if url:
                    threading.Thread(target=callback, args=(url, body.get('job', '?'), peer), daemon=True).start()
                self.reply('{"queued":true}', 'application/json')
            else:
                self.reply('not found', code=404)
    serve(5357, H)


# ---------------------------------------------------------------- client listener
def run_listen(name):
    log = f'{STATE}/{name}-callbacks.log'

    class H(Quiet):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            with open(log, 'a') as f:
                f.write(f'{time.time():.3f} {now()} {self.client_address[0]} {body.decode(errors="replace")}\n')
            self.reply('ok', 'text/plain')
    serve(5357, H)


if __name__ == '__main__':
    mode = sys.argv[1]
    def labweb():
        threading.Thread(target=run_listen, args=('pc1',), daemon=True).start()
        run_web('實驗室內部服務')

    {'web': lambda: run_web('Example Internet Site'),
     'labweb': labweb,
     'school': run_school,
     'printer': run_printer,
     'listen': lambda: run_listen(sys.argv[2])}[mode]()
