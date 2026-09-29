"""背景工作：模擬一天、驗收、重開、從頭來過。同一時間只跑一個，網頁看得到進度。"""
import threading
import time
import traceback

_lock = threading.Lock()
_job = None          # 目前（或最後一個）工作
_seq = 0


class Job:
    def __init__(self, kind, title):
        global _seq
        _seq += 1
        self.id, self.kind, self.title = _seq, kind, title
        self.lines, self.state, self.result = [], 'running', None
        self.started, self.ended = time.time(), None

    def log(self, *parts):
        line = ' '.join(str(p) for p in parts)
        self.lines.append(f'{time.strftime("%H:%M:%S")}  {line}')
        print(f'[{self.kind}] {line}', flush=True)

    def summary(self, since=0):
        return {'id': self.id, 'kind': self.kind, 'title': self.title, 'state': self.state,
                'started': self.started, 'ended': self.ended, 'result': self.result,
                'lines': self.lines[since:], 'total': len(self.lines)}


def current():
    return _job


def busy():
    return _job is not None and _job.state == 'running'


def start(kind, title, fn):
    """fn(job) 在背景執行；回傳 Job，或 None（已經有工作在跑）。"""
    global _job
    with _lock:
        if busy():
            return None
        job = _job = Job(kind, title)

    def run():
        try:
            job.result = fn(job)
            job.state = 'done'
        except Exception as e:
            job.log(f'發生錯誤：{e}')
            print(traceback.format_exc(), flush=True)
            job.state = 'failed'
        job.ended = time.time()

    threading.Thread(target=run, daemon=True).start()
    return job
