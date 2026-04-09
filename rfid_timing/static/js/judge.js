let riders = [];
let selectedRiderId = null;
let startMode = 'mass';

let spStates = {};
let spCountdownTimer = null;

let spEntries = [];

let catTimerElapsed = {};
let catTimerPerf = {};
let catTimerClosed = {};
let globalTimerRef = null;
let authManager = null;
let currentCategoryStarted = false;
let currentCategoryClosed = false;
let raceStatusRequestInFlight = false;
let riderPanelRequestInFlight = false;

const JUDGE_LOG_POLL_MS = 5000;
const JUDGE_RACE_STATUS_POLL_MS = 500;
const JUDGE_RIDER_PANEL_POLL_MS = 700;

function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

function setStateDisabled(el, disabled) {
  if (!el) return;
  const stateValue = disabled ? 'true' : 'false';
  const authLocked = !authManager || !authManager.isAuthenticated();
  const finalDisabled = authLocked || !!disabled;
  const ariaValue = finalDisabled ? 'true' : 'false';
  if (el.dataset.stateDisabled !== stateValue) el.dataset.stateDisabled = stateValue;
  if ('disabled' in el && el.disabled !== finalDisabled) el.disabled = finalDisabled;
  if (el.getAttribute('aria-disabled') !== ariaValue) el.setAttribute('aria-disabled', ariaValue);
  const pointerValue = finalDisabled ? 'none' : '';
  const opacityValue = finalDisabled ? '0.55' : '';
  const cursorValue = finalDisabled ? 'not-allowed' : '';
  if (el.style.pointerEvents !== pointerValue) el.style.pointerEvents = pointerValue;
  if (el.style.opacity !== opacityValue) el.style.opacity = opacityValue;
  if (el.style.cursor !== cursorValue) el.style.cursor = cursorValue;
  if (el.classList.contains('is-disabled') !== finalDisabled) el.classList.toggle('is-disabled', finalDisabled);
}

function setSectionStateDisabled(selector, disabled, excludeIds) {
  const exclude = new Set(excludeIds || []);
  document.querySelectorAll(selector).forEach(function (el) {
    if (exclude.has(el.id)) return;
    setStateDisabled(el, disabled);
  });
}

function ensureProtocolCategory(message) {
  const catId = getCatId();
  if (!catId) {
    toast(message || 'Сначала выберите категорию', true);
    return false;
  }
  return true;
}

async function api(url, method, body) {
  const opts = { method: method || 'GET' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }

  const result = await authManager.fetchJson(url, opts);
  if (result.unauthorized) {
    return { ok: false, unauthorized: true, error: 'Login required' };
  }

  const data = result.data || {};
  data._status = result.status;
  data._httpOk = result.ok;
  if (data.ok === undefined && result.ok) data.ok = true;
  if (data.ok === undefined && !result.ok) data.ok = false;
  return data;
}

async function loadRiders() {
  const data = await api('/api/riders', 'GET');
  riders = Array.isArray(data) ? data : [];
}

function requireJudgeEditAccess(message) {
  if (!authManager || authManager.isAuthenticated()) return true;
  authManager.openLogin(message || 'Для выполнения действия судьи требуется войти в систему');
  return false;
}

async function ensureJudgeAuth(message) {
  return await authManager.requireAuth(message || 'Для выполнения действия судьи требуется войти в систему');
}

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}

function getCatId() {
  return document.getElementById('race-category').value;
}


function spGetState(catId) {
  if (!catId) return null;
  if (!spStates[catId]) {
    spStates[catId] = { entries: [], planned: null, running: false, startedSet: new Set(), starting: false, pausedDelayMs: null };
  }
  return spStates[catId];
}

function spIsRunning(catId) { const s = spStates[catId]; return s && s.running; }

function spEnsureCountdownTick() {
  if (spCountdownTimer) return;
  spCountdownTimer = setInterval(function() {
    if (startMode !== 'individual') return;
    const catId = getCatId();
    if (catId && spIsRunning(catId)) spUpdateCountdownDisplay(catId);
  }, 100);
}

async function spSyncStatus(catId, silent) {
  if (!catId) {
    spUpdateUI();
    return;
  }
  const res = await api('/api/judge/start-protocol/status?category_id=' + catId, 'GET');
  const st = spGetState(catId);
  const prevRunning = !!st.running;
  const prevPlannedKey = Array.isArray(st.planned)
    ? st.planned.map(e => [e.entry_id || e.id, e.status, e.planned_time, e.actual_time].join(':')).join('|')
    : '';
  const prevStarted = new Set(st.startedSet || []);

  if (!res || !res.running && !Array.isArray(res.planned)) {
    const hadProtocol = prevRunning || prevPlannedKey !== '';
    st.running = false;
    st.planned = null;
    st.startedSet = new Set();
    st.pausedDelayMs = null;
    spSaveAllStates();
    if (hadProtocol) spRenderList();
    spUpdateUI();
    return;
  }

  st.planned = Array.isArray(res.planned) ? res.planned : [];
  st.running = !!res.running;
  st.startedSet = new Set(
    st.planned
      .filter(e => e.status === 'STARTED')
      .map(e => e.rider_id)
  );
  if (st.running) st.pausedDelayMs = null;
  const nextPlannedKey = st.planned.map(e => [e.entry_id || e.id, e.status, e.planned_time, e.actual_time].join(':')).join('|');
  const startedChanged =
    prevStarted.size !== st.startedSet.size ||
    Array.from(st.startedSet).some(riderId => !prevStarted.has(riderId));
  const protocolChanged = prevRunning !== st.running || prevPlannedKey !== nextPlannedKey;

  if (!silent) {
    st.planned.forEach(entry => {
      if (entry.status === 'STARTED' && !prevStarted.has(entry.rider_id)) {
        toast('СТАРТ: #' + entry.rider_number + ' ' + entry.rider_name);
      }
    });
  }

  spSaveAllStates();
  if (protocolChanged || startedChanged) spRenderList();
  spUpdateUI();
}

function spSaveAllStates() {
  const data = {};
  Object.entries(spStates).forEach(([catId, s]) => {
    if (s.planned && s.planned.length) {
      data[catId] = {
        planned: s.planned,
        startedRiders: Array.from(s.startedSet),
        running: !!s.running,
        pausedDelayMs: s.pausedDelayMs
      };
    }
  });
  if (Object.keys(data).length) sessionStorage.setItem('sp_states', JSON.stringify(data));
  else sessionStorage.removeItem('sp_states');
}

function spRestoreAllStates() {
  try {
    const raw = sessionStorage.getItem('sp_states');
    if (!raw) return false;
    const data = JSON.parse(raw);
    let restored = false;
    Object.entries(data).forEach(([catId, saved]) => {
      if (!saved.planned || !saved.planned.length) return;
      const started = new Set(saved.startedRiders || []);
      const remaining = saved.planned.filter(p => !started.has(p.rider_id));
      if (!remaining.length) return;
      const lastPlanned = saved.planned[saved.planned.length - 1].planned_time;
      if (saved.running && lastPlanned && Date.now() - lastPlanned > 10 * 60 * 1000) return;
      const s = spGetState(catId);
      s.planned = saved.planned;
      s.startedSet = started;
      s.running = !!saved.running;
      s.starting = false;
      s.pausedDelayMs = saved.pausedDelayMs ?? null;
      restored = true;
    });
    if (!restored) sessionStorage.removeItem('sp_states');
    return restored;
  } catch(e) { return false; }
}

function spClearStateFor(catId) {
  if (spStates[catId]) {
    spStates[catId].running = false;
    spStates[catId].planned = null;
    spStates[catId].startedSet = new Set();
    spStates[catId].starting = false;
    spStates[catId].pausedDelayMs = null;
  }
  spSaveAllStates();
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
    spSwitchToCategory();
  }
}


let spDdIndex = -1;
let spDdFiltered = [];

function spGetAvailableRiders() {
  const catId = getCatId();
  const inList = new Set(spEntries.map(e => e.rider_id));
  return riders.filter(r => {
    if (inList.has(r.id)) return false;
    if (catId && r.category_id != catId) return false;
    return true;
  });
}

function spOnSearchInput() {
  if (!ensureProtocolCategory('Нельзя собирать очередь без выбранной категории')) return;
  spDdIndex = -1;
  spRenderSearchDropdown();
  document.getElementById('sp-dropdown').classList.add('open');
}
function spOnSearchFocus() {
  if (!ensureProtocolCategory('Нельзя собирать очередь без выбранной категории')) return;
  document.getElementById('sp-search').select();
  spDdIndex = -1;
  spRenderSearchDropdown();
  document.getElementById('sp-dropdown').classList.add('open');
}

function spOnSearchKey(e) {
  const dd = document.getElementById('sp-dropdown');
  const isOpen = dd.classList.contains('open');
  if (e.key === 'ArrowDown') { e.preventDefault(); if (!isOpen) { spRenderSearchDropdown(); dd.classList.add('open'); } spDdIndex = Math.min(spDdIndex + 1, spDdFiltered.length - 1); spHighlightSearchItem(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); spDdIndex = Math.max(spDdIndex - 1, 0); spHighlightSearchItem(); }
  else if (e.key === 'Enter') { e.preventDefault(); if (spDdIndex >= 0 && spDdIndex < spDdFiltered.length) spSelectFromSearch(spDdFiltered[spDdIndex].id); else if (spDdFiltered.length === 1) spSelectFromSearch(spDdFiltered[0].id); }
  else if (e.key === 'Escape') { dd.classList.remove('open'); document.getElementById('sp-search').blur(); }
}

function spHighlightSearchItem() {
  document.querySelectorAll('#sp-dropdown .rider-dropdown-item').forEach((el, i) => {
    el.classList.toggle('active', i === spDdIndex);
    if (i === spDdIndex) el.scrollIntoView({ block: 'nearest' });
  });
}

function spRenderSearchDropdown() {
  if (!getCatId()) {
    document.getElementById('sp-dropdown').innerHTML = '<div style="padding:8px 10px;color:var(--text-dim);font-size:11px">Сначала выберите категорию</div>';
    spDdFiltered = [];
    return;
  }
  const query = (document.getElementById('sp-search').value || '').toLowerCase();
  const dd = document.getElementById('sp-dropdown');
  const available = spGetAvailableRiders();
  spDdFiltered = available.filter(r => { if (!query) return true; return String(r.number).includes(query) || (r.last_name||'').toLowerCase().includes(query) || (r.first_name||'').toLowerCase().includes(query); });
  if (!spDdFiltered.length) { dd.innerHTML = '<div style="padding:8px 10px;color:var(--text-dim);font-size:11px">' + (available.length === 0 ? 'Все участники уже в протоколе' : 'Не найдено') + '</div>'; return; }
  dd.innerHTML = spDdFiltered.map((r, i) =>
    '<div class="rider-dropdown-item' + (i === spDdIndex ? ' active' : '') + '" onclick="spSelectFromSearch(' + r.id + ')" style="padding:4px 8px;font-size:11px">' +
    '<span class="rdi-num" style="min-width:28px">#' + r.number + '</span><span class="rdi-name">' + (r.last_name||'') + ' ' + (r.first_name||'') + '</span></div>'
  ).join('');
}

function spSelectFromSearch(riderId) {
  if (!requireJudgeEditAccess('Для выполнения действия судьи требуется войти в систему')) return;
  if (!ensureProtocolCategory('Нельзя собирать очередь без выбранной категории')) return;
  const r = riders.find(x => x.id === riderId);
  if (!r) return;
  document.getElementById('sp-dropdown').classList.remove('open');
  document.getElementById('sp-search').value = '';
  if (spEntries.some(e => e.rider_id === r.id)) { toast('Участник уже в протоколе', true); return; }
  spEntries.push({ rider_id: r.id, rider_number: r.number, last_name: r.last_name || '', first_name: r.first_name || '' });
  spRenderList();
  spSaveToServer();
  toast('#' + r.number + ' ' + (r.last_name || '') + ' добавлен');
}

document.addEventListener('click', function(e) {
  if (!e.target.closest('.rider-selector')) {
    document.getElementById('rider-dropdown').classList.remove('open');
    const spDd = document.getElementById('sp-dropdown');
    if (spDd) spDd.classList.remove('open');
  }
});

function spFindNextVisualIndex(catId) {
  const st = spStates[catId];
  if (!st || !st.planned) return -1;
  for (let i = 0; i < st.planned.length; i++) { if (!st.startedSet.has(st.planned[i].rider_id)) return i; }
  return -1;
}

let spDragIdx = null;
function spDragStart(e) { if (!requireJudgeEditAccess('Для выполнения действия судьи требуется войти в систему')) { e.preventDefault(); return; } spDragIdx = parseInt(e.target.dataset.idx); e.target.classList.add('dragging'); }
function spDragEnd(e) { e.target.classList.remove('dragging'); document.querySelectorAll('.sp-item').forEach(el => el.classList.remove('drag-over')); }
function spDragOver(e) { e.preventDefault(); const el = e.target.closest('.sp-item'); if (el) { document.querySelectorAll('.sp-item').forEach(x => x.classList.remove('drag-over')); el.classList.add('drag-over'); } }
function spDrop(e) { if (!requireJudgeEditAccess('Для выполнения действия судьи требуется войти в систему')) { e.preventDefault(); return; } e.preventDefault(); const el = e.target.closest('.sp-item'); if (!el) return; const dropIdx = parseInt(el.dataset.idx); if (spDragIdx === null || spDragIdx === dropIdx) return; const [moved] = spEntries.splice(spDragIdx, 1); spEntries.splice(dropIdx, 0, moved); spDragIdx = null; spRenderList(); spSaveToServer(); }

async function spAutoFill() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const catId = getCatId();
  if (!catId) { toast('Выберите категорию', true); return; }
  if (spIsRunning(catId)) { toast('Протокол запущен — остановите сначала', true); return; }
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;
  const res = await api('/api/judge/start-protocol/auto-fill', 'POST', { category_id: parseInt(catId), interval_sec: interval });
  if (res.ok) { toast('Протокол заполнен: ' + res.count + ' участников'); await spLoadProtocol(); } else toast(res.error || 'Ошибка', true);
}

async function spClear() {
  if (!await ensureJudgeAuth('Clearing protocol requires login')) return;
  const catId = getCatId();
  if (spIsRunning(catId)) { toast('Остановите протокол перед очисткой', true); return; }
  if (!catId) return;
  if (!confirm('Очистить стартовый протокол?')) return;
  await api('/api/judge/start-protocol?category_id=' + catId, 'DELETE');
  spEntries = []; spRenderList(); toast('Протокол очищен');
}

async function spLoadProtocol() {
  const catId = getCatId();
  if (!catId) { spEntries = []; spRenderList(); return; }
  const data = await api('/api/judge/start-protocol?category_id=' + catId, 'GET');
  if (Array.isArray(data)) {
    spEntries = data.map(e => ({ rider_id: e.rider_id, rider_number: e.rider_number, last_name: e.last_name || '', first_name: e.first_name || '', entry_id: e.id, status: e.status }));
  } else { spEntries = []; }
  await spSyncStatus(catId, true);
  spRenderList();
}

async function spSaveToServer() {
  if (!await ensureJudgeAuth('Saving protocol requires login')) return;
  const catId = getCatId();
  if (!catId) return;
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;
  await api('/api/judge/start-protocol', 'POST', { category_id: parseInt(catId), interval_sec: interval, rider_ids: spEntries.map(e => e.rider_id) });
}

function spSwitchToCategory() {
  const catId = getCatId();
  const intervalEl = document.getElementById('sp-interval');
  if (catId) {
    const saved = sessionStorage.getItem('sp_interval_' + catId);
    if (saved) intervalEl.value = saved;
  } else {
    spEntries = [];
    document.getElementById('sp-search').value = '';
    document.getElementById('sp-dropdown').classList.remove('open');
  }
  spLoadProtocol();
  spUpdateUI();
}

async function doIndividualStart() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const startBtn = document.getElementById('btn-individual-start');
  if (startBtn && startBtn.disabled) {
    toast(startBtn.textContent || 'Индивидуальный старт сейчас недоступен', true);
    return;
  }
  if (!ensureProtocolCategory('Сначала выберите категорию')) return;
  if (!selectedRiderId) { toast('Выберите участника для старта', true); return; }
  const r = riders.find(x => x.id === selectedRiderId);
  const label = r ? '#' + r.number + ' ' + r.last_name : '#' + selectedRiderId;
  if (!confirm('Дать индивидуальный старт участнику ' + label + '?')) return;
  const res = await api('/api/judge/individual-start', 'POST', { rider_id: selectedRiderId });
  if (res.ok) { toast('Старт: ' + (res.info && res.info.rider_name || label)); loadRaceStatus(); refreshRiderPanel(); }
  else toast(res.error || 'Ошибка старта', true);
}


let ddIndex = -1;
let ddFiltered = [];

function onSearchInput() { renderDropdown(); document.getElementById('rider-dropdown').classList.add('open'); }
function onSearchFocus() { document.getElementById('rider-search').select(); ddIndex = -1; renderDropdown(); document.getElementById('rider-dropdown').classList.add('open'); }
function onSearchKey(e) {
  const dd = document.getElementById('rider-dropdown');
  const isOpen = dd.classList.contains('open');
  if (e.key === 'ArrowDown') { e.preventDefault(); if (!isOpen) { renderDropdown(); dd.classList.add('open'); } ddIndex = Math.min(ddIndex+1, ddFiltered.length-1); highlightItem(); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); ddIndex = Math.max(ddIndex-1, 0); highlightItem(); }
  else if (e.key === 'Enter') { e.preventDefault(); if (ddIndex >= 0 && ddIndex < ddFiltered.length) selectRider(ddFiltered[ddIndex].id); else if (ddFiltered.length === 1) selectRider(ddFiltered[0].id); }
  else if (e.key === 'Escape') { dd.classList.remove('open'); document.getElementById('rider-search').blur(); }
}
function highlightItem() { document.querySelectorAll('#rider-dropdown .rider-dropdown-item').forEach((el, i) => { el.classList.toggle('active', i === ddIndex); if (i === ddIndex) el.scrollIntoView({ block: 'nearest' }); }); }

function renderDropdown() {
  const query = (document.getElementById('rider-search').value || '').toLowerCase();
  const dd = document.getElementById('rider-dropdown');
  const filterByCat = document.getElementById('search-filter-cat').checked;
  const catId = getCatId();
  ddFiltered = riders.filter(r => {
    if (filterByCat && catId && String(r.category_id) !== String(catId)) return false;
    if (!query) return true;
    return String(r.number).includes(query) || (r.last_name||'').toLowerCase().includes(query) || (r.first_name||'').toLowerCase().includes(query);
  });
  if (!ddFiltered.length) { dd.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim);font-size:12px">Не найдено</div>'; return; }
  dd.innerHTML = ddFiltered.map((r, i) =>
    '<div class="rider-dropdown-item' + (i === ddIndex ? ' active' : '') + '" onclick="selectRider(' + r.id + ')">' +
    '<span class="rdi-num">#' + r.number + '</span><span class="rdi-name">' + (r.last_name||'') + ' ' + (r.first_name||'') + '</span>' +
    (!filterByCat && r.category_name ? '<span style="font-size:9px;color:var(--text-dim);margin-left:auto">' + r.category_name + '</span>' : '') +
    '</div>'
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

function fmtLapMs(ms) { if (ms === null || ms === undefined) return '—'; const totalSec = Math.abs(ms)/1000; const m = Math.floor(totalSec/60); const s = totalSec%60; return String(m).padStart(2,'0') + ':' + s.toFixed(1).padStart(4,'0'); }

let lastLapsHash = '';

function buildLapRowHtml(l) {
  return '<div class="lap-row" id="lap-row-' + l.id + '"><span class="lr-num">' + (l.lap_number === 0 ? '0' : l.lap_number) + '</span>' +
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

async function refreshRiderPanel() {
  if (!selectedRiderId || riderPanelRequestInFlight) return;
  riderPanelRequestInFlight = true;
  try {
    await loadRiderFinishInfo(selectedRiderId);
    await loadRiderLaps(selectedRiderId);
  } finally {
    riderPanelRequestInFlight = false;
  }
}

async function saveLap(lapId) {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; const mm = document.getElementById('lap-mm-'+lapId).value.trim(); const ss = document.getElementById('lap-ss-'+lapId).value.trim(); const minutes = parseInt(mm)||0; const seconds = parseFloat(ss)||0; if (seconds >= 60 || seconds < 0) { toast('Неверное время', true); return; } const lapTimeMs = Math.round((minutes*60+seconds)*1000); const res = await api('/api/judge/lap/'+lapId, 'PUT', { lap_time_ms: lapTimeMs }); if (res.ok) { toast('Круг обновлён'); lastLapsHash=''; await refreshRiderPanel(); } else toast(res.error||'Ошибка', true); }
async function deleteLap(lapId) {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!confirm('Удалить этот круг?')) return; const res = await api('/api/judge/lap/'+lapId, 'DELETE'); if (res.ok) { toast('Круг удалён'); lastLapsHash=''; await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true); }
async function doAddManualLap() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const res = await api('/api/judge/manual-lap', 'POST', { rider_id: selectedRiderId }); if (res.ok) { toast('Круг добавлен'); lastLapsHash=''; await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true); }

function requireRider() { if (!selectedRiderId) { toast('Выберите участника', true); return false; } return true; }

async function doDNF(reason) {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const res = await api('/api/judge/dnf', 'POST', { rider_id: selectedRiderId, reason_code: reason }); if (res.ok) { toast('DNF зафиксирован'); loadLog(); refreshRiderPanel(); } else toast(res.error||'Ошибка', true); }
async function doDSQ() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const reason = document.getElementById('dsq-reason').value.trim(); const res = await api('/api/judge/dsq', 'POST', { rider_id: selectedRiderId, reason }); if (res.ok) { toast('DSQ — дисквалификация'); document.getElementById('dsq-reason').value=''; loadLog(); refreshRiderPanel(); } else toast(res.error||'Ошибка', true); }
async function doTimePenalty() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const seconds = parseFloat(document.getElementById('pen-seconds').value)||0; const reason = document.getElementById('pen-reason').value.trim(); if (seconds <= 0) { toast('Укажите время штрафа', true); return; } const res = await api('/api/judge/time-penalty', 'POST', { rider_id: selectedRiderId, seconds, reason }); if (res.ok) { toast('+'+seconds+' сек штрафа'); document.getElementById('pen-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }
async function doExtraLap() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const laps = parseInt(document.getElementById('extra-laps').value)||1; const reason = document.getElementById('extra-reason').value.trim(); const res = await api('/api/judge/extra-lap', 'POST', { rider_id: selectedRiderId, laps, reason }); if (res.ok) { toast('+'+laps+' штрафной круг'); document.getElementById('extra-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }
async function doWarning() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const reason = document.getElementById('warn-reason').value.trim(); const res = await api('/api/judge/warning', 'POST', { rider_id: selectedRiderId, reason }); if (res.ok) { toast('Предупреждение выдано'); document.getElementById('warn-reason').value=''; loadLog(); } else toast(res.error||'Ошибка', true); }

async function deletePenalty(pid) {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!confirm('Удалить это решение?')) return; const res = await api('/api/judge/penalty/'+pid, 'DELETE'); if (res.ok) { toast('Решение отменено'); loadLog(); } else toast(res.error||'Ошибка', true); }

async function loadLog() {
  try {
    const data = await api('/api/judge/log', 'GET');
    const log = Array.isArray(data) ? data : [];
    const list = document.getElementById('log-list');
    if (!log.length) { list.innerHTML = '<div style="padding:40px 20px;text-align:center;color:var(--text-dim)">Нет записей</div>'; return; }
    const typeLabels = { TIME_PENALTY:'Штраф', EXTRA_LAP:'Доп. круг', WARNING:'Предупр.', DSQ:'DSQ', DNF:'DNF' };
    const groups = {}; const order = [];
    log.forEach(item => {
      const key = String(item.category_id || 0);
      if (!groups[key]) { groups[key] = { name: item.category_name || 'Без категории', items: [] }; order.push(key); }
      groups[key].items.push(item);
    });
    let html = '';
    order.forEach(key => {
      const g = groups[key];
      html += '<div style="padding:5px 12px;font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.08em;color:var(--accent);background:var(--surface2);border-bottom:1px solid var(--border)">' + g.name + '</div>';
      g.items.forEach(item => {
        const timeStr = new Date(item.created_at*1000).toLocaleTimeString('ru-RU');
        html += '<div class="log-item"><div class="li-badge '+item.type+'">'+(typeLabels[item.type]||item.type)+'</div>' +
          '<div class="li-info"><div class="li-rider">#'+item.rider_number+' '+item.last_name+'</div>' +
          '<div class="li-detail">'+(item.reason||item.type)+'</div></div>' +
          '<div class="li-time">'+timeStr+'</div>' +
          '<div class="li-delete" onclick="deletePenalty('+item.id+')" title="Отменить">✕</div></div>';
      });
    });
    list.innerHTML = html;
  } catch(e) {}
}


function updateCategoryTimers() {
  const timersEl = document.getElementById('cat-timers');
  if (!timersEl) return;
  const catId = getCatId();
  const entries = Object.entries(catTimerElapsed);
  if (!entries.length) {
    timersEl.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Нет запущенных категорий</div>';
    return;
  }
  let html = '';
  entries.forEach(([cid, elapsed]) => {
    const isClosed = catTimerClosed[cid] || false;
    const perfRef = catTimerPerf[cid];
    let displayMs = elapsed;
    if (!isClosed && perfRef) displayMs = elapsed + (performance.now() - perfRef);
    const isSelected = String(cid) === String(catId);
    const catInfo = (window._catNameMap || {})[cid] || ('Кат. ' + cid);
    const isSpRun = spIsRunning(cid);
    const color = isClosed ? 'var(--text-dim)' : (isSelected ? 'var(--accent)' : 'var(--green)');
    const label = isClosed ? '✓ ' + catInfo : catInfo;
    html += '<div class="cat-timer-item" style="' + (isSelected ? 'background:var(--accent-glow);border:1px solid rgba(56,189,248,0.3);' : '') +
      'padding:4px 8px;border-radius:4px;display:flex;align-items:center;gap:8px;margin-bottom:3px">' +
      '<span style="font-size:10px;font-weight:700;color:' + color + ';min-width:80px;white-space:nowrap">' + label + '</span>' +
      '<span style="font-family:var(--mono);font-size:16px;font-weight:700;color:' + color + '">' + fmtMs(displayMs) + '</span>' +
      (isClosed ? '<span style="font-size:9px;color:var(--text-dim)">завершена</span>' : '') +
      (isSpRun ? '<span style="font-size:8px;color:var(--yellow);font-weight:700">SP</span>' : '') +
      '</div>';
  });
  timersEl.innerHTML = html;
}

function startGlobalTimerTick() { if (globalTimerRef) return; globalTimerRef = setInterval(updateCategoryTimers, 100); }

async function initJudge() {
  authManager = createAuthManager({
    toast: toast,
    loginButtonId: 'login-btn',
    logoutButtonId: 'logout-btn',
    authHintId: 'auth-hint',
    onAuthChange: function () {
      loadRaceStatus();
      spUpdateUI();
    },
  });

  await authManager.checkAuth();
  await loadRiders();
  loadLog(); loadNotes();
  await loadCategoriesAndRestore();
  const initCat = getCatId();
  if (initCat) {
    const saved = sessionStorage.getItem('sp_interval_' + initCat);
    if (saved) document.getElementById('sp-interval').value = saved;
  }
  const savedMode = sessionStorage.getItem('judge_start_mode');
  if (savedMode === 'individual') setStartMode('individual');
  if (savedMode === 'individual') spUpdateUI();
  startGlobalTimerTick();
  spEnsureCountdownTick();
}

initJudge();
setInterval(loadLog, JUDGE_LOG_POLL_MS);
setInterval(loadRaceStatus, JUDGE_RACE_STATUS_POLL_MS);
setInterval(function() { if (!selectedRiderId) return; const el = document.activeElement; if (el && el.tagName === 'INPUT' && el.closest('#laps-section')) return; refreshRiderPanel(); }, JUDGE_RIDER_PANEL_POLL_MS);

async function loadCategoriesAndRestore() {
  const cats = await api('/api/categories', 'GET');
  const sel = document.getElementById('race-category');
  sel.innerHTML = '<option value="">— Выберите категорию —</option>';
  window._catNameMap = {};
  cats.forEach(c => { const o = document.createElement('option'); o.value = c.id; o.textContent = c.name + ' (' + c.laps + ' кр.)'; sel.appendChild(o); window._catNameMap[String(c.id)] = c.name; });
  const saved = sessionStorage.getItem('judge_cat_id');
  if (saved && sel.querySelector('option[value="'+saved+'"]')) sel.value = saved;
  else if (cats.length === 1) sel.value = cats[0].id;
  loadRaceStatus();
}

async function loadRaceStatus() {
  if (raceStatusRequestInFlight) return;
  raceStatusRequestInFlight = true;
  const catId = getCatId();
  if (catId) sessionStorage.setItem('judge_cat_id', catId);
  try {
    const qs = catId ? '?category_id=' + catId : '';
    const resp = await fetch('/api/state' + qs);
    const data = await resp.json();
    const st = data.status || {};
    const catStates = data.category_states || {};
    if (data.categories) data.categories.forEach(c => { window._catNameMap = window._catNameMap || {}; window._catNameMap[String(c.id)] = c.name; });
    const now = performance.now();

    Object.keys(catTimerElapsed).forEach(cid => {
      if (!(cid in catStates)) {
        delete catTimerElapsed[cid];
        delete catTimerPerf[cid];
        delete catTimerClosed[cid];
      }
    });

    Object.entries(catStates).forEach(([cid, cs]) => { if (cs.elapsed_ms !== null && cs.elapsed_ms !== undefined) { catTimerElapsed[cid] = cs.elapsed_ms; catTimerPerf[cid] = now; catTimerClosed[cid] = cs.closed; } });
    if (!catId) {
      document.getElementById('race-status-bar').style.display = 'none';
      setStateDisabled(document.getElementById('btn-mass-start'), false);
      setStateDisabled(document.getElementById('btn-finish-race'), true);
      setStateDisabled(document.getElementById('btn-finish-race-ind'), true);
      if (authManager) authManager.syncProtectedControls();
      return;
    }
    const racing = st.RACING||0; const finished = st.FINISHED||0; const dnf = (st.DNF||0)+(st.DSQ||0);
    document.getElementById('rs-racing').textContent = racing;
    document.getElementById('rs-finished').textContent = finished;
    document.getElementById('rs-dnf').textContent = dnf;
    document.getElementById('race-status-bar').style.display = 'block';
    const thisCatClosed = data.category_closed === true;
    const thisCatStarted = data.category_started === true;
    currentCategoryClosed = thisCatClosed;
    currentCategoryStarted = thisCatStarted;
    const effectivelyClosed = thisCatClosed;
    const startBtn = document.getElementById('btn-mass-start');
    const finishBtn = document.getElementById('btn-finish-race');
    const finishIndBtn = document.getElementById('btn-finish-race-ind');
    setStateDisabled(startBtn, thisCatStarted || effectivelyClosed);
    setStateDisabled(finishBtn, !thisCatStarted || effectivelyClosed);
    setStateDisabled(finishIndBtn, !thisCatStarted || effectivelyClosed);
    if (effectivelyClosed) startBtn.textContent = 'Категория завершена';
    else if (thisCatStarted) startBtn.textContent = racing > 0 ? 'Гонка идёт' : 'Гонка активна';
    else startBtn.textContent = '▶ Масс-старт';
    const spLaunchBtn = document.getElementById('btn-sp-launch');
    const individualStartBtn = document.getElementById('btn-individual-start');
    const currentProtocolState = catId ? spGetState(catId) : null;
    const hasPendingProtocolEntries = !!(
      catId &&
      (
        (currentProtocolState && Array.isArray(currentProtocolState.planned) && currentProtocolState.planned.some(e => e.status !== 'STARTED')) ||
        ((!currentProtocolState || !Array.isArray(currentProtocolState.planned)) && spEntries.length > 0)
      )
    );
    const canLaunchProtocol = !effectivelyClosed && !spIsRunning(catId) && hasPendingProtocolEntries;

    setStateDisabled(individualStartBtn, effectivelyClosed || !catId);
    setStateDisabled(spLaunchBtn, !canLaunchProtocol || !catId);

    if (effectivelyClosed) spLaunchBtn.textContent = 'Категория завершена';
    else if (thisCatStarted && hasPendingProtocolEntries) spLaunchBtn.textContent = '▶ Продолжить протокол';
    else spLaunchBtn.textContent = '▶ Запустить протокол';
    const finBtn = document.getElementById('btn-finish-race');
    finBtn.textContent = effectivelyClosed ? 'Категория завершена' : '■ Завершить категорию';
    document.getElementById('btn-finish-race-ind').textContent = effectivelyClosed ? 'Категория завершена' : '■ Завершить';
    setSectionStateDisabled(
      '#laps-section [data-auth-required], .actions-grid [data-auth-required], .notes-section [data-auth-required]',
      effectivelyClosed,
      ['btn-mass-start', 'btn-finish-race', 'btn-finish-race-ind', 'btn-sp-launch', 'btn-individual-start']
    );
    if (authManager) authManager.syncProtectedControls();
    if (startMode === 'individual' && catId) await spSyncStatus(catId, false);
  } catch(e) {}
  finally { raceStatusRequestInFlight = false; }
}

function spHasPendingEntries(catId) {
  const st = catId ? spGetState(catId) : null;
  return !!(
    catId &&
    (
      (st && Array.isArray(st.planned) && st.planned.some(e => e.status !== 'STARTED')) ||
      ((!st || !Array.isArray(st.planned)) && spEntries.length > 0)
    )
  );
}

function spComputePausedDelayMs(catId) {
  const st = catId ? spGetState(catId) : null;
  if (!st || !st.running || !Array.isArray(st.planned)) return 0;
  const next = st.planned.find(e => !st.startedSet.has(e.rider_id));
  if (!next || next.planned_time === null || next.planned_time === undefined) return 0;
  return Math.max(0, next.planned_time - Date.now());
}

document.getElementById('race-category').addEventListener('change', function() { loadRaceStatus(); if (startMode === 'individual') spSwitchToCategory(); });
document.getElementById('sp-interval').addEventListener('change', function() { const c = getCatId(); if (c) sessionStorage.setItem('sp_interval_' + c, this.value); spRenderList(); });
document.getElementById('sp-interval').addEventListener('input', function() { const c = getCatId(); if (c) sessionStorage.setItem('sp_interval_' + c, this.value); spRenderList(); });

async function doMassStart() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const startBtn = document.getElementById('btn-mass-start');
  if (startBtn && startBtn.disabled) {
    toast(startBtn.textContent || 'Старт уже недоступен', true);
    return;
  }
  const catId = getCatId();
  if (!catId) { toast('Выберите категорию', true); return; }
  if (!confirm('Запустить масс-старт для выбранной категории?')) return;
  const res = await api('/api/judge/mass-start', 'POST', { category_id: parseInt(catId) });
  if (res.ok) {
    toast('Масс-старт! Участников: ' + (res.info && res.info.riders_started || '?'));
    loadRaceStatus();
  } else toast(res.error || 'Ошибка', true);
}
async function doUnfinishRider() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; if (!requireRider()) return; const r = riders.find(x => x.id === selectedRiderId); const label = r ? '#'+r.number+' '+r.last_name : '#'+selectedRiderId; if (!confirm('Отменить финиш '+label+'?\nУчастник вернётся в статус RACING.')) return; const res = await api('/api/judge/unfinish-rider', 'POST', { rider_id: selectedRiderId }); if (res.ok) { toast('Финиш отменён: '+label); await refreshRiderPanel(); loadRaceStatus(); } else toast(res.error||'Ошибка', true); }
async function doEditFinishTime() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
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

async function addNote() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; const text = document.getElementById('note-text').value.trim(); if (!text) { toast('Введите текст заметки', true); return; } const res = await api('/api/judge/notes', 'POST', { text, rider_id: selectedRiderId||null }); if (res.ok) { toast('Заметка сохранена'); document.getElementById('note-text').value=''; loadNotes(); } else toast(res.error||'Ошибка', true); }
async function deleteNote(nid) {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return; const res = await api('/api/judge/notes/'+nid, 'DELETE'); if (res.ok) loadNotes(); }
async function loadNotes() {
  try {
    const data = await api('/api/judge/notes', 'GET');
    const notes = Array.isArray(data) ? data : [];
    const list = document.getElementById('notes-list');
    if (!notes.length) { list.innerHTML = ''; return; }
    list.innerHTML = notes.map(n => {
      const timeStr = new Date(n.created_at*1000).toLocaleTimeString('ru-RU');
      const rider = n.rider_number ? '#'+n.rider_number+' '+(n.last_name||'')+' - ' : '';
      return '<div style="display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">' +
        '<div style="flex:1;min-width:0"><span style="color:var(--accent);font-weight:600">'+rider+'</span><span style="color:var(--text)">'+n.text+'</span></div>' +
        '<span style="color:var(--text-dim);font-family:var(--mono);font-size:10px;white-space:nowrap">'+timeStr+'</span>' +
        '<button class="note-del" data-nid="'+n.id+'">✕</button></div>';
    }).join('');
    list.querySelectorAll('.note-del').forEach(btn => { btn.addEventListener('click', function() { deleteNote(parseInt(this.dataset.nid)); }); });
  } catch(e) {}
}

async function doFinishRace() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const catId = getCatId();
  if (!catId) { toast('Выберите категорию', true); return; }
  const catName = (window._catNameMap || {})[catId] || catId;
  if (!confirm('Завершить категорию «' + catName + '»?\n* Участники, проехавшие все круги -> FINISHED\n* Остальные -> DNF\n* Таймер категории остановится')) return;
  const res = await api('/api/judge/finish-race', 'POST', { category_id: parseInt(catId) });
  if (res.ok) {
    toast('Категория завершена. Финиш: '+(res.finished||0)+', DNF: '+(res.dnf_count||0));
    if (spIsRunning(catId)) { spClearStateFor(catId); spUpdateUI(); }
    loadRaceStatus(); loadLog();
  } else toast(res.error||'Ошибка', true);
}

async function doResetCategory() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const catId = getCatId();
  if (!catId) { toast('Выберите категорию для сброса', true); return; }
  const catName = (window._catNameMap || {})[catId] || catId;
  if (!confirm('Сбросить категорию «' + catName + '»?\n\nВсе результаты, круги и штрафы этой категории будут удалены.\nУчастники останутся в стартовом листе.\nДругие категории не затрагиваются.')) return;
  const res = await api('/api/judge/reset-category', 'POST', { category_id: parseInt(catId) });
  if (res.ok) {
    toast('Категория «' + (res.category || catName) + '» сброшена: ' + (res.deleted_results || 0) + ' результатов удалено');
    if (spIsRunning(catId)) spClearStateFor(catId);
    spEntries = []; spRenderList();
    delete catTimerElapsed[catId]; delete catTimerPerf[catId]; delete catTimerClosed[catId];
    spUpdateUI(); loadRaceStatus(); loadLog();
  } else toast(res.error || 'Ошибка', true);
}

async function doNewRace() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  if (!confirm('Создать полностью новую гоночную сессию?\nРезультаты ВСЕХ категорий будут архивированы.\n\nДля сброса одной категории используйте «Сбросить категорию».')) return;
  const res = await api('/api/settings/reset-race', 'POST');
  if (res.ok) {
    toast('Новая сессия #'+res.race_id);
    Object.keys(spStates).forEach(cid => spClearStateFor(cid));
    spStopGlobalTick();
    spEntries=[]; spRenderList();
    catTimerElapsed = {}; catTimerPerf = {}; catTimerClosed = {};
    spUpdateUI(); loadRaceStatus(); loadLog();
  } else toast(res.error||'Ошибка', true);
}

function spRemoveEntry(index) {
  if (!requireJudgeEditAccess('Для выполнения действия судьи требуется войти в систему')) return;
  const entry = spEntries[index];
  const catId = getCatId();
  const st = catId ? spGetState(catId) : null;
  if (entry && st && st.startedSet && st.startedSet.has(entry.rider_id)) {
    toast('Уже стартовавшего участника нельзя убрать из протокола', true);
    return;
  }
  spEntries.splice(index, 1);
  spRenderList();
  spSaveToServer();
}

function spRenderList() {
  const list = document.getElementById('sp-list');
  const interval = parseInt(document.getElementById('sp-interval').value) || 30;
  const catId = getCatId();
  const isRunning = spIsRunning(catId);
  const st = catId ? spGetState(catId) : null;
  const startedSet = st ? st.startedSet : new Set();

  if (!catId) {
    list.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim);font-size:11px">Выберите категорию, чтобы собирать очередь индивидуального старта</div>';
    return;
  }

  if (!spEntries.length) {
    list.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-dim);font-size:11px">Протокол пуст - нажмите «Авто» или добавьте участников</div>';
    return;
  }

  list.innerHTML = spEntries.map((e, i) => {
    const offsetSec = i * interval;
    const mm = Math.floor(offsetSec / 60);
    const ss = offsetSec % 60;
    const timeStr = mm > 0 ? (mm + ':' + String(ss).padStart(2, '0')) : (ss + 'с');
    const isStarted = startedSet.has(e.rider_id);
    const isNext = isRunning && !isStarted && i === spFindNextVisualIndex(catId);
    const canEditEntry = !isRunning && !isStarted;
    let cls = 'sp-item';
    if (isStarted) cls += ' sp-started';
    if (isNext) cls += ' sp-active';
    const actionHtml = isStarted
      ? '<span style="color:var(--green);font-size:10px;font-weight:700">OK</span>'
      : '<span class="sp-del" onclick="spRemoveEntry(' + i + ')">X</span>';
    return '<div class="' + cls + '" draggable="' + (canEditEntry ? 'true' : 'false') + '" data-idx="' + i + '"' +
      ' ondragstart="spDragStart(event)" ondragover="spDragOver(event)" ondrop="spDrop(event)" ondragend="spDragEnd(event)">' +
      '<span class="sp-pos">' + (i + 1) + '</span><span class="sp-num">#' + e.rider_number + '</span>' +
      '<span class="sp-name">' + e.last_name + ' ' + e.first_name + '</span>' +
      '<span class="sp-time">+' + timeStr + '</span>' +
      actionHtml +
    '</div>';
  }).join('');
}

function spUpdateUI() {
  const catId = getCatId();
  const isRunning = spIsRunning(catId);
  const launchBtn = document.getElementById('btn-sp-launch');
  const stopBtn = document.getElementById('btn-sp-stop');
  const searchEl = document.getElementById('sp-search');
  const intervalEl = document.getElementById('sp-interval');
  const hasCategory = !!catId;
  const st = catId ? spGetState(catId) : null;
  const hasPendingProtocolEntries = spHasPendingEntries(catId);
  const isPausedWithQueue = !!(st && !st.running && st.pausedDelayMs !== null && hasPendingProtocolEntries);
  const protocolEditable = !isRunning && hasCategory && !currentCategoryClosed && (!currentCategoryStarted || hasPendingProtocolEntries);
  const showCountdown = hasCategory && (isRunning || isPausedWithQueue);

  launchBtn.style.display = isRunning ? 'none' : 'block';
  setStateDisabled(launchBtn, isRunning || !hasCategory || currentCategoryClosed || !hasPendingProtocolEntries);
  stopBtn.style.display = isRunning ? 'block' : 'none';
  document.getElementById('sp-countdown-area').style.display = showCountdown ? 'block' : 'none';
  setStateDisabled(searchEl, !protocolEditable);
  setStateDisabled(intervalEl, !protocolEditable);
  if (showCountdown) spUpdateCountdownDisplay(catId);
}

async function spLaunch() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const catId = getCatId();
  if (!catId) { toast('Выберите категорию', true); return; }

  await loadRaceStatus();

  if (spIsRunning(catId)) {
    toast('Протокол уже запущен', true);
    return;
  }

  if (currentCategoryClosed) {
    toast('Категория завершена', true);
    return;
  }

  const st = spGetState(catId);
  const isResume = currentCategoryStarted;
  const resumeDelayMs = isResume && st && st.pausedDelayMs ? st.pausedDelayMs : 0;
  if (!spEntries.length) { toast('Протокол пуст', true); return; }

  await spSaveToServer();

  const confirmText = (isResume ? 'Продолжить' : 'Запустить') + ' стартовый протокол?'
    + (resumeDelayMs > 0
      ? '\nОчередь продолжится с оставшегося времени.'
      : '\nПервый оставшийся участник стартует сейчас.');
  if (!confirm(confirmText)) return;

  const body = { category_id: parseInt(catId) };
  if (resumeDelayMs > 0) body.resume_delay_ms = resumeDelayMs;
  const res = await api('/api/judge/start-protocol/launch', 'POST', body);
  if (!res.ok) { toast(res.error || 'Ошибка запуска', true); return; }

  if (st) st.pausedDelayMs = null;
  await spSyncStatus(catId, true);
  loadRaceStatus();
  toast(isResume ? 'Протокол продолжен' : 'Протокол запущен');
}

async function spStop() {
  if (!await ensureJudgeAuth('Для выполнения действия судьи требуется войти в систему')) return;
  const catId = getCatId();
  if (!catId) return;
  const pausedDelayMs = spComputePausedDelayMs(catId);
  const res = await api('/api/judge/start-protocol/stop', 'POST', { category_id: parseInt(catId) });
  if (!res.ok) { toast(res.error || 'Ошибка остановки', true); return; }
  spClearStateFor(catId);
  const st = spGetState(catId);
  st.pausedDelayMs = pausedDelayMs;
  await spSyncStatus(catId, true);
  spSaveAllStates();
  spUpdateUI();
  toast('Протокол поставлен на паузу');
}

function spUpdateCountdownDisplay(catId) {
  const st = spStates[catId];
  if (!st || !st.planned) return;
  let nextIdx = -1;
  for (let i = 0; i < st.planned.length; i++) {
    if (!st.startedSet.has(st.planned[i].rider_id)) {
      nextIdx = i;
      break;
    }
  }
  const timerEl = document.getElementById('sp-countdown-timer');
  const infoEl = document.getElementById('sp-next-info');
  if (nextIdx === -1) {
    if (timerEl.textContent !== '00:00') timerEl.textContent = '00:00';
    if (timerEl.className !== 'sp-countdown go') timerEl.className = 'sp-countdown go';
    if (infoEl.dataset.nextKey !== 'done') {
      infoEl.textContent = 'Все стартовали';
      infoEl.dataset.nextKey = 'done';
    }
    return;
  }

  const next = st.planned[nextIdx];
  let remain = 0;
  if (st.running) remain = Math.max(0, (next.planned_time || 0) - Date.now());
  else if (st.pausedDelayMs !== null && st.pausedDelayMs !== undefined) remain = Math.max(0, st.pausedDelayMs);
  else return;

  const sec = remain > 0 ? Math.floor((remain + 999) / 1000) : 0;
  const mm = Math.floor(sec / 60);
  const ss = sec % 60;
  const timerText = String(mm).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
  const timerClass = 'sp-countdown' + (sec <= 3 ? ' go' : '');
  const nextKey = String(next.rider_id) + ':' + String(st.running ? next.planned_time : st.pausedDelayMs);
  if (timerEl.textContent === timerText && timerEl.className === timerClass && infoEl.dataset.nextKey === nextKey) return;
  timerEl.textContent = timerText;
  timerEl.className = timerClass;
  infoEl.dataset.nextKey = nextKey;
  infoEl.innerHTML = 'Следующий: <b>#' + next.rider_number + '</b> ' + next.rider_name;
}