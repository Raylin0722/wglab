#!/usr/bin/env python3
"""在某台機器（namespace）裡做一個動作；由 scenario.py 以 `ip netns exec <ns>` 呼叫。

  print  <名稱> <自己的IP> <工作名>   向印表機訂閱 WSD 事件後列印（印表機會回撥 <自己的IP>:5357）
  scan   <自己的IP> <網段前三碼> <間隔秒>   像 Windows 的網路探索：對整段發 NetBIOS 名稱查詢（UDP 137）
  bcast  <廣播位址>                  NetBIOS 廣播查詢（區網內的正常行為）
  browse <網址>                      開網頁
"""
import json
import random
import socket
import struct
import sys
import time
import urllib.request

PRINTER = 'http://10.31.3.254:5357'


def post(url, data, timeout=4):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), method='POST',
                                 headers={'Content-Type': 'application/json'})
    return urllib.request.urlopen(req, timeout=timeout).read()


def nbstat_query():
    # NetBIOS Name Service：NBSTAT 查詢名稱「*」
    name = b'CK' + b'AA' * 15
    return struct.pack('!HHHHHH', random.randint(0, 65535), 0, 1, 0, 0, 0) + b'\x20' + name + b'\x00' + struct.pack('!HH', 0x21, 1)


def nbns_socket(src=''):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.bind((src, 137))
    except OSError:
        s.bind((src, 0))
    return s


def main():
    cmd, *a = sys.argv[1:]
    if cmd == 'print':
        name, myip, job = a
        post(f'{PRINTER}/subscribe', {'client': name, 'callback': f'http://{myip}:5357/wsd/events'})
        post(f'{PRINTER}/print', {'client': name, 'job': job})
    elif cmd == 'scan':
        myip, prefix, gap = a[0], a[1], float(a[2])
        s = nbns_socket(myip)
        targets = [f'{prefix}.{i}' for i in range(1, 255) if f'{prefix}.{i}' != myip]
        for ip in targets:
            try:
                s.sendto(nbstat_query(), (ip, 137))
            except OSError:
                pass
            time.sleep(gap)
    elif cmd == 'bcast':
        nbns_socket().sendto(nbstat_query(), (a[0], 137))
    elif cmd == 'browse':
        urllib.request.urlopen(a[0], timeout=4).read()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'nsact: {e}', file=sys.stderr)
        sys.exit(1)
