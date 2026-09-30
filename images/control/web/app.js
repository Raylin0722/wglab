// 實驗室網頁：終端機（斷線自動重連）、側欄文件、學校網頁、模擬一天、驗收、重開、從頭來過
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const NAMES = { wg227: '227', router: 'router', routerlog: 'routerlog' };

// ---------------------------------------------------------------- 終端機
const terms = {};

function makeTerm(svc) {
  const el = document.createElement('div');
  el.className = 'term';
  $('#tbody').appendChild(el);
  const term = new Terminal({
    fontFamily: '"JetBrains Mono", Consolas, monospace', fontSize: 15, cursorBlink: true, scrollback: 5000,
    theme: { background: '#000000', foreground: '#e6e9ef', cursor: '#4cc2ff', selectionBackground: '#2b4a66' },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open(el);
  const t = { svc, el, term, fit, ws: null, timer: null };
  term.onData(d => t.ws && t.ws.readyState === 1 && t.ws.send(JSON.stringify({ type: 'in', data: d })));
  term.onResize(({ cols, rows }) => t.ws && t.ws.readyState === 1 && t.ws.send(JSON.stringify({ type: 'resize', cols, rows })));
  connect(t);
  return t;
}

function connect(t) {
  clearTimeout(t.timer);
  const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/term/${t.svc}`);
  ws.binaryType = 'arraybuffer';
  t.ws = ws;
  ws.onopen = () => { safeFit(t); ws.send(JSON.stringify({ type: 'resize', cols: t.term.cols, rows: t.term.rows })); };
  ws.onmessage = e => {
    if (typeof e.data === 'string') {
      const m = JSON.parse(e.data);
      if (m.type === 'status') t.term.write(`\r\n\x1b[33m${m.text}\x1b[0m\r\n`);
    } else {
      t.term.write(new Uint8Array(e.data));
    }
  };
  ws.onclose = () => {
    if (t.ws !== ws) return;
    t.term.write(`\r\n\x1b[90m[和 ${NAMES[t.svc]} 的連線中斷，3 秒後自動重新連線…]\x1b[0m\r\n`);
    t.timer = setTimeout(() => connect(t), 3000);
  };
}

function safeFit(t) { try { t.fit.fit(); } catch (e) { /* 隱藏中的分頁量不到大小 */ } }

function showTerm(svc) {
  $$('.ttab').forEach(x => x.classList.toggle('active', x.dataset.svc === svc));
  if (!terms[svc]) terms[svc] = makeTerm(svc);
  Object.values(terms).forEach(t => t.el.classList.toggle('active', t.svc === svc));
  requestAnimationFrame(() => { safeFit(terms[svc]); terms[svc].term.focus(); });
}

$$('.ttab .tname').forEach(b => b.onclick = () => showTerm(b.closest('.ttab').dataset.svc));
$$('.ttab .rst').forEach(b => b.onclick = async () => {
  const svc = b.closest('.ttab').dataset.svc;
  if (!confirm(`重開 ${NAMES[svc]}？（等同這台機器重新開機，設定會保留）`)) return;
  await post(`/api/restart/${svc}`);
});
addEventListener('resize', () => Object.values(terms).forEach(t => t.el.classList.contains('active') && safeFit(t)));

// ---------------------------------------------------------------- 側欄
$$('.stabs button').forEach(b => b.onclick = () => {
  $$('.stabs button').forEach(x => x.classList.toggle('active', x === b));
  $$('.pane').forEach(p => p.classList.toggle('active', p.dataset.pane === b.dataset.pane));
  if (b.dataset.pane === 'school') loadSchool();
});

async function loadDocs() {
  for (const name of ['letter', 'guide', 'report']) {
    const r = await fetch(`/api/doc/${name}`);
    $(`#doc-${name}`).innerHTML = marked.parse(await r.text());
  }
}

async function loadSchool() {
  const s = await (await fetch('/api/school')).json();
  $('#schoolTime').textContent = `查詢時間：${s.time}`;
  $('#schoolRows').innerHTML = s.rows || '<tr><td colspan="5">目前沒有異常紀錄</td></tr>';
}

// ---------------------------------------------------------------- 工作（模擬一天、驗收、重開、從頭來過）
async function post(url) {
  const r = await fetch(url, { method: 'POST' });
  const j = await r.json();
  if (!j.ok) alert(j.error || '無法執行');
  poll();
  return j;
}

$('#btnDay').onclick = () => post('/api/day');
$('#btnCheck').onclick = () => {
  $$('.stabs button').find(b => b.dataset.pane === 'check').click();
  post('/api/check');
};
$('#btnReset').onclick = () => {
  if (confirm('從頭來過：227、router、routerlog 會重建，你做的所有設定都會清掉。確定嗎？')) post('/api/reset');
};

let shownJob = 0, shownLines = 0;

async function poll() {
  let s;
  try { s = await (await fetch('/api/state')).json(); } catch (e) { $('#jobStatus').textContent = '連不上實驗室'; return; }
  const init = s.init || {};
  $('#initView').classList.toggle('show', !!init.active);
  if (init.active) {
    const order = $$('#initSteps li').map(li => li.dataset.step), at = order.indexOf(init.step);
    $$('#initSteps li').forEach((li, i) => { li.classList.toggle('done', i < at); li.classList.toggle('now', i === at); });
  }
  for (const [svc, up] of Object.entries(s.machines)) $(`.ttab[data-svc="${svc}"] .dot`).classList.toggle('up', up);
  const job = s.job, busy = job && job.state === 'running';
  $$('#btnDay, #btnCheck, #btnReset, .ttab .rst').forEach(b => b.disabled = busy);
  const st = $('#jobStatus');
  st.classList.toggle('busy', !!busy);
  if (busy && job.kind === 'day' && s.day) st.textContent = `模擬一天：${s.day.elapsed} / ${s.day.duration} 秒`;
  else if (busy) st.textContent = `${job.title}進行中…（進度見「驗收」分頁）`;
  else if (job && job.kind === 'init') st.textContent = '待命中';
  else if (job) st.textContent = `上一個工作：${job.title}（${job.state === 'done' ? '完成' : '失敗'}）`;
  else st.textContent = '待命中';

  if (job && job.kind !== 'day' && job.kind !== 'init') {
    if (job.id !== shownJob) { shownJob = job.id; shownLines = 0; $('#jobLog').textContent = ''; $('#result').innerHTML = ''; }
    const j = await (await fetch(`/api/job?since=${shownLines}`)).json();
    if (j && j.lines.length) { $('#jobLog').textContent += j.lines.join('\n') + '\n'; shownLines = j.total; }
    if (j && j.kind === 'check' && j.state !== 'running' && j.result && j.result.items) {
      $('#result').innerHTML = j.result.items.map(i => `<li class="${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '✗'}　${i.name}</li>`).join('')
        + `<li class="total ${j.result.passed ? 'ok' : 'bad'}">${j.result.passed ? '全部通過' : '還有沒通過的項目'}</li>`;
    }
  }
}

loadDocs();
showTerm('wg227');
poll();
setInterval(poll, 2000);
