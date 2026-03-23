import csv
import io
import time
from flask import (
    render_template_string, jsonify, request, Response,
)
from .database import Database
from .race_engine import RaceEngine


START_LIST_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Стартовый лист</title>
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

    .page { display: grid; grid-template-columns: 340px 1fr; height: calc(100vh - 52px); }
    .sidebar {
      border-right: 1px solid var(--border); display: flex;
      flex-direction: column; overflow: hidden;
    }
    .main-area { display: flex; flex-direction: column; overflow: hidden; }

    .panel-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 18px; font-size: 12px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim);
      background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0;
    }

    .btn {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 7px 14px; font-family: var(--sans); font-size: 12px; font-weight: 700;
      border: 1px solid var(--border); border-radius: 6px;
      background: var(--surface2); color: var(--text); cursor: pointer;
      transition: background .15s, border-color .15s;
    }
    .btn:hover { background: var(--surface); border-color: var(--accent); }
    .btn-accent {
      background: var(--accent); color: var(--bg); border-color: var(--accent);
    }
    .btn-accent:hover { background: #2daae8; }
    .btn-danger { color: var(--red); }
    .btn-danger:hover { background: var(--red-glow); border-color: var(--red); }
    .btn-sm { padding: 4px 10px; font-size: 11px; }

    .cat-list { flex: 1; overflow-y: auto; }
    .cat-item {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 18px; cursor: pointer;
      border-bottom: 1px solid rgba(42,53,72,0.5);
      transition: background .12s;
    }
    .cat-item:hover { background: rgba(56,189,248,0.04); }
    .cat-item.active { background: var(--accent-glow); border-left: 3px solid var(--accent); }
    .cat-name { font-weight: 600; font-size: 14px; }
    .cat-meta { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
    .cat-count {
      font-family: var(--mono); font-size: 13px; font-weight: 700;
      color: var(--accent); min-width: 28px; text-align: center;
    }
    .cat-actions { display: flex; gap: 4px; }

    .toolbar {
      display: flex; align-items: center; gap: 10px; padding: 10px 18px;
      background: var(--surface); border-bottom: 1px solid var(--border); flex-shrink: 0;
      flex-wrap: wrap;
    }
    .search-box {
      flex: 1; min-width: 180px; padding: 7px 14px;
      font-family: var(--sans); font-size: 13px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); outline: none;
    }
    .search-box:focus { border-color: var(--accent); }
    .search-box::placeholder { color: var(--text-dim); }

    .table-scroll { flex: 1; overflow-y: auto; }
    .rtable { width: 100%; border-collapse: collapse; font-size: 13px; }
    .rtable thead { position: sticky; top: 0; z-index: 2; }
    .rtable th {
      padding: 10px 12px; text-align: left; font-size: 11px;
      font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-dim); background: var(--surface);
      border-bottom: 2px solid var(--border);
    }
    .rtable td {
      padding: 9px 12px; border-bottom: 1px solid rgba(42,53,72,0.4);
    }
    .rtable tr:hover { background: rgba(56,189,248,0.04); }
    .rtable .c { text-align: center; }
    .rtable .mono { font-family: var(--mono); }
    .rtable .num-col { font-family: var(--mono); font-weight: 700; color: var(--accent); text-align: center; }
    .rtable .epc-col {
      font-family: var(--mono); font-size: 11px; color: var(--text-dim);
      max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .rtable .epc-col.bound { color: var(--green); }
    .rtable .actions-col { display: flex; gap: 4px; justify-content: center; }
    th.c { text-align: center; }

    .empty-state {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 60px 20px; color: var(--text-dim);
    }
    .empty-state .icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }
    .empty-state .msg { font-size: 14px; font-weight: 600; }

    .modal-overlay {
      display: none; position: fixed; inset: 0; z-index: 100;
      background: rgba(0,0,0,0.65); align-items: center; justify-content: center;
    }
    .modal-overlay.open { display: flex; }
    .modal {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: 12px; padding: 28px; min-width: 400px; max-width: 520px; width: 90%;
      box-shadow: 0 24px 60px rgba(0,0,0,0.5);
    }
    .modal h2 {
      font-size: 16px; font-weight: 900; text-transform: uppercase;
      letter-spacing: -0.02em; margin-bottom: 20px;
    }
    .modal h2 span { color: var(--accent); }

    .form-row { margin-bottom: 14px; }
    .form-row label {
      display: block; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-dim); margin-bottom: 5px;
    }
    .form-row input, .form-row select {
      width: 100%; padding: 8px 12px; font-family: var(--sans); font-size: 13px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); outline: none;
    }
    .form-row input:focus, .form-row select:focus { border-color: var(--accent); }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
    .form-actions { display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px; }

    .toast {
      position: fixed; bottom: 24px; right: 24px; z-index: 200;
      padding: 12px 20px; border-radius: 8px; font-size: 13px; font-weight: 600;
      background: var(--green); color: #fff; opacity: 0;
      transform: translateY(12px); transition: opacity .25s, transform .25s;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { background: var(--red); }

    .stat-row {
      display: flex; gap: 16px; padding: 14px 18px;
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .stat-item { font-size: 12px; color: var(--text-dim); font-weight: 600; }
    .stat-item b { color: var(--text); font-family: var(--mono); }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    @media (max-width: 800px) {
      .page { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
      .sidebar { max-height: 240px; border-right: none; border-bottom: 1px solid var(--border); }
      .modal { min-width: auto; }
    }
  </style>
</head>
<body>

  <nav class="topnav">
    <div class="topnav-brand"><span>RFID</span> Хронометраж</div>
    <a href="/start-list" class="active">Стартовый лист</a>
    <a href="/">Хронометраж</a>
    <a href="/protocol">Протокол</a>
    <a href="/settings">Настройки</a>
    <a href="/judge">Судья</a>
  </nav>

  <div class="page">

    <div class="sidebar">
      <div class="panel-header">
        Категории
        <button class="btn btn-sm btn-accent" onclick="openCatModal()">+ Добавить</button>
      </div>
      <div class="cat-list" id="cat-list">
        <div class="cat-item active" data-id="" onclick="selectCategory(this, '')">
          <div>
            <div class="cat-name">Все участники</div>
            <div class="cat-meta">показать всех</div>
          </div>
          <div class="cat-count" id="cnt-all">0</div>
        </div>
      </div>
    </div>

    <div class="main-area">
      <div class="toolbar">
        <input type="text" class="search-box" id="search-input"
               placeholder="Поиск по номеру, фамилии, клубу…"
               oninput="applySearch()">
        <button class="btn btn-accent" onclick="openRiderModal()">+ Участник</button>
        <button class="btn" onclick="exportCSV()">↓ CSV</button>
        <label class="btn" style="margin:0">
          ↑ Импорт
          <input type="file" accept=".csv" style="display:none" onchange="importCSV(event)">
        </label>
      </div>
      <div class="stat-row" id="stat-row">
        <div class="stat-item">Всего: <b id="stat-total">0</b></div>
        <div class="stat-item">С EPC: <b id="stat-epc">0</b></div>
        <div class="stat-item">Без EPC: <b id="stat-noepc">0</b></div>
      </div>
      <div class="table-scroll">
        <table class="rtable">
          <thead>
            <tr>
              <th class="c" style="width:56px">Номер</th>
              <th>Фамилия</th>
              <th>Имя</th>
              <th class="c">Год</th>
              <th>Город</th>
              <th>Команда</th>
              <th>Категория</th>
              <th>EPC</th>
              <th class="c" style="width:100px">Действия</th>
            </tr>
          </thead>
          <tbody id="riders-body"></tbody>
        </table>
        <div class="empty-state" id="empty-state" style="display:none">
          <div class="icon">🏁</div>
          <div class="msg">Нет участников</div>
        </div>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="cat-modal">
    <div class="modal">
      <h2 id="cat-modal-title"><span>Новая</span> категория</h2>
      <input type="hidden" id="cat-edit-id">
      <div class="form-row">
        <label>Название</label>
        <input type="text" id="cat-name" placeholder="М18-29">
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Кругов</label>
          <input type="number" id="cat-laps" value="5" min="1">
        </div>
        <div class="form-row">
          <label>Дистанция круга (км)</label>
          <input type="number" id="cat-dist" value="5" step="0.1" min="0">
        </div>
      </div>
      <div class="form-actions">
        <button class="btn" onclick="closeCatModal()">Отмена</button>
        <button class="btn btn-accent" onclick="saveCat()">Сохранить</button>
      </div>
    </div>
  </div>

  <div class="modal-overlay" id="rider-modal">
    <div class="modal">
      <h2 id="rider-modal-title"><span>Новый</span> участник</h2>
      <input type="hidden" id="rider-edit-id">
      <div class="form-grid">
        <div class="form-row">
          <label>Стартовый номер</label>
          <input type="number" id="r-number" min="1">
        </div>
        <div class="form-row">
          <label>Категория</label>
          <select id="r-category"></select>
        </div>
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Фамилия</label>
          <input type="text" id="r-lastname">
        </div>
        <div class="form-row">
          <label>Имя</label>
          <input type="text" id="r-firstname">
        </div>
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Год рождения</label>
          <input type="number" id="r-year" min="1940" max="2020">
        </div>
        <div class="form-row">
          <label>Город</label>
          <input type="text" id="r-city">
        </div>
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Команда / клуб</label>
          <input type="text" id="r-club">
        </div>
        <div class="form-row">
          <label>EPC метки</label>
          <input type="text" id="r-epc" placeholder="оставьте пустым" class="mono" style="font-size:12px">
        </div>
      </div>
      <div class="form-actions">
        <button class="btn" onclick="closeRiderModal()">Отмена</button>
        <button class="btn btn-accent" onclick="saveRider()">Сохранить</button>
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
let allRiders = [];
let categories = [];
let selectedCatId = '';

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
  return r.json();
}

async function loadAll() {
  categories = await api('/api/categories', 'GET');
  renderCategories();
  await loadRiders();
}

async function loadRiders() {
  const qs = selectedCatId ? '?category_id=' + selectedCatId : '';
  allRiders = await api('/api/riders' + qs, 'GET');
  renderRiders();
  updateStats();
}

function renderCategories() {
  const list = document.getElementById('cat-list');
  const allItem = list.querySelector('[data-id=""]');
  list.innerHTML = '';
  list.appendChild(allItem);

  let totalRiders = 0;
  categories.forEach(c => {
    const div = document.createElement('div');
    div.className = 'cat-item' + (selectedCatId == c.id ? ' active' : '');
    div.dataset.id = c.id;
    div.onclick = () => selectCategory(div, c.id);
    div.innerHTML =
      '<div>' +
        '<div class="cat-name">' + esc(c.name) + '</div>' +
        '<div class="cat-meta">' + c.laps + ' кр. · ' + (c.distance_km || 0) + ' км</div>' +
      '</div>' +
      '<div style="display:flex;align-items:center;gap:8px">' +
        '<div class="cat-count">' + (c.rider_count || 0) + '</div>' +
        '<div class="cat-actions">' +
          '<button class="btn btn-sm" onclick="event.stopPropagation();editCat(' + c.id + ')" title="Редакт.">✎</button>' +
          '<button class="btn btn-sm btn-danger" onclick="event.stopPropagation();deleteCat(' + c.id + ')" title="Удалить">✕</button>' +
        '</div>' +
      '</div>';
    list.appendChild(div);
    totalRiders += (c.rider_count || 0);
  });

  // Обновляем счётчик "Все"
  document.getElementById('cnt-all').textContent = totalRiders;
  if (!selectedCatId) allItem.classList.add('active');
}

function selectCategory(el, catId) {
  selectedCatId = catId;
  document.querySelectorAll('.cat-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
  loadRiders();
}

function openCatModal(cat) {
  document.getElementById('cat-edit-id').value = cat ? cat.id : '';
  document.getElementById('cat-name').value = cat ? cat.name : '';
  document.getElementById('cat-laps').value = cat ? cat.laps : 5;
  document.getElementById('cat-dist').value = cat ? (cat.distance_km || 0) : 5;
  document.getElementById('cat-modal-title').innerHTML = cat
    ? '<span>Редактировать</span> категорию' : '<span>Новая</span> категория';
  document.getElementById('cat-modal').classList.add('open');
}
function closeCatModal() { document.getElementById('cat-modal').classList.remove('open'); }

async function saveCat() {
  const id = document.getElementById('cat-edit-id').value;
  const body = {
    name: document.getElementById('cat-name').value.trim(),
    laps: parseInt(document.getElementById('cat-laps').value) || 1,
    distance_km: parseFloat(document.getElementById('cat-dist').value) || 0,
  };
  if (!body.name) { toast('Введите название', true); return; }

  if (id) {
    await api('/api/categories/' + id, 'PUT', body);
    toast('Категория обновлена');
  } else {
    await api('/api/categories', 'POST', body);
    toast('Категория создана');
  }
  closeCatModal();
  loadAll();
}

async function editCat(catId) {
  const cat = categories.find(c => c.id === catId);
  if (cat) openCatModal(cat);
}

async function deleteCat(catId) {
  if (!confirm('Удалить категорию? Участники в ней не должны быть.')) return;
  const res = await api('/api/categories/' + catId, 'DELETE');
  if (res.error) { toast(res.error, true); return; }
  toast('Категория удалена');
  if (selectedCatId == catId) selectedCatId = '';
  loadAll();
}

function renderRiders() {
  const tbody = document.getElementById('riders-body');
  const query = document.getElementById('search-input').value.toLowerCase();
  const filtered = allRiders.filter(r => {
    if (!query) return true;
    return (String(r.number).includes(query) ||
            (r.last_name || '').toLowerCase().includes(query) ||
            (r.first_name || '').toLowerCase().includes(query) ||
            (r.club || '').toLowerCase().includes(query) ||
            (r.city || '').toLowerCase().includes(query) ||
            (r.epc || '').toLowerCase().includes(query));
  });

  document.getElementById('empty-state').style.display = filtered.length ? 'none' : 'flex';

  tbody.innerHTML = filtered.map(r => {
    const hasEpc = r.epc && r.epc.length > 0;
    return '<tr>' +
      '<td class="num-col">' + r.number + '</td>' +
      '<td style="font-weight:600">' + esc(r.last_name || '') + '</td>' +
      '<td>' + esc(r.first_name || '') + '</td>' +
      '<td class="c mono">' + (r.birth_year || '—') + '</td>' +
      '<td>' + esc(r.city || '') + '</td>' +
      '<td>' + esc(r.club || '') + '</td>' +
      '<td>' + esc(r.category_name || '—') + '</td>' +
      '<td class="epc-col' + (hasEpc ? ' bound' : '') + '" title="' + esc(r.epc || '') + '">' +
        (hasEpc ? r.epc : '—') + '</td>' +
      '<td><div class="actions-col">' +
        '<button class="btn btn-sm" onclick="editRider(' + r.id + ')" title="Редакт.">✎</button>' +
        '<button class="btn btn-sm btn-danger" onclick="deleteRider(' + r.id + ')" title="Удалить">✕</button>' +
      '</div></td>' +
    '</tr>';
  }).join('');
}

function applySearch() { renderRiders(); }

function updateStats() {
  const total = allRiders.length;
  const withEpc = allRiders.filter(r => r.epc && r.epc.length > 0).length;
  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-epc').textContent = withEpc;
  document.getElementById('stat-noepc').textContent = total - withEpc;
}

function openRiderModal(rider) {
  document.getElementById('rider-edit-id').value = rider ? rider.id : '';
  document.getElementById('r-number').value = rider ? rider.number : '';
  document.getElementById('r-lastname').value = rider ? (rider.last_name || '') : '';
  document.getElementById('r-firstname').value = rider ? (rider.first_name || '') : '';
  document.getElementById('r-year').value = rider ? (rider.birth_year || '') : '';
  document.getElementById('r-city').value = rider ? (rider.city || '') : '';
  document.getElementById('r-club').value = rider ? (rider.club || '') : '';
  document.getElementById('r-epc').value = rider ? (rider.epc || '') : '';
  document.getElementById('rider-modal-title').innerHTML = rider
    ? '<span>Редактировать</span> участника' : '<span>Новый</span> участник';

  const sel = document.getElementById('r-category');
  sel.innerHTML = '<option value="">— без категории —</option>';
  categories.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id; o.textContent = c.name;
    if (rider && rider.category_id === c.id) o.selected = true;
    sel.appendChild(o);
  });
  if (!rider && selectedCatId) sel.value = selectedCatId;

  document.getElementById('rider-modal').classList.add('open');
}
function closeRiderModal() { document.getElementById('rider-modal').classList.remove('open'); }

async function saveRider() {
  const id = document.getElementById('rider-edit-id').value;
  const body = {
    number: parseInt(document.getElementById('r-number').value),
    last_name: document.getElementById('r-lastname').value.trim(),
    first_name: document.getElementById('r-firstname').value.trim(),
    birth_year: parseInt(document.getElementById('r-year').value) || null,
    city: document.getElementById('r-city').value.trim(),
    club: document.getElementById('r-club').value.trim(),
    category_id: parseInt(document.getElementById('r-category').value) || null,
    epc: document.getElementById('r-epc').value.trim() || null,
  };
  if (!body.number || !body.last_name) {
    toast('Номер и фамилия обязательны', true); return;
  }

  let res;
  if (id) {
    res = await api('/api/riders/' + id, 'PUT', body);
    if (res.error) { toast(res.error, true); return; }
    toast('Участник обновлён');
  } else {
    res = await api('/api/riders', 'POST', body);
    if (res.error) { toast(res.error, true); return; }
    toast('Участник добавлен');
  }
  closeRiderModal();
  loadAll();
}

async function editRider(riderId) {
  const rider = allRiders.find(r => r.id === riderId);
  if (rider) openRiderModal(rider);
}

async function deleteRider(riderId) {
  const rider = allRiders.find(r => r.id === riderId);
  const label = rider ? '#' + rider.number + ' ' + rider.last_name : '#' + riderId;
  if (!confirm('Удалить участника ' + label + '?')) return;
  const res = await api('/api/riders/' + riderId, 'DELETE');
  if (res.error) { toast(res.error, true); return; }
  toast('Участник удалён');
  loadAll();
}

function exportCSV() {
  window.location.href = '/api/riders/export';
}

async function importCSV(event) {
  const file = event.target.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  try {
    const resp = await fetch('/api/riders/import', { method: 'POST', body: formData });
    const res = await resp.json();
    if (res.error) { toast(res.error, true); return; }
    toast('Импортировано: ' + (res.imported || 0) + ' участников');
    loadAll();
  } catch (e) {
    toast('Ошибка импорта', true);
  }
  event.target.value = '';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

loadAll();
</script>
</body>
</html>
"""



def register_start_list(app, db: Database, engine: RaceEngine = None):
    """Подключает страницу и API стартового листа к Flask-приложению."""


    @app.route("/start-list")
    def start_list_page():
        return render_template_string(START_LIST_HTML)


    @app.route("/api/categories", methods=["GET"])
    def api_categories_list():
        cats = db.get_categories()
        for c in cats:
            riders = db.get_riders(category_id=c["id"])
            c["rider_count"] = len(riders)
        return jsonify(cats)

    @app.route("/api/categories", methods=["POST"])
    def api_categories_create():
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Название обязательно"}), 400
        laps = data.get("laps", 1)
        distance_km = data.get("distance_km", 0)
        cid = db.add_category(name=name, laps=laps, distance_km=distance_km)
        return jsonify({"ok": True, "id": cid})

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    def api_categories_update(cid):
        data = request.get_json(force=True)
        db.update_category(cid, **data)
        return jsonify({"ok": True})

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    def api_categories_delete(cid):
        ok = db.delete_category(cid)
        if not ok:
            return jsonify({"error":
                "Нельзя удалить — есть участники в этой категории"}), 400
        return jsonify({"ok": True})


    @app.route("/api/riders", methods=["GET"])
    def api_riders_list():
        cat_id = request.args.get("category_id", type=int)
        riders = db.get_riders_with_category(category_id=cat_id)
        return jsonify(riders)

    @app.route("/api/riders", methods=["POST"])
    def api_riders_create():
        data = request.get_json(force=True)
        number = data.get("number")
        last_name = data.get("last_name", "").strip()
        if not number or not last_name:
            return jsonify({"error":
                "Номер и фамилия обязательны"}), 400

        existing = db.get_rider_by_number(int(number))
        if existing:
            return jsonify({"error":
                f"Номер {number} уже занят"}), 400

        epc = data.get("epc")
        if epc:
            epc_existing = db.get_rider_by_epc(epc)
            if epc_existing:
                return jsonify({"error":
                    f"EPC уже привязан к #{epc_existing['number']}"}), 400

        rid = db.add_rider(
            number=int(number),
            last_name=last_name,
            first_name=data.get("first_name", ""),
            birth_year=data.get("birth_year"),
            city=data.get("city", ""),
            club=data.get("club", ""),
            category_id=data.get("category_id"),
            epc=epc,
        )

        if engine:
            engine.reload_epc_map()

        cat_id = data.get("category_id")
        if cat_id is not None:
            try:
                cat_id = int(cat_id)
            except (ValueError, TypeError):
                cat_id = None
 
        race_id = db.get_current_race_id()
        if cat_id and race_id:
            existing_result = db.get_result_by_rider(rid)
            if not existing_result:
                others = db.get_results_by_category(cat_id)
                start_time = None
                for r in others:
                    st = r.get("start_time")
                    if st:
                        start_time = st
                        break
 
                if start_time is None:
                    start_time = time.time() * 1000
 
                db.create_result(
                    rider_id=rid,
                    category_id=cat_id,
                    start_time=start_time,
                    status="RACING",
                )

        return jsonify({"ok": True, "id": rid})

    @app.route("/api/riders/<int:rid>", methods=["PUT"])
    def api_riders_update(rid):
        data = request.get_json(force=True)

        if "number" in data:
            existing = db.get_rider_by_number(int(data["number"]))
            if existing and existing["id"] != rid:
                return jsonify({"error":
                    f"Номер {data['number']} уже занят"}), 400

        if "epc" in data and data["epc"]:
            epc_existing = db.get_rider_by_epc(data["epc"])
            if epc_existing and epc_existing["id"] != rid:
                return jsonify({"error":
                    f"EPC уже привязан к #{epc_existing['number']}"}), 400

        db.update_rider(rid, **data)

        if engine:
            engine.reload_epc_map()

        return jsonify({"ok": True})

    @app.route("/api/riders/<int:rid>", methods=["DELETE"])
    def api_riders_delete(rid):
        ok = db.delete_rider(rid)
        if not ok:
            return jsonify({"error": "Не удалось удалить участника"}), 400
        if engine:
            engine.reload_epc_map()
        return jsonify({"ok": True})


    @app.route("/api/riders/export")
    def api_riders_export():
        riders = db.get_riders_with_category()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "number", "last_name", "first_name", "birth_year",
            "city", "club", "category", "epc",
        ])
        for r in riders:
            writer.writerow([
                r["number"], r["last_name"], r["first_name"],
                r.get("birth_year", ""), r.get("city", ""),
                r.get("club", ""), r.get("category_name", ""),
                r.get("epc", ""),
            ])
        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    "attachment; filename=start_list.csv"
            },
        )


    @app.route("/api/riders/import", methods=["POST"])
    def api_riders_import():
        if "file" not in request.files:
            return jsonify({"error": "Файл не найден"}), 400

        file = request.files["file"]
        try:
            text = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            file.seek(0)
            text = file.read().decode("cp1251")

        reader_csv = csv.DictReader(io.StringIO(text))
        imported = 0
        errors = []

        cat_cache = {}
        for c in db.get_categories():
            cat_cache[c["name"].lower().strip()] = c["id"]

        for i, row in enumerate(reader_csv, start=2):
            num_str = (row.get("number") or row.get("номер")
                       or row.get("Number") or "").strip()
            last_name = (row.get("last_name") or row.get("фамилия")
                         or row.get("Фамилия") or "").strip()

            if not num_str or not last_name:
                errors.append(f"Строка {i}: пропущена (нет номера/фамилии)")
                continue

            try:
                number = int(num_str)
            except ValueError:
                errors.append(f"Строка {i}: неверный номер '{num_str}'")
                continue

            if db.get_rider_by_number(number):
                errors.append(f"Строка {i}: номер {number} уже есть")
                continue

            first_name = (row.get("first_name") or row.get("имя")
                          or row.get("Имя") or "").strip()
            birth_year = None
            by_str = (row.get("birth_year") or row.get("год")
                      or row.get("Год") or "").strip()
            if by_str:
                try:
                    birth_year = int(by_str)
                except ValueError:
                    pass

            city = (row.get("city") or row.get("город")
                    or row.get("Город") or "").strip()
            club = (row.get("club") or row.get("команда")
                    or row.get("Команда") or row.get("клуб")
                    or "").strip()
            cat_name = (row.get("category") or row.get("категория")
                        or row.get("Категория") or "").strip()
            epc = (row.get("epc") or row.get("EPC") or "").strip() or None

            cat_id = None
            if cat_name:
                cat_key = cat_name.lower().strip()
                if cat_key in cat_cache:
                    cat_id = cat_cache[cat_key]
                else:
                    cat_id = db.add_category(name=cat_name)
                    cat_cache[cat_key] = cat_id

            if epc and db.get_rider_by_epc(epc):
                errors.append(
                    f"Строка {i}: EPC '{epc}' уже привязан")
                epc = None

            db.add_rider(
                number=number, last_name=last_name,
                first_name=first_name, birth_year=birth_year,
                city=city, club=club, category_id=cat_id, epc=epc,
            )
            imported += 1

        if engine:
            engine.reload_epc_map()

        result = {"ok": True, "imported": imported}
        if errors:
            result["warnings"] = errors
        return jsonify(result)