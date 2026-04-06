let authManager = null;
let authReady = false;

function toast(msg, isError) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = 'toast', 2500);
}

async function api(url, method, body) {
  const opts = { method: method || 'GET' };
  if (body !== undefined) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body = JSON.stringify(body);
  }

  const result = await authManager.fetchJson(url, opts);
  if (result.unauthorized) return null;
  return result;
}

function updateModeVisibility() {
  const useEmulator = document.getElementById('s-use-emulator').checked;
  const readerBlock = document.getElementById('reader-settings-block');
  const emulatorBlock = document.getElementById('emulator-settings-block');
  const filterBlock = document.getElementById('filter-settings-block');
  const checkBtn = document.getElementById('btn-check-connection');
  const connBadge = document.getElementById('conn-status');
  const minLapLabel = document.getElementById('s-min-lap-label');
  const readerLabel = document.getElementById('mode-label-reader');
  const emulatorLabel = document.getElementById('mode-label-emulator');
  const modeBadge = document.getElementById('reader-mode-badge');

  if (readerBlock) readerBlock.style.display = useEmulator ? 'none' : 'block';
  if (emulatorBlock) emulatorBlock.style.display = useEmulator ? 'block' : 'none';
  if (filterBlock) filterBlock.style.display = useEmulator ? 'none' : 'grid';
  if (checkBtn) checkBtn.style.display = useEmulator ? 'none' : '';
  if (connBadge) connBadge.style.display = useEmulator ? 'none' : '';
  if (readerLabel) readerLabel.classList.toggle('active', !useEmulator);
  if (emulatorLabel) emulatorLabel.classList.toggle('active', useEmulator);
  if (modeBadge) {
    modeBadge.className = 'status-badge ' + (useEmulator ? 'wait' : 'ok');
    modeBadge.textContent = useEmulator ? 'Эмулятор' : 'Считыватель';
  }
  if (minLapLabel) {
    minLapLabel.textContent = useEmulator ? 'Антидребезг эмулятора (сек)' : 'Антидребезг ридера (сек)';
  }
}

async function loadSettings() {
  const resp = await api('/api/settings', 'GET');
  if (!resp || !resp.data) return;
  const s = resp.data;

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

  updateModeVisibility();
  loadSysInfo();
}

async function saveSettings() {
  if (!await authManager.requireAuth('Для сохранения настроек нужен пароль администратора')) return;

  const antennas = [];
  for (let i = 1; i <= 4; i++) {
    if (document.getElementById('s-ant-' + i).checked) antennas.push(i);
  }

  const body = {
    reader_ip: document.getElementById('s-reader-ip').value.trim(),
    reader_port: parseInt(document.getElementById('s-reader-port').value, 10) || 5084,
    tx_power: parseFloat(document.getElementById('s-tx-power').value) || 30,
    antennas: antennas,
    rssi_window_sec: parseFloat(document.getElementById('s-rssi-window').value) || 2.0,
    min_lap_time_sec: parseFloat(document.getElementById('s-min-lap').value) || 120,
    use_emulator: document.getElementById('s-use-emulator').checked,
    emulator_min_lap_sec: parseFloat(document.getElementById('s-emu-lap').value) || 15,
  };

  const resp = await api('/api/settings/apply', 'POST', body);
  if (!resp || !resp.data) return;
  const data = resp.data;

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
    if (!resp || !resp.data) return;
    const st = resp.data;
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
  } catch (e) {
    // ignore
  }
}

async function checkConnection() {
  if (!await authManager.requireAuth('Для проверки подключения нужен пароль администратора')) return;

  const badge = document.getElementById('conn-status');
  badge.className = 'status-badge wait';
  badge.textContent = 'Проверяю…';

  try {
    const resp = await api('/api/settings/check-reader', 'POST');
    if (!resp || !resp.data) {
      badge.className = 'status-badge err';
      badge.textContent = '—';
      return;
    }

    const data = resp.data;
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
  if (!await authManager.requireAuth('Для резервной копии нужен пароль администратора')) return;

  try {
    const resp = await api('/api/settings/backup', 'POST');
    if (!resp || !resp.data) return;
    const data = resp.data;
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
  if (!await authManager.requireAuth('Для сброса гонки нужен пароль администратора')) return;
   if (!confirm('Сбросить текущую гонку? Будет создана новая сессия.\nСтарые данные сохранятся в архиве БД.')) return;

  try {
    const resp = await api('/api/settings/reset-race', 'POST');
    if (!resp || !resp.data) return;
    const data = resp.data;
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
    if (!resp || !resp.data) return;
    const info = resp.data;
    document.getElementById('si-db').textContent = info.db_size;
    document.getElementById('si-log').textContent = info.log_size;
    document.getElementById('si-bk').textContent = info.backups_count;
    document.getElementById('si-race').textContent = info.race_id || '—';
    document.getElementById('si-riders').textContent = info.riders_count;
  } catch (e) {
    // ignore
  }
}

async function init() {
  authManager = createAuthManager({
    toast: toast,
    authHintId: 'auth-hint',
    logoutButtonId: 'logout-btn',
    onAuthChange: function (authenticated) {
      if (authReady && authenticated) {
        loadSettings();
        loadReaderStatus();
      }
    },
  });

  await authManager.checkAuth();
  authReady = true;
  document.getElementById('s-use-emulator').addEventListener('change', updateModeVisibility);
  loadSettings();
  loadReaderStatus();
}

init();
