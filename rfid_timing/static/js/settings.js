let _authenticated = false;

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
  const resp = await fetch(url, opts);

  if (resp.status === 401) {
    _authenticated = false;
    updateAuthUI();
    toast('Сессия истекла — войдите заново', true);
    return null;
  }
  return resp;
}

function updateAuthUI() {
  const overlay = document.getElementById('auth-overlay');
  const logoutBtn = document.getElementById('logout-btn');
  const authHint = document.getElementById('auth-hint');

  if (_authenticated) {
    overlay.classList.add('hidden');
    logoutBtn.classList.remove('hidden');
    if (authHint) authHint.classList.add('hidden');
  } else {
    overlay.classList.remove('hidden');
    logoutBtn.classList.add('hidden');
    if (authHint) authHint.classList.remove('hidden');
  }
}

async function checkAuth() {
  try {
    const resp = await fetch('/api/settings/auth-status');
    const data = await resp.json();
    _authenticated = !!data.authenticated;
  } catch (e) {
    _authenticated = false;
  }
  updateAuthUI();
}

async function doLogin() {
  const input = document.getElementById('login-password');
  const errEl = document.getElementById('login-error');
  const password = input.value.trim();

  errEl.textContent = '';

  if (!password) {
    errEl.textContent = 'Введите пароль';
    input.focus();
    return;
  }

  try {
    const resp = await fetch('/api/settings/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await resp.json();

    if (data.ok) {
      _authenticated = true;
      input.value = '';
      updateAuthUI();
      toast('Авторизация успешна');
      loadSettings();
    } else {
      errEl.textContent = data.error || 'Ошибка входа';
      input.select();
    }
  } catch (e) {
    errEl.textContent = 'Ошибка сети';
  }
}

async function doLogout() {
  try {
    await fetch('/api/settings/logout', { method: 'POST' });
  } catch (e) { /* ignore */ }
  _authenticated = false;
  updateAuthUI();
  toast('Вы вышли');
}

function onLoginKeydown(e) {
  if (e.key === 'Enter') doLogin();
}

async function loadSettings() {
  const resp = await api('/api/settings', 'GET');
  if (!resp) return;
  const s = await resp.json();

  document.getElementById('s-reader-ip').value = s.reader_ip || '';
  document.getElementById('s-reader-port').value = s.reader_port || 5084;
  document.getElementById('s-tx-power').value = s.tx_power || 30;
  document.getElementById('s-rssi-window').value = s.rssi_window_sec || 2.0;
  document.getElementById('s-min-lap').value = s.min_lap_time_sec || 120;
  document.getElementById('s-use-emulator').checked = !!s.use_emulator;
  document.getElementById('s-emu-lap').value = s.emulator_min_lap_sec || 15;

  const antennas = s.antennas || [1, 2, 3, 4];
  for (let i = 1; i <= 4; i++) {
    document.getElementById('s-ant-' + i).checked = antennas.includes(i);
  }

  if (s._authenticated !== undefined) {
    _authenticated = !!s._authenticated;
    updateAuthUI();
  }

  loadSysInfo();
}

async function saveSettings() {
  if (!_authenticated) {
    toast('Сначала войдите', true);
    return;
  }

  const antennas = [];
  for (let i = 1; i <= 4; i++) {
    if (document.getElementById('s-ant-' + i).checked) antennas.push(i);
  }

  const body = {
    reader_ip: document.getElementById('s-reader-ip').value.trim(),
    reader_port: parseInt(document.getElementById('s-reader-port').value) || 5084,
    tx_power: parseFloat(document.getElementById('s-tx-power').value) || 30,
    antennas: antennas,
    rssi_window_sec: parseFloat(document.getElementById('s-rssi-window').value) || 2.0,
    min_lap_time_sec: parseFloat(document.getElementById('s-min-lap').value) || 120,
    use_emulator: document.getElementById('s-use-emulator').checked,
    emulator_min_lap_sec: parseFloat(document.getElementById('s-emu-lap').value) || 15,
  };

  const resp = await api('/api/settings/apply', 'POST', body);
  if (!resp) return;
  const data = await resp.json();

  if (data.ok) {
    toast(data.message || 'Настройки применены');
    loadReaderStatus();
  } else {
    const msg = data.errors
      ? 'Ошибки: ' + data.errors.join('; ')
      : (data.error || 'Ошибка');
    toast(msg, true);
  }
}

async function loadReaderStatus() {
  try {
    const resp = await api('/api/settings/reader-status', 'GET');
    if (!resp) return;
    const st = await resp.json();
    const el = document.getElementById('reader-mode-badge');
    if (!el) return;
    if (!st.running) {
      el.className = 'status-badge err';
      el.textContent = 'Остановлен';
    } else if (st.mode === 'emulator') {
      el.className = 'status-badge wait';
      el.textContent = 'Эмулятор';
    } else {
      el.className = 'status-badge ok';
      el.textContent = 'Ридер ' + (st.reader_ip || '');
    }
  } catch (e) { /* ignore */ }
}

async function checkConnection() {
  if (!_authenticated) { toast('Сначала войдите', true); return; }

  const badge = document.getElementById('conn-status');
  badge.className = 'status-badge wait';
  badge.textContent = 'Проверяю…';

  try {
    const resp = await api('/api/settings/check-reader', 'POST');
    if (!resp) { badge.className = 'status-badge err'; badge.textContent = '—'; return; }
    const data = await resp.json();
    if (data.ok) {
      badge.className = 'status-badge ok';
      badge.textContent = data.message || 'Подключён';
      badge.title = data.message || '';
    } else {
      badge.className = 'status-badge err';
      badge.textContent = 'Нет связи';
      badge.title = data.error || '';
      toast(data.error || 'Нет связи', true);
    }
  } catch (e) {
    badge.className = 'status-badge err';
    badge.textContent = 'Ошибка сети';
  }
}

async function backupDB() {
  if (!_authenticated) { toast('Сначала войдите', true); return; }
  try {
    const resp = await api('/api/settings/backup', 'POST');
    if (!resp) return;
    const data = await resp.json();
    if (data.ok) {
      toast('Бэкап создан: ' + data.filename);
    } else {
      toast(data.error || 'Ошибка', true);
    }
  } catch (e) {
    toast('Ошибка создания бэкапа', true);
  }
}

async function resetRace() {
  if (!_authenticated) { toast('Сначала войдите', true); return; }
  if (!confirm('Сбросить текущую гонку? Будет создана новая сессия.\nСтарые данные сохранятся в архиве БД.')) return;
  try {
    const resp = await api('/api/settings/reset-race', 'POST');
    if (!resp) return;
    const data = await resp.json();
    if (data.ok) {
      toast('Новая гоночная сессия: #' + data.race_id);
    } else {
      toast(data.error || 'Ошибка', true);
    }
  } catch (e) {
    toast('Ошибка сброса', true);
  }
}

async function loadSysInfo() {
  try {
    const resp = await api('/api/settings/sys-info', 'GET');
    if (!resp) return;
    const info = await resp.json();
    document.getElementById('si-db').textContent = info.db_size;
    document.getElementById('si-log').textContent = info.log_size;
    document.getElementById('si-bk').textContent = info.backups_count;
    document.getElementById('si-race').textContent = info.race_id || '—';
    document.getElementById('si-riders').textContent = info.riders_count;
  } catch (e) { /* ignore */ }
}

async function init() {
  await checkAuth();
  loadSettings();
  loadReaderStatus();
}

init();