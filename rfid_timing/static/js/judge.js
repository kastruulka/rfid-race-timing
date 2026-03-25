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

let ddIndex = -1;
let ddFiltered = [];

function onSearchInput() {
  renderDropdown();
  document.getElementById('rider-dropdown').classList.add('open');
}

function onSearchFocus() {
  document.getElementById('rider-search').select();
  ddIndex = -1;
  renderDropdown();
  document.getElementById('rider-dropdown').classList.add('open');
}

function onSearchKey(e) {
  const dd = document.getElementById('rider-dropdown');
  const isOpen = dd.classList.contains('open');
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    if (!isOpen) { renderDropdown(); dd.classList.add('open'); }
    ddIndex = Math.min(ddIndex + 1, ddFiltered.length - 1);
    highlightItem();
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    ddIndex = Math.max(ddIndex - 1, 0);
    highlightItem();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    if (ddIndex >= 0 && ddIndex < ddFiltered.length) {
      selectRider(ddFiltered[ddIndex].id);
    } else if (ddFiltered.length === 1) {
      selectRider(ddFiltered[0].id);
    }
  } else if (e.key === 'Escape') {
    dd.classList.remove('open');
    document.getElementById('rider-search').blur();
  }
}
 
function highlightItem() {
  document.querySelectorAll('.rider-dropdown-item').forEach((el, i) => {
    el.classList.toggle('active', i === ddIndex);
    if (i === ddIndex) el.scrollIntoView({ block: 'nearest' });
  });
}

function renderDropdown() {
  const query = (document.getElementById('rider-search').value || '').toLowerCase();
  const dd = document.getElementById('rider-dropdown');
  ddFiltered = riders.filter(r => {
    if (!query) return true;
    return String(r.number).includes(query) ||
           (r.last_name || '').toLowerCase().includes(query) ||
           (r.first_name || '').toLowerCase().includes(query);
  });

  if (!ddFiltered.length) {
    dd.innerHTML = '<div style="padding:12px 14px;color:var(--text-dim);font-size:12px">Не найдено</div>';
    return;
  }

   dd.innerHTML = ddFiltered.map((r, i) =>
    '<div class="rider-dropdown-item' + (i === ddIndex ? ' active' : '') + '" onclick="selectRider(' + r.id + ')">' +
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
      const ms = data.total_time_ms;
      const m = Math.floor(Math.abs(ms) / 1000 / 60);
      const s = (Math.abs(ms) / 1000) % 60;
      const timeStr = String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
      document.getElementById('current-finish-time').textContent = timeStr;
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

function fmtLapMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}

let lastLapsHash = '';

function buildLapRowHtml(l) {
  return '<div class="lap-row" id="lap-row-' + l.id + '">' +
    '<span class="lr-num">' + (l.lap_number === 0 ? '0' : l.lap_number) + '</span>' +
    '<span class="lr-time">' + fmtLapMs(l.lap_time) + '</span>' +
    '<input id="lap-mm-' + l.id + '" placeholder="М" value="' + Math.floor(Math.abs(l.lap_time || 0) / 1000 / 60) + '">' +
    '<span style="color:var(--text-dim)">:</span>' +
    '<input id="lap-ss-' + l.id + '" placeholder="С.д" style="width:50px" value="' + (((Math.abs(l.lap_time || 0) / 1000) % 60).toFixed(1)) + '">' +
    '<span class="lr-btn save" onclick="saveLap(' + l.id + ')">✓</span>' +
    '<span class="lr-btn del" onclick="deleteLap(' + l.id + ')">✕</span>' +
  '</div>';
}

async function loadRiderLaps(riderId) {
  try {
    const data = await api('/api/judge/rider-laps/' + riderId, 'GET');
    const laps = Array.isArray(data) ? data : [];
    const listEl = document.getElementById('laps-list');

    if (!laps.length) {
      lastLapsHash = '';
      listEl.innerHTML =
        '<div style="font-size:11px;color:var(--text-dim);padding:4px 0">Нет зафиксированных кругов</div>';
      return;
    }

    const newHash = laps.map(l => l.id + ':' + l.lap_number + ':' + l.lap_time).join('|');
    if (newHash === lastLapsHash) return;

    // Если пользователь сейчас редактирует инпут круга — не перерисовываем,
    // только добавляем новые строки
    const focused = document.activeElement;
    if (focused && focused.id && focused.id.startsWith('lap-')) {
      const existingIds = new Set();
      listEl.querySelectorAll('.lap-row').forEach(row => {
        existingIds.add(parseInt(row.id.replace('lap-row-', '')));
      });
      laps.forEach(l => {
        if (!existingIds.has(l.id)) {
          listEl.insertAdjacentHTML('beforeend', buildLapRowHtml(l));
        }
      });
      lastLapsHash = newHash;
      return;
    }

    // Фокуса нет — полная перерисовка
    lastLapsHash = newHash;
    listEl.innerHTML = laps.map(l => buildLapRowHtml(l)).join('');
  } catch(e) {}
}

async function refreshRiderPanel() {
  if (selectedRiderId) {
    await loadRiderFinishInfo(selectedRiderId);
    await loadRiderLaps(selectedRiderId);
  }
}

async function saveLap(lapId) {
  const mm = document.getElementById('lap-mm-' + lapId).value.trim();
  const ss = document.getElementById('lap-ss-' + lapId).value.trim();
  const minutes = parseInt(mm) || 0;
  const seconds = parseFloat(ss) || 0;
  if (seconds >= 60 || seconds < 0) { toast('Неверное время', true); return; }
  const lapTimeMs = Math.round((minutes * 60 + seconds) * 1000);

  const res = await api('/api/judge/lap/' + lapId, 'PUT', { lap_time_ms: lapTimeMs });
  if (res.ok) {
    toast('Круг обновлён');
    lastLapsHash = ''; // сбросить чтобы принудительно перерисовать
    await refreshRiderPanel();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function deleteLap(lapId) {
  if (!confirm('Удалить этот круг?')) return;
  const res = await api('/api/judge/lap/' + lapId, 'DELETE');
  if (res.ok) {
    toast('Круг удалён');
    lastLapsHash = '';
    await refreshRiderPanel();
    loadRaceStatus();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

async function doAddManualLap() {
  if (!requireRider()) return;
  const res = await api('/api/judge/manual-lap', 'POST', { rider_id: selectedRiderId });
  if (res.ok) {
    toast('Круг добавлен');
    lastLapsHash = '';
    await refreshRiderPanel();
    loadRaceStatus();
  } else {
    toast(res.error || 'Ошибка', true);
  }
}

function requireRider() {
  if (!selectedRiderId) { toast('Выберите участника', true); return false; }
  return true;
}

async function doDNF(reason) {
  if (!requireRider()) return;
  const res = await api('/api/judge/dnf', 'POST', {
    rider_id: selectedRiderId, reason_code: reason
  });
  if (res.ok) { toast('DNF зафиксирован'); loadLog(); refreshRiderPanel(); }
  else toast(res.error || 'Ошибка', true);
}

async function doDSQ() {
  if (!requireRider()) return;
  const reason = document.getElementById('dsq-reason').value.trim();
  const res = await api('/api/judge/dsq', 'POST', {
    rider_id: selectedRiderId, reason: reason
  });
  if (res.ok) { toast('DSQ — дисквалификация'); document.getElementById('dsq-reason').value = ''; loadLog(); refreshRiderPanel(); }
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
setInterval(function() {
  if (!selectedRiderId) return;
  // Не обновляем если пользователь редактирует круги или финиш
  const el = document.activeElement;
  if (el && el.tagName === 'INPUT' && el.closest('#laps-section')) return;
  refreshRiderPanel();
}, 3000);

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

    document.querySelectorAll('.actions-grid .btn, #laps-section .btn').forEach(b => {
      b.disabled = raceClosed;
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
    await refreshRiderPanel();
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
    await refreshRiderPanel();
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
      return '<div style="display:flex;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px">' +
        '<div style="flex:1;min-width:0"><span style="color:var(--accent);font-weight:600">' + rider + '</span>' +
        '<span style="color:var(--text)">' + n.text + '</span></div>' +
        '<span style="color:var(--text-dim);font-family:var(--mono);font-size:10px;white-space:nowrap">' + timeStr + '</span>' +
        '<button class="note-del" data-nid="' + n.id + '">✕</button>' +
      '</div>';
    }).join('');

    list.querySelectorAll('.note-del').forEach(btn => {
      btn.addEventListener('click', function() { deleteNote(parseInt(this.dataset.nid)); });
    });
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