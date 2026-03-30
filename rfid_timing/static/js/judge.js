let riders = [];
let selectedRiderId = null;
let startMode = 'mass';

let spEntries = [];
let spPlanned = null;
let spRunning = false;
let spTimer = null;
let spStartedSet = new Set();
let spNextIndex = 0;

let catTimerElapsed = {};   // category_id -> elapsed_ms from server
let catTimerPerf = {};      // category_id -> performance.now() at sync
let catTimerClosed = {};    // category_id -> bool
let globalTimerRef = null;

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

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}


function spSaveState() {
  const state = {
    running: spRunning,
    planned: spPlanned,
    startedRiders: Array.from(spStartedSet),
  };
  sessionStorage.setItem('sp_state', JSON.stringify(state));
}

function spRestoreState() {
  try {
    const raw = sessionStorage.getItem('sp_state');
    if (!raw) return false;
    const state = JSON.parse(raw);
    if (!state.running || !state.planned || !state.planned.length) return false;

    const started = new Set(state.startedRiders || []);
    const remaining = state.planned.filter(p => !started.has(p.rider_id));
    if (!remaining.length) {
      sessionStorage.removeItem('sp_state');
      return false;
    }

    const lastPlanned = state.planned[state.planned.length - 1].planned_time;
    if (Date.now() - lastPlanned > 10 * 60 * 1000) {
      sessionStorage.removeItem('sp_state');
      return false;
    }

    spPlanned = state.planned;
    spStartedSet = started;
    spRunning = true;
    return true;
  } catch(e) {
    return false;
  }
}

function spClearState() {
  sessionStorage.removeItem('sp_state');
}


function setStartMode(mode) {
  startMode = mode;
  sessionStorage.setItem('judge_start_mode', mode);
  const massBtn = document.getElementById('btn-mode-mass');
  const indBtn = document.getElementById('btn-mode-individual');
  const massSection = document.getElementById('mass-start-section');
  const indSection = document.getElementById('individual-start-section');
  if (mode === 'mass') {
    massBtn.style.background = 'var(--accent)'; massBtn.style.color = 'var(--bg)';
    indBtn.style.background = 'transparent'; indBtn.style.color = 'var(--text-dim)';
    massSection.style.display = 'block'; indSection.style.display = 'none';
  } else {
    indBtn.style.background = 'var(--accent)'; indBtn.style.color = 'var(--bg)';
    massBtn.style.background = 'transparent'; massBtn.style.color = 'var(--text-dim)';
    massSection.style.display = 'none'; indSection.style.display = 'block';
    spLoadProtocol();
    spUpdateAddSelect();
  }
}


function spUpdateAddSelect() {
  const sel = document.getElementById('sp-add-rider');
  const catId = document.getElementById('race-category').value;
  const inList = new Set(spEntries.map(e => e.rider_id));
  sel.innerHTML = '<option value="">+ Добавить участника…</option>';
  riders.filter(r => {
    if (inList.has(r.id)) return false;
    if (catId && r.category_id != catId) return false;
    return true;
  }).forEach(r => {
    const o = document.createElement('option');
    o.value = r.id;
    o.textContent = '#' + r.number + ' ' + (r.last_name || '') + ' ' + (r.first_name || '');
    sel.appendChild(o);
  });
}

function spAddRider() {
  const sel = document.getElementById('sp-add-rider');
  const rid = parseInt(sel.value);
  if (!rid) return;
  const r = riders.find(x => x.id === rid);
  if (!r) return;
  spEntries.push({
    rider_id: r.id, rider_number: r.number,
    last_name: r.last_name || '', first_name: r.first_name || '',
  });
  spRenderList();
  spUpdateAddSelect();
  spSaveToServer();
}

function spRemoveEntry(index) {
  spEntries.splice(index, 1);
  spRenderList();
  spUpdateAddSelect();
  spSaveToServer();
}

function spRenderList() {
  const list = document.getElementById('sp-list');
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;

  if (!spEntries.length) {
    list.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim);font-size:11px">' +
      'Протокол пуст — нажмите «Авто» или добавьте участников</div>';
    return;
  }

  list.innerHTML = spEntries.map((e, i) => {
    const offsetSec = i * interval;
    const mm = Math.floor(offsetSec / 60);
    const ss = offsetSec % 60;
    const timeStr = (mm > 0 ? mm + ':' + String(ss).padStart(2, '0') : ss + 'с');
    const isStarted = spStartedSet.has(e.rider_id);
    const isNext = spRunning && !isStarted && i === spFindNextVisualIndex();
    let cls = 'sp-item';
    if (isStarted) cls += ' sp-started';
    if (isNext) cls += ' sp-active';

    return '<div class="' + cls + '" draggable="' + (spRunning ? 'false' : 'true') + '" data-idx="' + i + '"' +
      ' ondragstart="spDragStart(event)" ondragover="spDragOver(event)" ondrop="spDrop(event)" ondragend="spDragEnd(event)">' +
      '<span class="sp-pos">' + (i + 1) + '</span>' +
      '<span class="sp-num">#' + e.rider_number + '</span>' +
      '<span class="sp-name">' + e.last_name + ' ' + e.first_name + '</span>' +
      '<span class="sp-time">+' + timeStr + '</span>' +
      (spRunning ? (isStarted ? '<span style="color:var(--green);font-size:10px;font-weight:700">✓</span>' : '') :
        '<span class="sp-del" onclick="spRemoveEntry(' + i + ')">✕</span>') +
    '</div>';
  }).join('');
}

function spFindNextVisualIndex() {
  if (!spPlanned) return -1;
  for (let i = 0; i < spPlanned.length; i++) {
    if (!spStartedSet.has(spPlanned[i].rider_id)) return i;
  }
  return -1;
}

let spDragIdx = null;
function spDragStart(e) { spDragIdx = parseInt(e.target.dataset.idx); e.target.classList.add('dragging'); }
function spDragEnd(e) { e.target.classList.remove('dragging'); document.querySelectorAll('.sp-item').forEach(el => el.classList.remove('drag-over')); }
function spDragOver(e) {
  e.preventDefault();
  const el = e.target.closest('.sp-item');
  if (el) { document.querySelectorAll('.sp-item').forEach(x => x.classList.remove('drag-over')); el.classList.add('drag-over'); }
}
function spDrop(e) {
  e.preventDefault();
  const el = e.target.closest('.sp-item');
  if (!el) return;
  const dropIdx = parseInt(el.dataset.idx);
  if (spDragIdx === null || spDragIdx === dropIdx) return;
  const [moved] = spEntries.splice(spDragIdx, 1);
  spEntries.splice(dropIdx, 0, moved);
  spDragIdx = null;
  spRenderList();
  spSaveToServer();
}

async function spAutoFill() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { toast('Выберите категорию', true); return; }
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;
  const res = await api('/api/judge/start-protocol/auto-fill', 'POST', {
    category_id: parseInt(catId), interval_sec: interval
  });
  if (res.ok) {
    toast('Протокол заполнен: ' + res.count + ' участников');
    await spLoadProtocol();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function spClear() {
  if (spRunning) { toast('Остановите протокол перед очисткой', true); return; }
  const catId = document.getElementById('race-category').value;
  if (!catId) return;
  if (!confirm('Очистить стартовый протокол?')) return;
  await api('/api/judge/start-protocol?category_id=' + catId, 'DELETE');
  spEntries = [];
  spRenderList();
  spUpdateAddSelect();
  toast('Протокол очищен');
}

async function spLoadProtocol() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { spEntries = []; spRenderList(); return; }
  const data = await api('/api/judge/start-protocol?category_id=' + catId, 'GET');
  if (Array.isArray(data)) {
    spEntries = data.map(e => ({
      rider_id: e.rider_id, rider_number: e.rider_number,
      last_name: e.last_name || '', first_name: e.first_name || '',
      entry_id: e.id, status: e.status,
    }));
    spStartedSet = new Set();
    spEntries.forEach(e => { if (e.status === 'STARTED') spStartedSet.add(e.rider_id); });
  } else {
    spEntries = [];
  }
  spRenderList();
}

async function spSaveToServer() {
  const catId = document.getElementById('race-category').value;
  if (!catId) return;
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;
  await api('/api/judge/start-protocol', 'POST', {
    category_id: parseInt(catId),
    interval_sec: interval,
    rider_ids: spEntries.map(e => e.rider_id),
  });
}


async function spLaunch() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { toast('Выберите категорию', true); return; }
  if (!spEntries.length) { toast('Протокол пуст', true); return; }
  await spSaveToServer();
  if (!confirm('Запустить стартовый протокол?\nПервый участник стартует СЕЙЧАС.')) return;

  const res = await api('/api/judge/start-protocol/launch', 'POST', {
    category_id: parseInt(catId)
  });
  if (!res.ok) { toast(res.error || 'Ошибка запуска', true); return; }

  spPlanned = res.planned;
  spRunning = true;
  spNextIndex = 0;
  spStartedSet = new Set();

  if (spPlanned.length > 0) {
    const first = spPlanned[0];
    await spStartOneRider(first);
  }

  const clientNow = Date.now();
  for (let i = 0; i < spPlanned.length; i++) {
    const interval = spPlanned[i].offset_sec || 0;
    spPlanned[i].planned_time = clientNow + interval * 1000;
  }

  spSaveState();
  spShowRunningUI();

  if (spPlanned.length <= 1 || spStartedSet.size >= spPlanned.length) {
    spRunning = false;
    spClearState();
    spShowIdleUI();
    toast('Все участники стартовали!');
    return;
  }

  spTickCountdown();
  spTimer = setInterval(spTickCountdown, 100);
}

function spShowRunningUI() {
  document.getElementById('btn-sp-launch').style.display = 'none';
  document.getElementById('btn-sp-stop').style.display = 'block';
  document.getElementById('sp-countdown-area').style.display = 'block';
  spRenderList();
}

function spShowIdleUI() {
  document.getElementById('btn-sp-launch').style.display = 'block';
  document.getElementById('btn-sp-stop').style.display = 'none';
  document.getElementById('sp-countdown-area').style.display = 'none';
  spRenderList();
}

function spStop() {
  spRunning = false;
  if (spTimer) { clearInterval(spTimer); spTimer = null; }
  spClearState();
  spShowIdleUI();
  toast('Протокол остановлен');
}

async function spStartOneRider(entry) {
  const res = await api('/api/judge/start-protocol/start-rider', 'POST', {
    entry_id: entry.entry_id,
    rider_id: entry.rider_id,
  });
  if (res.ok) {
    spStartedSet.add(entry.rider_id);
    spSaveState();
    toast('СТАРТ: #' + entry.rider_number + ' ' + entry.rider_name);
    loadRaceStatus();
  } else {
    if (res.error && res.error.includes('уже в гонке')) {
      spStartedSet.add(entry.rider_id);
      spSaveState();
    } else {
      toast('Ошибка старта #' + entry.rider_number + ': ' + (res.error || ''), true);
    }
  }
}

let spStarting = false;

function spTickCountdown() {
  if (!spRunning || !spPlanned || !spPlanned.length || spStarting) return;

  const now = Date.now();

  let nextIdx = -1;
  for (let i = 0; i < spPlanned.length; i++) {
    if (!spStartedSet.has(spPlanned[i].rider_id)) {
      nextIdx = i;
      break;
    }
  }

  if (nextIdx === -1) {
    spRunning = false;
    if (spTimer) { clearInterval(spTimer); spTimer = null; }
    spClearState();
    spShowIdleUI();
    toast('Все участники стартовали!');
    return;
  }

  const next = spPlanned[nextIdx];
  const timeLeft = next.planned_time - now;

  const remain = Math.max(0, timeLeft);
  const sec = Math.ceil(remain / 1000);
  const mm = Math.floor(sec / 60);
  const ss = sec % 60;
  const timerEl = document.getElementById('sp-countdown-timer');
  timerEl.textContent = String(mm).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
  timerEl.className = 'sp-countdown' + (sec <= 3 ? ' go' : '');

  document.getElementById('sp-next-info').innerHTML =
    'Следующий: <b>#' + next.rider_number + '</b> ' + next.rider_name;

  if (timeLeft <= 50) {
    spStarting = true;
    spStartOneRider(next).then(() => {
      spStarting = false;
      spRenderList();
    });
  }
}


async function doIndividualStart() {
  if (!selectedRiderId) { toast('Выберите участника для старта', true); return; }
  const r = riders.find(x => x.id === selectedRiderId);
  const label = r ? '#' + r.number + ' ' + r.last_name : '#' + selectedRiderId;
  if (!confirm('Дать индивидуальный старт участнику ' + label + '?')) return;
  const res = await api('/api/judge/individual-start', 'POST', { rider_id: selectedRiderId });
  if (res.ok) {
    toast('Старт: ' + (res.info && res.info.rider_name || label));
    loadRaceStatus(); refreshRiderPanel();
  } else {
    toast(res.error || 'Ошибка старта', true);
  }
}


let ddIndex = -1;
let ddFiltered = [];

function onSearchInput() { renderDropdown(); document.getElementById('rider-dropdown').classList.add('open'); }
function onSearchFocus() {
  document.getElementById('rider-search').select(); ddIndex = -1;
  renderDropdown(); document.getElementById('rider-dropdown').classList.add('open');
}
function onSearchKey(e) {
  const dd = document.getElementById('rider-dropdown');
  const isOpen = dd.classList.contains('open');
  if (e.key === 'ArrowDown') { e.preventDefault(); if (!isOpen) { renderDropdown(); dd.classList.add('open'); } ddIndex = Math.min(ddIndex + 1, ddFiltered.length - 1); highlightItem(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); ddIndex = Math.max(ddIndex - 1, 0); highlightItem(); }
  else if (e.key === 'Enter') { e.preventDefault(); if (ddIndex >= 0 && ddIndex < ddFiltered.length) selectRider(ddFiltered[ddIndex].id); else if (ddFiltered.length === 1) selectRider(ddFiltered[0].id); }
  else if (e.key === 'Escape') { dd.classList.remove('open'); document.getElementById('rider-search').blur(); }
}
function highlightItem() { document.querySelectorAll('.rider-dropdown-item').forEach((el, i) => { el.classList.toggle('active', i === ddIndex); if (i === ddIndex) el.scrollIntoView({ block: 'nearest' }); }); }

function renderDropdown() {
  const query = (document.getElementById('rider-search').value || '').toLowerCase();
  const dd = document.getElementById('rider-dropdown');
  ddFiltered = riders.filter(r => { if (!query) return true; return String(r.number).includes(query) || (r.last_name||'').toLowerCase().includes(query) || (r.first_name||'').toLowerCase().includes(query); });
  if (!ddFiltered.length) { dd.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim);font-size:12px">Не найдено</div>'; return; }
  dd.innerHTML = ddFiltered.map((r, i) =>
    '<div class="rider-dropdown-item' + (i === ddIndex ? ' active' : '') + '" onclick="selectRider(' + r.id + ')">' +
    '<span class="rdi-num">#' + r.number + '</span><span class="rdi-name">' + (r.last_name||'') + ' ' + (r.first_name||'') + '</span></div>'
  ).join('');
}

function selectRider(riderId) {
  selectedRiderId = riderId;
  const r = riders.find(x => x.id === riderId);
  document.getElementById('rider-dropdown').classList.remove('open');
  if (!r) return;
  document.getElementById('rider-search').value = '#' + r.number + ' ' + r.last_name + ' ' + (r.first_name || '');
  document.getElementById('sr-num').textContent = '#' + r.number;
  document.getElementById('sr-name').textContent = r.last_name + ' ' + (r.first_name || '');
  document.getElementById('sr-meta').textContent = (r.category_name || '—') + ' · ' + (r.club || '—') + ' · ' + (r.city || '');
  document.getElementById('selected-info').classList.add('visible');
  lastLapsHash = '';
  loadRiderFinishInfo(riderId);
  loadRiderLaps(riderId);
}

async function loadRiderFinishInfo(riderId) {
  try {
    const data = await api('/api/judge/rider-status/' + riderId, 'GET');
    const cfi = document.getElementById('current-finish-info');
    const nfi = document.getElementById('no-finish-info');
    const srs = document.getElementById('sr-status');
    if (data.status === 'FINISHED' && data.total_time_ms != null) {
      const ms = data.total_time_ms; const m = Math.floor(Math.abs(ms)/1000/60); const s = (Math.abs(ms)/1000)%60;
      const timeStr = String(m).padStart(2,'0') + ':' + s.toFixed(1).padStart(4,'0');
      document.getElementById('current-finish-time').textContent = timeStr;
      document.getElementById('edit-finish-mm').value = String(m);
      document.getElementById('edit-finish-ss').value = s.toFixed(1);
      cfi.style.display = 'block'; nfi.style.display = 'none';
      srs.innerHTML = '<span style="color:var(--green);font-weight:700;font-size:12px">FINISHED</span>';
    } else {
      cfi.style.display = 'none'; nfi.style.display = data.status === 'RACING' ? 'block' : 'none';
      document.getElementById('edit-finish-mm').value = ''; document.getElementById('edit-finish-ss').value = '';
      srs.innerHTML = '<span style="font-weight:700;font-size:12px;color:' +
        (data.status==='RACING'?'var(--accent)':data.status==='DNF'?'var(--red)':data.status==='DSQ'?'var(--red)':'var(--text-dim)') +
        '">' + (data.status||'—') + '</span>' +
        (data.dnf_reason ? '<span style="font-size:10px;color:var(--text-dim);margin-left:6px">' + data.dnf_reason + '</span>' : '');
    }
  } catch(e) { document.getElementById('current-finish-info').style.display = 'none'; document.getElementById('no-finish-info').style.display = 'none'; }
}

document.addEventListener('click', function(e) { if (!e.target.closest('.rider-selector')) document.getElementById('rider-dropdown').classList.remove('open'); });

function fmtLapMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms)/1000; const m = Math.floor(totalSec/60); const s = totalSec%60;
  return String(m).padStart(2,'0') + ':' + s.toFixed(1).padStart(4,'0');
}

let lastLapsHash = '';

function buildLapRowHtml(l) {
  return '<div class="lap-row" id="lap-row-' + l.id + '">' +
    '<span class="lr-num">' + (l.lap_number === 0 ? '0' : l.lap_number) + '</span>' +
    '<span class="lr-time">' + fmtLapMs(l.lap_time) + '</span>' +
    '<input id="lap-mm-' + l.id + '" placeholder="М" value="' + Math.floor(Math.abs(l.lap_time||0)/1000/60) + '">' +
    '<span style="color:var(--text-dim)">:</span>' +
    '<input id="lap-ss-' + l.id + '" placeholder="С.д" style="width:50px" value="' + (((Math.abs(l.lap_time||0)/1000)%60).toFixed(1)) + '">' +
    '<span class="lr-btn save" onclick="saveLap(' + l.id + ')">✓</span>' +
    '<span class="lr-btn del" onclick="deleteLap(' + l.id + ')">✕</span></div>';
}

async function loadRiderLaps(riderId) {
  try {
    const data = await api('/api/judge/rider-laps/' + riderId, 'GET');
    const laps = Array.isArray(data) ? data : [];
    const listEl = document.getElementById('laps-list');
    if (!laps.length) { lastLapsHash = ''; listEl.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Нет зафиксированных кругов</div>'; return; }
    const newHash = laps.map(l => l.id+':'+l.lap_number+':'+l.lap_time).join('|');
    if (newHash === lastLapsHash) return;
    const focused = document.activeElement;
    if (focused && focused.id && focused.id.startsWith('lap-')) {
      const existingIds = new Set(); listEl.querySelectorAll('.lap-row').forEach(row => { existingIds.add(parseInt(row.id.replace('lap-row-',''))); });
      laps.forEach(l => { if (!existingIds.has(l.id)) listEl.insertAdjacentHTML('beforeend', buildLapRowHtml(l)); });
      lastLapsHash = newHash; return;
    }
    lastLapsHash = newHash;
    listEl.innerHTML = laps.map(l => buildLapRowHtml(l)).join('');
  } catch(e) {}
}

async function refreshRiderPanel() { if (selectedRiderId) { await loadRiderFinishInfo(selectedRiderId); await loadRiderLaps(selectedRiderId); } }

async function saveLap(lapId) {
  const mm = document.getElementById('lap-mm-'+lapId).value.trim(); const ss = document.getElementById('lap-ss-'+lapId).value.trim();
  const minutes = parseInt(mm)||0; const seconds = parseFloat(ss)||0;
  if (seconds >= 60 || seconds < 0) { toast('Неверное время', true); return; }
  const lapTimeMs = Math.round((minutes*60+seconds)*1000);
  const res = await api('/api/judge/lap/'+lapId, 'PUT', { lap_time_ms: lapTimeMs });
  if (res.ok) { toast('Круг обновлён'); lastLapsHash=''; await refreshRiderPanel(); } else toast(res.error||'Ошибка', true);
}
async function deleteLap(lapId) {
  if (!confirm('Удалить этот круг?')) return;
  const res = await api('/api/judge/lap/'+lapId, 'DELETE');
  if (res.ok) { toast('Круг удалён'); lastLapsHash=''; await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true);
}
async function doAddManualLap() {
  if (!requireRider()) return;
  const res = await api('/api/judge/manual-lap', 'POST', { rider_id: selectedRiderId });
  if (res.ok) { toast('Круг добавлен'); lastLapsHash=''; await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true);
}

function requireRider() { if (!selectedRiderId) { toast('Выберите участника', true); return false; } return true; }

async function doDNF(reason) { if (!requireRider()) return; const res = await api('/api/judge/dnf', 'POST', { rider_id: selectedRiderId, reason_code: reason }); if (res.ok) { toast('DNF зафиксирован'); loadLog(); refreshRiderPanel(); } else toast(res.error||'Ошибка', true); }
async function doDSQ() { if (!requireRider()) return; const reason = document.getElementById('dsq-reason').value.trim(); const res = await api('/api/judge/dsq', 'POST', { rider_id: selectedRiderId, reason }); if (res.ok) { toast('DSQ — дисквалификация'); document.getElementById('dsq-reason').value=''; loadLog(); refreshRiderPanel(); } else toast(res.error||'Ошибка', true); }
async function doTimePenalty() { if (!requireRider()) return; const seconds = parseFloat(document.getElementById('pen-seconds').value)||0; const reason = document.getElementById('pen-reason').value.trim(); if (seconds <= 0) { toast('Укажите время штрафа', true); return; } const res = await api('/api/judge/time-penalty', 'POST', { rider_id: selectedRiderId, seconds, reason }); if (res.ok) { toast('+'+seconds+' сек штрафа'); document.getElementById('pen-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }
async function doExtraLap() { if (!requireRider()) return; const laps = parseInt(document.getElementById('extra-laps').value)||1; const reason = document.getElementById('extra-reason').value.trim(); const res = await api('/api/judge/extra-lap', 'POST', { rider_id: selectedRiderId, laps, reason }); if (res.ok) { toast('+'+laps+' штрафной круг'); document.getElementById('extra-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }
async function doWarning() { if (!requireRider()) return; const reason = document.getElementById('warn-reason').value.trim(); const res = await api('/api/judge/warning', 'POST', { rider_id: selectedRiderId, reason }); if (res.ok) { toast('Предупреждение выдано'); document.getElementById('warn-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }

async function deletePenalty(pid) { if (!confirm('Удалить это решение?')) return; const res = await api('/api/judge/penalty/'+pid, 'DELETE'); if (res.ok) { toast('Решение отменено'); loadLog(); } else toast(res.error||'Ошибка', true); }

async function loadLog() {
  try {
    const data = await api('/api/judge/log', 'GET');
    const log = Array.isArray(data) ? data : [];
    const list = document.getElementById('log-list');
    if (!log.length) { list.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-dim)">Нет записей</div>'; return; }
    const typeLabels = { TIME_PENALTY:'Штраф', EXTRA_LAP:'Доп. круг', WARNING:'Предупр.', DSQ:'DSQ', DNF:'DNF' };
    list.innerHTML = log.map(item => {
      const timeStr = new Date(item.created_at*1000).toLocaleTimeString('ru-RU');
      return '<div class="log-item"><div class="li-badge '+item.type+'">'+(typeLabels[item.type]||item.type)+'</div>' +
        '<div class="li-info"><div class="li-rider">#'+item.rider_number+' '+item.last_name+'</div>' +
        '<div class="li-detail">'+(item.reason||item.type)+'</div></div>' +
        '<div class="li-time">'+timeStr+'</div>' +
        '<div class="li-delete" onclick="deletePenalty('+item.id+')" title="Отменить">✕</div></div>';
    }).join('');
  } catch(e) {}
}



function updateCategoryTimers() {
  const timersEl = document.getElementById('cat-timers');
  if (!timersEl) return;

  const catId = document.getElementById('race-category').value;
  let html = '';

  const entries = Object.entries(catTimerElapsed);
  if (!entries.length) {
    timersEl.innerHTML = '';
    return;
  }

  entries.forEach(([cid, elapsed]) => {
    const isClosed = catTimerClosed[cid] || false;
    const perfRef = catTimerPerf[cid];

    let displayMs = elapsed;
    if (!isClosed && perfRef) {
      displayMs = elapsed + (performance.now() - perfRef);
    }

    const isSelected = String(cid) === String(catId);
    const catInfo = (window._catNameMap || {})[cid] || ('Кат. ' + cid);

    const color = isClosed ? 'var(--text-dim)' : (isSelected ? 'var(--accent)' : 'var(--green)');
    const label = isClosed ? '✓ ' + catInfo : catInfo;

    html += '<div class="cat-timer-item" style="' +
      (isSelected ? 'background:var(--accent-glow);border:1px solid rgba(56,189,248,0.3);' : '') +
      'padding:4px 8px;border-radius:4px;display:flex;align-items:center;gap:8px;margin-bottom:3px">' +
      '<span style="font-size:10px;font-weight:700;color:' + color + ';min-width:80px;white-space:nowrap">' + label + '</span>' +
      '<span style="font-family:var(--mono);font-size:16px;font-weight:700;color:' + color + '">' + fmtMs(displayMs) + '</span>' +
      (isClosed ? '<span style="font-size:9px;color:var(--text-dim)">завершена</span>' : '') +
      '</div>';
  });

  timersEl.innerHTML = html;
}

function startGlobalTimerTick() {
  if (globalTimerRef) return;
  globalTimerRef = setInterval(updateCategoryTimers, 100);
}


async function initJudge() {
  await loadRiders();
  loadLog();
  loadNotes();
  await loadCategoriesAndRestore();

  const savedInterval = sessionStorage.getItem('sp_interval');
  if (savedInterval) {
    document.getElementById('sp-interval').value = savedInterval;
  }

  const savedMode = sessionStorage.getItem('judge_start_mode');
  if (savedMode === 'individual') {
    setStartMode('individual');

    if (spRestoreState()) {
      spShowRunningUI();
      spTickCountdown();
      spTimer = setInterval(spTickCountdown, 100);
    }
  }

  startGlobalTimerTick();
}

initJudge();

setInterval(loadLog, 5000);
setInterval(loadRaceStatus, 2000);
setInterval(function() {
  if (!selectedRiderId) return;
  const el = document.activeElement;
  if (el && el.tagName === 'INPUT' && el.closest('#laps-section')) return;
  refreshRiderPanel();
}, 3000);

async function loadCategoriesAndRestore() {
  const cats = await api('/api/categories', 'GET');
  const sel = document.getElementById('race-category');
  sel.innerHTML = '<option value="">— Выберите категорию —</option>';
  window._catNameMap = {};
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
    window._catNameMap[String(c.id)] = c.name;
  });
  const saved = sessionStorage.getItem('judge_cat_id');
  if (saved && sel.querySelector('option[value="'+saved+'"]')) sel.value = saved;
  else if (cats.length === 1) sel.value = cats[0].id;
  loadRaceStatus();
}

async function loadRaceStatus() {
  const catId = document.getElementById('race-category').value;
  if (catId) sessionStorage.setItem('judge_cat_id', catId);

  try {
    const qs = catId ? '?category_id=' + catId : '';
    const resp = await fetch('/api/state' + qs);
    const data = await resp.json();
    const st = data.status || {};
    const catStates = data.category_states || {};

    if (data.categories) {
      data.categories.forEach(c => {
        window._catNameMap = window._catNameMap || {};
        window._catNameMap[String(c.id)] = c.name;
      });
    }

    const now = performance.now();
    Object.entries(catStates).forEach(([cid, cs]) => {
      if (cs.elapsed_ms !== null && cs.elapsed_ms !== undefined) {
        catTimerElapsed[cid] = cs.elapsed_ms;
        catTimerPerf[cid] = now;
        catTimerClosed[cid] = cs.closed;
      }
    });

    if (!catId) {
      document.getElementById('race-status-bar').style.display = 'none';
      document.getElementById('btn-mass-start').disabled = false;
      document.getElementById('btn-finish-race').disabled = true;
      document.getElementById('btn-finish-race-ind').disabled = true;
      return;
    }

    const racing = st.RACING || 0;
    const finished = st.FINISHED || 0;
    const dnf = (st.DNF || 0) + (st.DSQ || 0);
    const total = racing + finished + dnf;
    document.getElementById('rs-racing').textContent = racing;
    document.getElementById('rs-finished').textContent = finished;
    document.getElementById('rs-dnf').textContent = dnf;
    document.getElementById('race-status-bar').style.display = 'block';

    const thisCatClosed = data.category_closed === true;
    const thisCatStarted = data.category_started === true;
    const raceClosed = data.race_closed === true;
    const effectivelyClosed = thisCatClosed || raceClosed;

    document.getElementById('btn-mass-start').disabled = thisCatStarted || effectivelyClosed;
    document.getElementById('btn-finish-race').disabled = !thisCatStarted || effectivelyClosed;
    document.getElementById('btn-finish-race-ind').disabled = !thisCatStarted || effectivelyClosed;

    const startBtn = document.getElementById('btn-mass-start');
    if (effectivelyClosed) startBtn.textContent = 'Категория завершена';
    else if (thisCatStarted) startBtn.textContent = racing > 0 ? 'Гонка идёт' : 'Гонка активна';
    else startBtn.textContent = '▶ Масс-старт';

    document.getElementById('btn-individual-start').disabled = effectivelyClosed;
    document.getElementById('btn-sp-launch').disabled = effectivelyClosed;

    const finBtn = document.getElementById('btn-finish-race');
    finBtn.textContent = effectivelyClosed ? 'Категория завершена' : '■ Завершить категорию';
    document.getElementById('btn-finish-race-ind').textContent = effectivelyClosed ? 'Категория завершена' : '■ Завершить';

    document.querySelectorAll('.actions-grid .btn, #laps-section .btn').forEach(b => {
      b.disabled = effectivelyClosed;
    });

  } catch(e) {}
}

document.getElementById('race-category').addEventListener('change', function() {
  loadRaceStatus();
  if (startMode === 'individual') { spLoadProtocol(); spUpdateAddSelect(); }
});
document.getElementById('sp-interval').addEventListener('change', function() { sessionStorage.setItem('sp_interval', this.value); spRenderList(); });
document.getElementById('sp-interval').addEventListener('input', function() { sessionStorage.setItem('sp_interval', this.value); spRenderList(); });

async function doMassStart() { const catId = document.getElementById('race-category').value; if (!catId) { toast('Выберите категорию', true); return; } if (!confirm('Запустить масс-старт для выбранной категории?')) return; const res = await api('/api/judge/mass-start', 'POST', { category_id: parseInt(catId) }); if (res.ok) { toast('Масс-старт! Участников: '+(res.info&&res.info.riders_started||'?')); loadRaceStatus(); } else toast(res.error||'Ошибка', true); }
async function doUnfinishRider() { if (!requireRider()) return; const r = riders.find(x => x.id === selectedRiderId); const label = r ? '#'+r.number+' '+r.last_name : '#'+selectedRiderId; if (!confirm('Отменить финиш '+label+'?\nУчастник вернётся в статус RACING.')) return; const res = await api('/api/judge/unfinish-rider', 'POST', { rider_id: selectedRiderId }); if (res.ok) { toast('Финиш отменён: '+label); await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true); }
async function doEditFinishTime() {
  if (!requireRider()) return;
  const mm = document.getElementById('edit-finish-mm').value.trim(); const ss = document.getElementById('edit-finish-ss').value.trim();
  if (!mm && !ss) { toast('Введите время ММ:СС.д', true); return; }
  const minutes = parseInt(mm)||0; const seconds = parseFloat(ss)||0;
  if (minutes < 0 || seconds < 0 || seconds >= 60) { toast('Неверный формат времени', true); return; }
  const totalMs = Math.round((minutes*60+seconds)*1000);
  const r = riders.find(x => x.id === selectedRiderId);
  const label = r ? '#'+r.number+' '+r.last_name : '#'+selectedRiderId;
  const timeStr = String(minutes).padStart(2,'0') + ':' + seconds.toFixed(1).padStart(4,'0');
  if (!confirm('Изменить время финиша '+label+' на '+timeStr+'?')) return;
  const res = await api('/api/judge/edit-finish-time', 'POST', { rider_id: selectedRiderId, finish_time_ms: totalMs });
  if (res.ok) { toast('Время финиша изменено: '+label+' → '+timeStr); document.getElementById('edit-finish-mm').value=''; document.getElementById('edit-finish-ss').value=''; await refreshRiderPanel(); loadRaceStatus(); }
  else toast(res.error||'Ошибка', true);
}

async function addNote() { const text = document.getElementById('note-text').value.trim(); if (!text) { toast('Введите текст заметки', true); return; } const res = await api('/api/judge/notes', 'POST', { text, rider_id: selectedRiderId||null }); if (res.ok) { toast('Заметка сохранена'); document.getElementById('note-text').value=''; loadNotes(); } else toast(res.error||'Ошибка', true); }
async function deleteNote(nid) { const res = await api('/api/judge/notes/'+nid, 'DELETE'); if (res.ok) loadNotes(); }
async function loadNotes() {
  try {
    const data = await api('/api/judge/notes', 'GET');
    const notes = Array.isArray(data) ? data : [];
    const list = document.getElementById('notes-list');
    if (!notes.length) { list.innerHTML = ''; return; }
    list.innerHTML = notes.map(n => {
      const timeStr = new Date(n.created_at*1000).toLocaleTimeString('ru-RU');
      const rider = n.rider_number ? '#'+n.rider_number+' '+(n.last_name||'')+' — ' : '';
      return '<div style="display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">' +
        '<div style="flex:1;min-width:0"><span style="color:var(--accent);font-weight:600">'+rider+'</span>' +
        '<span style="color:var(--text)">'+n.text+'</span></div>' +
        '<span style="color:var(--text-dim);font-family:var(--mono);font-size:10px;white-space:nowrap">'+timeStr+'</span>' +
        '<button class="note-del" data-nid="'+n.id+'">✕</button></div>';
    }).join('');
    list.querySelectorAll('.note-del').forEach(btn => { btn.addEventListener('click', function() { deleteNote(parseInt(this.dataset.nid)); }); });
  } catch(e) {}
}

async function doFinishRace() {
  const catId = document.getElementById('race-category').value;
  if (!catId) { toast('Выберите категорию', true); return; }
  if (!confirm('Завершить категорию?\n• Участники, проехавшие все круги → FINISHED\n• Остальные → DNF\n• Таймер категории остановится')) return;
  const res = await api('/api/judge/finish-race', 'POST', { category_id: parseInt(catId) });
  if (res.ok) { toast('Категория завершена. Финиш: '+(res.finished||0)+', DNF: '+(res.dnf_count||0)); if (spRunning) spStop(); loadRaceStatus(); loadLog(); }
  else toast(res.error||'Ошибка', true);
}
async function doNewRace() {
  if (!confirm('Создать новую гоночную сессию?\nТекущие результаты останутся в архиве.')) return;
  const res = await api('/api/settings/reset-race', 'POST');
  if (res.ok) {
    toast('Новая сессия #'+res.race_id);
    if (spRunning) spStop();
    spEntries=[]; spRenderList();
    catTimerElapsed = {};
    catTimerPerf = {};
    catTimerClosed = {};
    loadRaceStatus(); loadLog();
  }
  else toast(res.error||'Ошибка', true);
}