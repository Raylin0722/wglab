"""網頁（http://localhost:8080）：終端機、模擬一天、驗收、重開、從頭來過、說明文件、學校網頁。"""
import asyncio
import fcntl
import html
import json
import os
import pty
import signal
import struct
import termios
import time

from aiohttp import WSMsgType, web

import check
import jobs
import machines
import scenario
import seed
from common import containers, log

WEB = '/opt/wglab/web'
DOCS = {'letter': 'LETTER.md', 'guide': 'GUIDE.md', 'report': 'REPORT-TEMPLATE.md'}
ALERTS = '/school/alerts.json'


def blocking(fn, *a):
    return asyncio.get_running_loop().run_in_executor(None, fn, *a)


# ---------------------------------------------------------------- 狀態
async def state(request):
    def collect():
        cs = containers()
        job = jobs.current()
        try:
            day = json.load(open(scenario.STATUS))
        except Exception:
            day = None
        return {'machines': {s: s in cs for s in machines.PLAYER},
                'job': job.summary(since=job.summary()['total']) if job else None,
                'day': day if day and day.get('mode') == 'day' else None}
    return web.json_response(await blocking(collect))


async def job_log(request):
    since = int(request.query.get('since', 0))
    job = jobs.current()
    return web.json_response(job.summary(since) if job else None)


def start(kind, title, fn):
    job = jobs.start(kind, title, fn)
    if not job:
        return web.json_response({'ok': False, 'error': '有其他工作正在進行，請等它結束'}, status=409)
    return web.json_response({'ok': True, 'id': job.id})


async def do_day(request):
    return start('day', '模擬一天', seed.day_job)


async def do_check(request):
    return start('check', '驗收', lambda job: check.full(job.log, detail=request.query.get('detail') == '1'))


async def do_restart(request):
    svc = request.match_info['svc']
    if svc not in machines.PLAYER:
        raise web.HTTPNotFound()

    def fn(job):
        t = machines.restart([svc], job.log)
        machines.wait_ready(job.log, since=t if svc == 'wg227' else 0, timeout=120)
        job.log('完成')
    return start('restart', f'重開 {machines.NAMES[svc]}', fn)


async def do_reset(request):
    return start('reset', '從頭來過', machines.reset)


# ---------------------------------------------------------------- 文件與學校網頁
async def doc(request):
    name = DOCS.get(request.match_info['name'])
    if not name:
        raise web.HTTPNotFound()
    return web.Response(text=open(f'/opt/wglab/docs/{name}', encoding='utf-8').read(), content_type='text/markdown')


async def school(request):
    try:
        a = json.load(open(ALERTS)) if os.path.exists(ALERTS) else []
    except Exception:
        a = []
    rows = ''.join(f'<tr><td>{html.escape(x["time"])}</td><td>{x["ip"]}</td><td>{x["type"]}</td>'
                   f'<td>{x["reason"]}</td><td>{html.escape(x["note"])}</td></tr>' for x in reversed(a))
    return web.json_response({'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'rows': rows})


# ---------------------------------------------------------------- 終端機
async def term(request):
    svc = request.match_info['svc']
    if svc not in machines.PLAYER:
        raise web.HTTPNotFound()
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)
    cs = await blocking(containers)
    if svc not in cs:
        await ws.send_str(json.dumps({'type': 'status', 'text': f'{machines.NAMES[svc]} 目前沒有在執行'}))
        await ws.close()
        return ws

    pid, fd = pty.fork()
    if pid == 0:
        os.environ['TERM'] = 'xterm-256color'
        os.execvp('docker', ['docker', 'exec', '-it', '-e', 'TERM=xterm-256color', cs[svc][0], 'bash'])
    loop = asyncio.get_running_loop()
    closed = asyncio.Event()

    def readable():
        try:
            data = os.read(fd, 65536)
        except OSError:
            data = b''
        if not data:
            loop.remove_reader(fd)
            closed.set()
            return
        asyncio.ensure_future(ws.send_bytes(data))

    loop.add_reader(fd, readable)

    async def pump():
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            m = json.loads(msg.data)
            if m.get('type') == 'in':
                os.write(fd, m['data'].encode())
            elif m.get('type') == 'resize':
                fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', int(m['rows']), int(m['cols']), 0, 0))
        closed.set()

    task = asyncio.ensure_future(pump())
    await closed.wait()
    task.cancel()
    try:
        loop.remove_reader(fd)
    except Exception:
        pass
    try:
        os.kill(pid, signal.SIGHUP)
        await blocking(os.waitpid, pid, 0)
    except Exception:
        pass
    os.close(fd)
    if not ws.closed:
        await ws.close()
    return ws


# ---------------------------------------------------------------- 網站
async def index(request):
    return web.FileResponse(f'{WEB}/index.html')


def serve():
    app = web.Application()
    app.add_routes([
        web.get('/', index),
        web.get('/api/state', state),
        web.get('/api/job', job_log),
        web.post('/api/day', do_day),
        web.post('/api/check', do_check),
        web.post('/api/restart/{svc}', do_restart),
        web.post('/api/reset', do_reset),
        web.get('/api/doc/{name}', doc),
        web.get('/api/school', school),
        web.get('/ws/term/{svc}', term),
        web.static('/static', WEB),
    ])
    log('網頁：http://localhost:8080')
    web.run_app(app, port=8080, print=None, handle_signals=False)
