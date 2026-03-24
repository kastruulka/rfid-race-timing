import time
from flask import render_template_string, jsonify, request
from .database import Database
from .race_engine import RaceEngine


JUDGE_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель судьи</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Montserrat:wght@400;600;700;900&display=swap');

    :root {
      --bg: #0a0e17;
      --surface: #111827;
      --surface2: #1a2234;
      --border: #2a3548;
      --text: #e2e8f0;
      --text-dim: #64748b;
      --accent: #38bdf8;
      --accent-glow: rgba(56, 189, 248, 0.15);
      --green: #22c55e;
      --green-glow: rgba(34, 197, 94, 0.15);
      --red: #ef4444;
      --red-glow: rgba(239, 68, 68, 0.15);
      --yellow: #eab308;
      --yellow-glow: rgba(234, 179, 8, 0.15);
      --orange: #f97316;
      --orange-glow: rgba(249, 115, 22, 0.15);
      --mono: 'JetBrains Mono', monospace;
      --sans: 'Montserrat', system-ui, sans-serif;
      --radius: 10px;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--sans); background: var(--bg); color: var(--text); min-height: 100vh; }

    .topnav {
      display: flex; align-items: center; gap: 24px;
      padding: 0 24px; height: 52px;
      background: var(--surface); border-bottom: 1px solid var(--border);
    }
    .topnav-brand { font-weight: 900; font-size: 16px; text-transform: uppercase; letter-spacing: -0.02em; }
    .topnav-brand span { color: var(--accent); }
    .topnav a {
      color: var(--text-dim); text-decoration: none; font-size: 13px;
      font-weight: 700; padding: 14px 0; border-bottom: 2px solid transparent;
      transition: color .15s, border-color .15s;
    }
    .topnav a:hover { color: var(--text); }
    .topnav a.active { color: var(--accent); border-bottom-color: var(--accent); }

    .page { display: grid; grid-template-columns: 1fr 1fr; gap: 0; height: calc(100vh - 52px); }

    .actions-panel {
      border-right: 1px solid var(--border); display: flex;
      flex-direction: column; overflow-y: auto; padding: 20px;
    }
    .panel-title {
      font-size: 14px; font-weight: 900; text-transform: uppercase;
      letter-spacing: -0.01em; margin-bottom: 18px;
    }
    .panel-title span { color: var(--accent); }

    .rider-selector { position: relative; margin-bottom: 20px; }
    .rider-selector input {
      width: 100%; padding: 10px 14px; font-family: var(--sans); font-size: 14px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 8px;
      color: var(--text); outline: none; font-weight: 600;
    }
    .rider-selector input:focus { border-color: var(--accent); }
    .rider-dropdown {
      display: none; position: absolute; top: 100%; left: 0; right: 0;
      z-index: 50; max-height: 240px; overflow-y: auto;
      background: var(--surface); border: 1px solid var(--accent);
      border-top: none; border-radius: 0 0 8px 8px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    .rider-dropdown.open { display: block; }
    .rider-dropdown-item {
      padding: 8px 14px; cursor: pointer; font-size: 13px;
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 1px solid rgba(42,53,72,0.3);
    }
    .rider-dropdown-item:hover { background: var(--accent-glow); }
    .rider-dropdown-item .rdi-num {
      font-family: var(--mono); font-weight: 700; color: var(--accent);
      min-width: 40px;
    }
    .rider-dropdown-item .rdi-name { font-weight: 600; flex: 1; }
    .rider-dropdown-item .rdi-status {
      font-size: 10px; font-weight: 700; padding: 2px 6px;
      border-radius: 3px; margin-left: 8px;
    }

    .selected-rider {
      display: none; padding: 14px 18px; margin-bottom: 18px;
      background: var(--accent-glow); border: 1px solid rgba(56,189,248,0.3);
      border-radius: var(--radius);
    }
    .selected-rider.visible { display: block; }
    .selected-rider .sr-number {
      font-family: var(--mono); font-size: 28px; font-weight: 700;
      color: var(--accent); display: inline;
    }
    .selected-rider .sr-name { font-size: 16px; font-weight: 700; display: inline; margin-left: 10px; }
    .selected-rider .sr-meta { font-size: 12px; color: var(--text-dim); margin-top: 4px; }

    .form-row { margin-bottom: 12px; }
    .form-row label {
      display: block; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-dim); margin-bottom: 4px;
    }

    .action-section {
      margin-bottom: 20px; padding: 18px;
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .action-title {
      font-size: 12px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; margin-bottom: 12px; padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    .action-title.red { color: var(--red); }
    .action-title.yellow { color: var(--yellow); }
    .action-title.orange { color: var(--orange); }

    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      padding: 9px 16px; font-family: var(--sans); font-size: 12px; font-weight: 700;
      border: 1px solid var(--border); border-radius: 6px;
      background: var(--surface2); color: var(--text); cursor: pointer;
      transition: all .15s;
    }
    .btn:hover { border-color: var(--accent); }
    .btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .btn-red { background: var(--red); color: #fff; border-color: var(--red); }
    .btn-red:hover { background: #dc2626; }
    .btn-yellow { background: var(--yellow); color: var(--bg); border-color: var(--yellow); }
    .btn-yellow:hover { background: #ca9f07; }
    .btn-orange { background: var(--orange); color: #fff; border-color: var(--orange); }
    .btn-orange:hover { background: #ea6c0e; }
    .btn-accent { background: var(--accent); color: var(--bg); border-color: var(--accent); }
    .btn-accent:hover { background: #2daae8; }

    .btn-row { display: flex; gap: 8px; flex-wrap: wrap; }

    .dnf-reasons { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
    .dnf-reasons .btn { flex: 1; min-width: 120px; text-align: center; }

    .penalty-input {
      display: flex; gap: 8px; align-items: flex-end; margin-bottom: 10px;
    }
    .penalty-input input, .penalty-input select {
      padding: 8px 12px; font-family: var(--sans); font-size: 13px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); outline: none;
    }
    .penalty-input input:focus { border-color: var(--accent); }
    .penalty-input input[type="number"] { width: 90px; }
    .penalty-input input[type="text"] { flex: 1; }

    .log-panel { display: flex; flex-direction: column; overflow: hidden; }
    .log-header {
      padding: 14px 20px; font-size: 12px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--text-dim); background: var(--surface);
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .log-scroll { flex: 1; overflow-y: auto; }

    .log-item {
      display: flex; align-items: flex-start; gap: 12px;
      padding: 10px 20px; border-bottom: 1px solid rgba(42,53,72,0.5);
    }
    .log-item .li-badge {
      flex-shrink: 0; padding: 3px 8px; border-radius: 4px;
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      min-width: 70px; text-align: center;
    }
    .li-badge.TIME_PENALTY { background: var(--orange-glow); color: var(--orange); }
    .li-badge.EXTRA_LAP { background: var(--orange-glow); color: var(--orange); }
    .li-badge.WARNING { background: var(--yellow-glow); color: var(--yellow); }
    .li-badge.DSQ { background: var(--red-glow); color: var(--red); }
    .li-badge.DNF { background: var(--red-glow); color: var(--red); }
    .log-item .li-info { flex: 1; }
    .log-item .li-rider { font-weight: 700; font-size: 13px; }
    .log-item .li-detail { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
    .log-item .li-time { font-family: var(--mono); font-size: 11px; color: var(--text-dim); white-space: nowrap; }
    .log-item .li-delete {
      font-size: 11px; color: var(--text-dim); cursor: pointer;
      padding: 2px 6px; border-radius: 4px;
    }
    .log-item .li-delete:hover { color: var(--red); background: var(--red-glow); }

    .toast {
      position: fixed; bottom: 24px; right: 24px; z-index: 200;
      padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 600;
      background: var(--green); color: #fff; opacity: 0;
      transform: translateY(12px); transition: opacity .25s, transform .25s;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { background: var(--red); }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    @media (max-width: 900px) {
      .page { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
    }
  </style>
</head>
<body>

  <nav class="topnav">
    <div class="topnav-brand"><span>RFID</span> Хронометраж</div>
    <a href="/start-list">Стартовый лист</a>
    <a href="/">Хронометраж</a>
    <a href="/protocol">Протокол</a>
    <a href="/settings">Настройки</a>
    <a href="/judge" class="active">Судья</a>
  </nav>

  <div class="page">
    <div class="actions-panel">
      <div class="panel-title"><span>Панель</span> судьи</div>

      <div class="action-section" id="race-control">
        <div class="action-title" style="color:var(--green)">Управление гонкой</div>
        <div class="form-row">
          <label>Категория</label>
          <select id="race-category">
            <option value="">— Выберите категорию —</option>
          </select>
        </div>
        <div class="race-status-bar" id="race-status-bar" style="display:none;margin-bottom:12px">
          <div style="display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text-dim)">
            <span>В гонке: <b id="rs-racing" style="color:var(--accent);font-family:var(--mono)">0</b></span>
            <span>Финиш: <b id="rs-finished" style="color:var(--green);font-family:var(--mono)">0</b></span>
            <span>DNF: <b id="rs-dnf" style="color:var(--red);font-family:var(--mono)">0</b></span>
          </div>
        </div>
        <div class="btn-row">
          <button class="btn btn-accent" onclick="doMassStart()" id="btn-mass-start" style="flex:1;padding:12px;font-size:14px">
            ▶ Масс-старт
          </button>
          <button class="btn" onclick="doFinishRace()" id="btn-finish-race" style="flex:1;padding:12px;font-size:14px" disabled>
            ■ Завершить гонку
          </button>
        </div>
        <div class="btn-row" style="margin-top:8px">
          <button class="btn" onclick="doNewRace()" id="btn-new-race" style="flex:1">
            Новая гоночная сессия
          </button>
        </div>
      </div>

      <div class="rider-selector">
        <label style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-dim);margin-bottom:4px;display:block">Участник</label>
        <input type="text" id="rider-search" placeholder="Введите номер или фамилию…"
               oninput="onSearchInput()" onfocus="onSearchFocus()" autocomplete="off">
        <div class="rider-dropdown" id="rider-dropdown"></div>
      </div>

      <div class="selected-rider" id="selected-info">
        <div><span class="sr-number" id="sr-num"></span><span class="sr-name" id="sr-name"></span></div>
        <div class="sr-meta" id="sr-meta"></div>
        <div class="sr-status" id="sr-status" style="margin-top:6px"></div>
      </div>

      <div class="action-section">
        <div class="action-title" style="color:var(--green)">Коррекция финиша</div>
        <div id="current-finish-info" style="display:none;margin-bottom:10px;padding:8px 12px;background:var(--surface2);border-radius:6px">
          <span style="font-size:11px;color:var(--text-dim)">Текущее время финиша:</span>
          <span id="current-finish-time" style="font-family:var(--mono);font-size:18px;font-weight:700;color:var(--green);margin-left:8px"></span>
        </div>
        <div id="no-finish-info" style="display:none;margin-bottom:10px;padding:8px 12px;font-size:12px;color:var(--text-dim)">
          Участник ещё не финишировал
        </div>
        <div class="penalty-input" style="margin-bottom:8px">
          <input type="text" id="edit-finish-mm" placeholder="ММ" style="width:60px;text-align:center;font-family:var(--mono)">
          <span style="color:var(--text-dim);font-weight:700;font-size:18px">:</span>
          <input type="text" id="edit-finish-ss" placeholder="СС.д" style="width:80px;text-align:center;font-family:var(--mono)">
          <button class="btn btn-accent" onclick="doEditFinishTime()">Изменить</button>
        </div>
        <button class="btn" onclick="doUnfinishRider()" style="width:100%;padding:8px">
          Отменить финиш → вернуть в RACING
        </button>
      </div>

      <div class="action-section">
        <div class="action-title red">Сход с дистанции (DNF)</div>
        <div class="dnf-reasons">
          <button class="btn btn-red" onclick="doDNF('voluntary')" id="btn-dnf-vol">Добровольный сход</button>
          <button class="btn btn-red" onclick="doDNF('mechanical')" id="btn-dnf-mech">Мех. поломка</button>
          <button class="btn btn-red" onclick="doDNF('injury')" id="btn-dnf-inj">Травма</button>
        </div>
      </div>

      <div class="action-section">
        <div class="action-title red">Дисквалификация (DSQ)</div>
        <div class="penalty-input">
          <input type="text" id="dsq-reason" placeholder="Причина дисквалификации">
          <button class="btn btn-red" onclick="doDSQ()">DSQ</button>
        </div>
      </div>

      <div class="action-section">
        <div class="action-title orange">Временной штраф</div>
        <div class="penalty-input">
          <input type="number" id="pen-seconds" placeholder="Сек" min="1" value="30">
          <input type="text" id="pen-reason" placeholder="Причина штрафа">
          <button class="btn btn-orange" onclick="doTimePenalty()">+ Штраф</button>
        </div>
      </div>

      <div class="action-section">
        <div class="action-title orange">Штрафной круг</div>
        <div class="penalty-input">
          <input type="number" id="extra-laps" placeholder="Кол-во" min="1" value="1" style="width:70px">
          <input type="text" id="extra-reason" placeholder="Причина">
          <button class="btn btn-orange" onclick="doExtraLap()">+ Штрафной круг</button>
        </div>
      </div>

      <div class="action-section">
        <div class="action-title yellow">Предупреждение</div>
        <div class="penalty-input">
          <input type="text" id="warn-reason" placeholder="Причина предупреждения">
          <button class="btn btn-yellow" onclick="doWarning()">Предупреждение</button>
        </div>
      </div>

      <div class="action-section">
        <div class="action-title" style="color:var(--accent)">Заметки судьи</div>
        <div class="penalty-input">
          <input type="text" id="note-text" placeholder="Текст заметки…" style="flex:1">
          <button class="btn btn-accent" onclick="addNote()">+ Заметка</button>
        </div>
        <div id="notes-list" style="margin-top:8px"></div>
      </div>
    </div>

    <div class="log-panel">
      <div class="log-header">Журнал решений судьи</div>
      <div class="log-scroll" id="log-list"></div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
let riders = [];
let selectedRiderId = null;

function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

async function api(url, method, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  try { return await r.json(); } catch(e) { return { error: 'Ошибка сервера', _status: r.status }; }
}

async function loadRiders() {
  const data = await api('/api/riders', 'GET');
  riders = Array.isArray(data) ? data : [];
}

function onSearchInput() {
  renderDropdown();
  document.getElementById('rider-dropdown').classList.add('open');
}

function onSearchFocus() {
  renderDropdown();
  document.getElementById('rider-dropdown').classList.add('open');
}

function renderDropdown() {
  const query = (document.getElementById('rider-search').value || '').toLowerCase();
  const dd = document.getElementById('rider-dropdown');
  const filtered = riders.filter(r => {
    if (!query) return true;
    return String(r.number).includes(query) ||
           (r.last_name || '').toLowerCase().includes(query) ||
           (r.first_name || '').toLowerCase().includes(query);
  });

  if (!filtered.length) {
    dd.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim);font-size:12px">Не найдено</div>';
    return;
  }

  dd.innerHTML = filtered.map(r =>
    '<div class="rider-dropdown-item" onclick="selectRider(' + r.id + ')">' +
      '<span class="rdi-num">#' + r.number + '</span>' +
      '<span class="rdi-name">' + (r.last_name || '') + ' ' + (r.first_name || '') + '</span>' +
    '</div>'
  ).join('');
}

function selectRider(riderId) {
  selectedRiderId = riderId;
  const r = riders.find(x => x.id === riderId);
  const dd = document.getElementById('rider-dropdown');
  dd.classList.remove('open');

  if (!r) return;

  document.getElementById('rider-search').value = '#' + r.number + ' ' + r.last_name + ' ' + (r.first_name || '');
  document.getElementById('sr-num').textContent = '#' + r.number;
  document.getElementById('sr-name').textContent = r.last_name + ' ' + (r.first_name || '');
  document.getElementById('sr-meta').textContent =
    (r.category_name || '—') + ' · ' + (r.club || '—') + ' · ' + (r.city || '');
  document.getElementById('selected-info').classList.add('visible');

  loadRiderFinishInfo(riderId);
}

async function loadRiderFinishInfo(riderId) {
  try {
    const data = await api('/api/judge/rider-status/' + riderId, 'GET');
    const cfi = document.getElementById('current-finish-info');
    const nfi = document.getElementById('no-finish-info');
    const srs = document.getElementById('sr-status');

    if (data.status === 'FINISHED' && data.total_time_ms != null) {
      const ms = data.total_time_ms;
      const m = Math.floor(Math.abs(ms) / 1000 / 60);
      const s = (Math.abs(ms) / 1000) % 60;
      const timeStr = String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
      document.getElementById('current-finish-time').textContent = timeStr;
      // Предзаполняем поля редактирования
      document.getElementById('edit-finish-mm').value = String(m);
      document.getElementById('edit-finish-ss').value = s.toFixed(1);
      cfi.style.display = 'block';
      nfi.style.display = 'none';
      srs.innerHTML = '<span style="color:var(--green);font-weight:700;font-size:12px">FINISHED</span>';
    } else {
      cfi.style.display = 'none';
      nfi.style.display = data.status === 'RACING' ? 'block' : 'none';
      document.getElementById('edit-finish-mm').value = '';
      document.getElementById('edit-finish-ss').value = '';
      srs.innerHTML = '<span style="font-weight:700;font-size:12px;color:' +
        (data.status === 'RACING' ? 'var(--accent)' :
         data.status === 'DNF' ? 'var(--red)' :
         data.status === 'DSQ' ? 'var(--red)' : 'var(--text-dim)') +
        '">' + (data.status || '—') + '</span>' +
        (data.dnf_reason ? '<span style="font-size:10px;color:var(--text-dim);margin-left:6px">' + data.dnf_reason + '</span>' : '');
    }
  } catch(e) {
    document.getElementById('current-finish-info').style.display = 'none';
    document.getElementById('no-finish-info').style.display = 'none';
  }
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('.rider-selector')) {
    document.getElementById('rider-dropdown').classList.remove('open');
  }
});

function requireRider() {
  if (!selectedRiderId) { toast('Выберите участника', true); return false; }
  return true;
}

async function doDNF(reason) {
  if (!requireRider()) return;
  const res = await api('/api/judge/dnf', 'POST', {
    rider_id: selectedRiderId, reason_code: reason
  });
  if (res.ok) { toast('DNF зафиксирован'); loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function doDSQ() {
  if (!requireRider()) return;
  const reason = document.getElementById('dsq-reason').value.trim();
  const res = await api('/api/judge/dsq', 'POST', {
    rider_id: selectedRiderId, reason: reason
  });
  if (res.ok) { toast('DSQ — дисквалификация'); document.getElementById('dsq-reason').value = ''; loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function doTimePenalty() {
  if (!requireRider()) return;
  const seconds = parseFloat(document.getElementById('pen-seconds').value) || 0;
  const reason = document.getElementById('pen-reason').value.trim();
  if (seconds <= 0) { toast('Укажите время штрафа', true); return; }
  const res = await api('/api/judge/time-penalty', 'POST', {
    rider_id: selectedRiderId, seconds: seconds, reason: reason
  });
  if (res.ok) { toast('+' + seconds + ' сек штрафа'); document.getElementById('pen-reason').value = ''; loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function doExtraLap() {
  if (!requireRider()) return;
  const laps = parseInt(document.getElementById('extra-laps').value) || 1;
  const reason = document.getElementById('extra-reason').value.trim();
  const res = await api('/api/judge/extra-lap', 'POST', {
    rider_id: selectedRiderId, laps: laps, reason: reason
  });
  if (res.ok) { toast('+' + laps + ' штрафной круг'); document.getElementById('extra-reason').value = ''; loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function doWarning() {
  if (!requireRider()) return;
  const reason = document.getElementById('warn-reason').value.trim();
  const res = await api('/api/judge/warning', 'POST', {
    rider_id: selectedRiderId, reason: reason
  });
  if (res.ok) { toast('Предупреждение выдано'); document.getElementById('warn-reason').value = ''; loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function deletePenalty(pid) {
  if (!confirm('Удалить это решение?')) return;
  const res = await api('/api/judge/penalty/' + pid, 'DELETE');
  if (res.ok) { toast('Решение отменено'); loadLog(); }
  else toast(res.error || 'Ошибка', true);
}

async function loadLog() {
  try {
    const data = await api('/api/judge/log', 'GET');
    const log = Array.isArray(data) ? data : [];
    const list = document.getElementById('log-list');

    if (!log.length) {
      list.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-dim)">Нет записей</div>';
      return;
    }

    list.innerHTML = log.map(item => {
    const timeStr = new Date(item.created_at * 1000).toLocaleTimeString('ru-RU');
    const valueStr = item.type === 'TIME_PENALTY' ? '+' + item.value + ' сек'
      : item.type === 'EXTRA_LAP' ? '+' + item.value + ' кр.'
      : item.type === 'WARNING' ? 'предупр.'
      : item.type;

    const typeLabels = {
      TIME_PENALTY: 'Штраф',
      EXTRA_LAP: 'Доп. круг',
      WARNING: 'Предупр.',
      DSQ: 'DSQ',
      DNF: 'DNF',
    };

    return '<div class="log-item">' +
      '<div class="li-badge ' + item.type + '">' + (typeLabels[item.type] || item.type) + '</div>' +
      '<div class="li-info">' +
        '<div class="li-rider">#' + item.rider_number + ' ' + item.last_name + '</div>' +
        '<div class="li-detail">' + (item.reason || valueStr) + '</div>' +
      '</div>' +
      '<div class="li-time">' + timeStr + '</div>' +
      '<div class="li-delete" onclick="deletePenalty(' + item.id + ')" title="Отменить">✕</div>' +
    '</div>';
  }).join('');
  } catch(e) { console.error('loadLog error', e); }
}

loadRiders();
loadLog();
loadNotes();
loadCategoriesAndRestore();
setInterval(loadLog, 5000);
setInterval(loadRaceStatus, 2000);

async function loadCategoriesAndRestore() {
  const cats = await api('/api/categories', 'GET');
  const sel = document.getElementById('race-category');
  sel.innerHTML = '<option value="">— Выберите категорию —</option>';
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
  });

  const saved = sessionStorage.getItem('judge_cat_id');
  if (saved && sel.querySelector('option[value="' + saved + '"]')) {
    sel.value = saved;
  } else if (cats.length === 1) {
    // Если одна категория — выбираем автоматически
    sel.value = cats[0].id;
  }
  loadRaceStatus();
}

async function loadRaceStatus() {
  const catId = document.getElementById('race-category').value;

  if (catId) {
    sessionStorage.setItem('judge_cat_id', catId);
  }

  if (!catId) {
    document.getElementById('race-status-bar').style.display = 'none';
    document.getElementById('btn-mass-start').disabled = false;
    document.getElementById('btn-finish-race').disabled = true;
    return;
  }
  try {
    const resp = await fetch('/api/state?category_id=' + catId);
    const data = await resp.json();
    const st = data.status || {};
    const racing = st.RACING || 0;
    const finished = st.FINISHED || 0;
    const dnf = (st.DNF || 0) + (st.DSQ || 0);
    const total = racing + finished + dnf;

    document.getElementById('rs-racing').textContent = racing;
    document.getElementById('rs-finished').textContent = finished;
    document.getElementById('rs-dnf').textContent = dnf;
    document.getElementById('race-status-bar').style.display = 'block';

    const raceClosed = data.race_closed === true;

    document.getElementById('btn-mass-start').disabled = total > 0;

    document.getElementById('btn-finish-race').disabled = total === 0 || raceClosed;

    const startBtn = document.getElementById('btn-mass-start');
    if (raceClosed) {
      startBtn.textContent = 'Гонка завершена';
    } else if (total > 0) {
      startBtn.textContent = racing > 0 ? 'Гонка идёт' : 'Гонка активна';
    } else {
      startBtn.textContent = '▶ Масс-старт';
    }

    const finBtn = document.getElementById('btn-finish-race');
    finBtn.textContent = raceClosed ? 'Гонка завершена' : '■ Завершить гонку';

    document.querySelectorAll('.action-section .btn').forEach(b => {
      if (!b.closest('#race-control')) {
        b.disabled = raceClosed;
      }
    });
  } catch(e) {}
}

document.getElementById('race-category').addEventListener('change', loadRaceStatus);

async function doMassStart() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { toast('Выберите категорию', true); return; }
  if (!confirm('Запустить масс-старт для выбранной категории?')) return;
  const res = await api('/api/judge/mass-start', 'POST', { category_id: parseInt(catId) });
  if (res.ok) {
    toast('Масс-старт! Участников: ' + (res.info && res.info.riders_started || '?'));
    loadRaceStatus();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function doUnfinishRider() {
  if (!requireRider()) return;
  const r = riders.find(x => x.id === selectedRiderId);
  const label = r ? '#' + r.number + ' ' + r.last_name : '#' + selectedRiderId;
  if (!confirm('Отменить финиш ' + label + '?\nУчастник вернётся в статус RACING.')) return;
  const res = await api('/api/judge/unfinish-rider', 'POST', { rider_id: selectedRiderId });
  if (res.ok) {
    toast('Финиш отменён: ' + label);
    loadRaceStatus();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function doEditFinishTime() {
  if (!requireRider()) return;
  const mm = document.getElementById('edit-finish-mm').value.trim();
  const ss = document.getElementById('edit-finish-ss').value.trim();
  if (!mm && !ss) { toast('Введите время ММ:СС.д', true); return; }
  const minutes = parseInt(mm) || 0;
  const seconds = parseFloat(ss) || 0;
  if (minutes < 0 || seconds < 0 || seconds >= 60) {
    toast('Неверный формат времени', true); return;
  }
  const totalMs = Math.round((minutes * 60 + seconds) * 1000);

  const r = riders.find(x => x.id === selectedRiderId);
  const label = r ? '#' + r.number + ' ' + r.last_name : '#' + selectedRiderId;
  const timeStr = String(minutes).padStart(2,'0') + ':' + seconds.toFixed(1).padStart(4,'0');
  if (!confirm('Изменить время финиша ' + label + ' на ' + timeStr + '?')) return;

  const res = await api('/api/judge/edit-finish-time', 'POST', {
    rider_id: selectedRiderId, finish_time_ms: totalMs
  });
  if (res.ok) {
    toast('Время финиша изменено: ' + label + ' → ' + timeStr);
    document.getElementById('edit-finish-mm').value = '';
    document.getElementById('edit-finish-ss').value = '';
    loadRaceStatus();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function addNote() {
  const text = document.getElementById('note-text').value.trim();
  if (!text) { toast('Введите текст заметки', true); return; }
  const res = await api('/api/judge/notes', 'POST', {
    text: text, rider_id: selectedRiderId || null
  });
  if (res.ok) {
    toast('Заметка сохранена');
    document.getElementById('note-text').value = '';
    loadNotes();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function deleteNote(nid) {
  const res = await api('/api/judge/notes/' + nid, 'DELETE');
  if (res.ok) loadNotes();
}

async function loadNotes() {
  try {
    const data = await api('/api/judge/notes', 'GET');
    const notes = Array.isArray(data) ? data : [];
    const list = document.getElementById('notes-list');
    if (!notes.length) { list.innerHTML = ''; return; }
    list.innerHTML = notes.map(n => {
      const timeStr = new Date(n.created_at * 1000).toLocaleTimeString('ru-RU');
      const rider = n.rider_number ? '#' + n.rider_number + ' ' + (n.last_name || '') + ' — ' : '';
      return '<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 0;border-bottom:1px solid var(--border);font-size:12px">' +
        '<div style="flex:1"><span style="color:var(--accent);font-weight:600">' + rider + '</span>' +
        '<span style="color:var(--text)">' + n.text + '</span></div>' +
        '<span style="color:var(--text-dim);font-family:var(--mono);font-size:10px;white-space:nowrap">' + timeStr + '</span>' +
        '<span style="cursor:pointer;color:var(--text-dim);font-size:10px" onclick="deleteNote(' + n.id + ')" title="Удалить">✕</span>' +
      '</div>';
    }).join('');
  } catch(e) {}
}

async function doFinishRace() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { toast('Выберите категорию', true); return; }
  if (!confirm('Завершить гонку?\n• Участники, проехавшие все круги → FINISHED\n• Остальные → DNF\n• Таймер остановится\n• Изменения более невозможны')) return;
  const res = await api('/api/judge/finish-race', 'POST', { category_id: parseInt(catId) });
  if (res.ok) {
    toast('Гонка завершена. Финиш: ' + (res.finished || 0) + ', DNF: ' + (res.dnf_count || 0));
    loadRaceStatus();
    loadLog();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function doNewRace() {
  if (!confirm('Создать новую гоночную сессию?\nТекущие результаты останутся в архиве.')) return;
  const res = await api('/api/settings/reset-race', 'POST');
  if (res.ok) {
    toast('Новая сессия #' + res.race_id);
    loadRaceStatus();
    loadLog();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}
</script>
</body>
</html>
"""


def register_judge(app, db: Database, engine: RaceEngine = None):

    @app.route("/judge")
    def judge_page():
        return render_template_string(JUDGE_HTML)

    @app.route("/api/judge/rider-status/<int:rid>", methods=["GET"])
    def api_judge_rider_status(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify({"status": "DNS", "total_time_ms": None,
                            "dnf_reason": ""})
        total_time_ms = None
        if result.get("finish_time") and result.get("start_time"):
            total_time_ms = int(result["finish_time"]) - int(result["start_time"])
        return jsonify({
            "status": result["status"],
            "total_time_ms": total_time_ms,
            "finish_time": result.get("finish_time"),
            "start_time": result.get("start_time"),
            "dnf_reason": result.get("dnf_reason", ""),
            "penalty_time_ms": result.get("penalty_time_ms") or 0,
            "extra_laps": result.get("extra_laps") or 0,
        })

    @app.route("/api/judge/dnf", methods=["POST"])
    def api_judge_dnf():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dnf(int(rid),
                            reason_code=data.get("reason_code", ""),
                            reason_text=data.get("reason_text", ""))
        if not ok:
            return jsonify({"error":
                "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/dsq", methods=["POST"])
    def api_judge_dsq():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dsq(int(rid), reason=data.get("reason", ""))
        if not ok:
            return jsonify({"error": "Невозможно"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/time-penalty", methods=["POST"])
    def api_judge_time_penalty():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        seconds = data.get("seconds", 0)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_time_penalty(
            int(rid), float(seconds), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/extra-lap", methods=["POST"])
    def api_judge_extra_lap():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        laps = data.get("laps", 1)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_extra_lap(
            int(rid), int(laps), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/warning", methods=["POST"])
    def api_judge_warning():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_warning(
            int(rid), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/penalty/<int:pid>", methods=["DELETE"])
    def api_judge_delete_penalty(pid):
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        ok = engine.remove_penalty(pid)
        if not ok:
            return jsonify({"error": "Штраф не найден"}), 404
        return jsonify({"ok": True})

    @app.route("/api/judge/log", methods=["GET"])
    def api_judge_log():
        try:
            penalties = db.get_penalties_by_race()
            return jsonify(penalties)
        except Exception as e:
            return jsonify([])

    @app.route("/api/judge/mass-start", methods=["POST"])
    def api_judge_mass_start():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        try:
            info = engine.mass_start(int(cat_id))
            return jsonify({"ok": True, "info": info})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/judge/unfinish-rider", methods=["POST"])
    def api_judge_unfinish_rider():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.unfinish_rider(int(rid))
        if not ok:
            return jsonify({"error":
                "Невозможно — участник не FINISHED или гонка закрыта"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/finish-race", methods=["POST"])
    def api_judge_finish_race():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        result = engine.finish_all(int(cat_id))
        return jsonify({"ok": True, **result})

    @app.route("/api/judge/edit-finish-time", methods=["POST"])
    def api_judge_edit_finish_time():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        finish_time_ms = data.get("finish_time_ms")
        if not rid or finish_time_ms is None:
            return jsonify({"error": "Участник или время не указаны"}), 400

        result = db.get_result_by_rider(int(rid))
        if not result or result["status"] != "FINISHED":
            return jsonify({"error":
                "Участник не FINISHED"}), 400
        start = result.get("start_time") or 0
        absolute_finish = int(start) + int(finish_time_ms)

        ok = engine.edit_finish_time(int(rid), absolute_finish)
        if not ok:
            return jsonify({"error":
                "Невозможно — гонка закрыта или участник не FINISHED"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/notes", methods=["GET"])
    def api_judge_notes_list():
        try:
            notes = db.get_notes()
            return jsonify(notes)
        except Exception:
            return jsonify([])

    @app.route("/api/judge/notes", methods=["POST"])
    def api_judge_notes_create():
        data = request.get_json(force=True)
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "Текст заметки пуст"}), 400
        rid = data.get("rider_id")
        nid = db.add_note(text=text, rider_id=int(rid) if rid else None)
        return jsonify({"ok": True, "id": nid})

    @app.route("/api/judge/notes/<int:nid>", methods=["DELETE"])
    def api_judge_notes_delete(nid):
        db.delete_note(nid)
        return jsonify({"ok": True})