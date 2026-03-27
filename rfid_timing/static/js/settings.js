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
  return fetch(url, opts);
}

async function loadSettings() {
  const resp = await api('/api/settings', 'GET');
  const s = await resp.json();

  document.getElementById('s-reader-ip').value = s.reader_ip || '';
  document.getElementById('s-reader-port').value = s.reader_port || 5084;
  document.getElementById('s-tx-power').value = s.tx_power || 30;
  document.getElementById('s-rssi-window').value = s.rssi_window_sec || 2.0;
  document.getElementById('s-min-lap').value = s.min_lap_time_sec || 120;
  document.getElementById('s-use-emulator').checked = !!s.use_emulator;
  document.getElementById('s-emu-lap').value = s.emulator_min_lap_sec || 15;

  const antennas = s.antennas || [1,2,3,4];
  for (let i = 1; i <= 4; i++) {
    document.getElementById('s-ant-' + i).checked = antennas.includes(i);
  }

  loadSysInfo();
}

async function saveSettings() {
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

  const resp = await api('/api/settings', 'PUT', body);
  const data = await resp.json();
  if (data.ok) {
    toast('Настройки сохранены');
  } else {
    toast(data.error || 'Ошибка', true);
  }
}

async function checkConnection() {
  const badge = document.getElementById('conn-status');
  badge.className = 'status-badge wait';
  badge.textContent = 'Проверяю…';

  try {
    const resp = await api('/api/settings/check-reader', 'POST');
    const data = await resp.json();
    if (data.ok) {
      badge.className = 'status-badge ok';
      badge.textContent = 'Подключён';
    } else {
      badge.className = 'status-badge err';
      badge.textContent = data.error || 'Нет связи';
    }
  } catch (e) {
    badge.className = 'status-badge err';
    badge.textContent = 'Ошибка сети';
  }
}

async function backupDB() {
  try {
    const resp = await api('/api/settings/backup', 'POST');
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
  if (!confirm('Сбросить текущую гонку? Будет создана новая сессия.\nСтарые данные сохранятся в архиве БД.')) return;
  try {
    const resp = await api('/api/settings/reset-race', 'POST');
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
    const info = await resp.json();
    document.getElementById('si-db').textContent = info.db_size;
    document.getElementById('si-log').textContent = info.log_size;
    document.getElementById('si-bk').textContent = info.backups_count;
    document.getElementById('si-race').textContent = info.race_id || '—';
    document.getElementById('si-riders').textContent = info.riders_count;
  } catch (e) {}
}

loadSettings();