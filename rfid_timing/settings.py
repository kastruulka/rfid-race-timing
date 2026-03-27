import json
import os
import shutil
import time
from flask import render_template_string, jsonify, request, send_file
from .database import Database


class ConfigState:

    DEFAULTS = {
        "reader_ip": "169.254.1.1",
        "reader_port": 5084,
        "tx_power": 30.0,
        "antennas": [1, 2, 3, 4],
        "rssi_window_sec": 2.0,
        "min_lap_time_sec": 120.0,
        "use_emulator": True,
        "emulator_min_lap_sec": 15.0,
    }

    def __init__(self, filepath: str = "data/settings.json"):
        self._filepath = filepath
        self._data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> dict:
        return dict(self._data)

    def update(self, **kw):
        allowed = set(self.DEFAULTS.keys())
        for k, v in kw.items():
            if k in allowed:
                self._data[k] = v
        self._save()

    def __getitem__(self, key):
        return self._data.get(key, self.DEFAULTS.get(key))



SETTINGS_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Настройки</title>
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
      --radius: 8px;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body { font-family: var(--sans); background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }

    .topnav {
      display: flex; align-items: center; gap: 24px;
      padding: 0 24px; height: 44px;
      background: var(--surface); border-bottom: 1px solid var(--border);
    }
    .topnav-brand { font-weight: 900; font-size: 14px; text-transform: uppercase; letter-spacing: -0.02em; }
    .topnav-brand span { color: var(--accent); }
    .topnav a {
      color: var(--text-dim); text-decoration: none; font-size: 12px;
      font-weight: 700; padding: 12px 0; border-bottom: 2px solid transparent;
      transition: color .15s, border-color .15s;
    }
    .topnav a:hover { color: var(--text); }
    .topnav a.active { color: var(--accent); border-bottom-color: var(--accent); }

    .page-content {
      height: calc(100vh - 44px);
      display: flex; flex-direction: column;
      max-width: 960px; margin: 0 auto; padding: 12px 20px 10px;
    }
    .page-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 10px;
    }
    .page-title {
      font-size: 16px; font-weight: 900; text-transform: uppercase;
      letter-spacing: -0.02em;
    }
    .page-title span { color: var(--accent); }

    .main-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      grid-template-rows: auto auto;
      gap: 10px;
      align-content: start;
    }

    .card {
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 12px 14px;
    }
    .card-title {
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--text-dim);
      margin-bottom: 8px; padding-bottom: 5px;
      border-bottom: 1px solid var(--border);
    }

    .form-row { margin-bottom: 6px; }
    .form-row:last-child { margin-bottom: 0; }
    .form-row label {
      display: block; font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-dim); margin-bottom: 2px;
    }
    .form-row input, .form-row select {
      width: 100%; padding: 5px 10px; font-family: var(--sans); font-size: 12px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 5px;
      color: var(--text); outline: none;
    }
    .form-row input:focus { border-color: var(--accent); }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
    .form-hint { font-size: 9px; color: var(--text-dim); margin-top: 1px; line-height: 1.2; }

    .checkbox-row {
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .cb-item {
      display: flex; align-items: center; gap: 4px;
      font-size: 11px; font-weight: 600; cursor: pointer;
    }
    .cb-item input[type="checkbox"] {
      width: 14px; height: 14px; accent-color: var(--accent); cursor: pointer;
    }

    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 4px;
      padding: 6px 12px; font-family: var(--sans); font-size: 11px; font-weight: 700;
      border: 1px solid var(--border); border-radius: 6px;
      background: var(--surface2); color: var(--text); cursor: pointer;
      transition: background .15s, border-color .15s;
    }
    .btn:hover { background: var(--surface); border-color: var(--accent); }
    .btn-accent { background: var(--accent); color: var(--bg); border-color: var(--accent); }
    .btn-accent:hover { background: #2daae8; }
    .btn-green { background: var(--green); color: #fff; border-color: var(--green); }
    .btn-green:hover { background: #1eab54; }
    .btn-danger { background: transparent; color: var(--red); border-color: var(--red); }
    .btn-danger:hover { background: var(--red-glow); }

    .btn-row { display: flex; gap: 8px; flex-wrap: wrap; }

    .status-badge {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 4px 10px; border-radius: 5px; font-size: 10px; font-weight: 700;
    }
    .status-badge.ok { background: var(--green-glow); color: var(--green); }
    .status-badge.err { background: var(--red-glow); color: var(--red); }
    .status-badge.wait { background: var(--accent-glow); color: var(--accent); }

    .toast {
      position: fixed; bottom: 16px; right: 16px; z-index: 200;
      padding: 10px 16px; border-radius: 6px; font-size: 12px; font-weight: 600;
      background: var(--green); color: #fff; opacity: 0;
      transform: translateY(12px); transition: opacity .25s, transform .25s;
    }
    .toast.show { opacity: 1; transform: translateY(0); }
    .toast.error { background: var(--red); }

    .info-row {
      display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px;
    }
    .info-item { font-size: 11px; color: var(--text-dim); }
    .info-item b { color: var(--text); font-family: var(--mono); font-size: 11px; }

    .conn-row {
      display: flex; align-items: center; gap: 8px; margin-top: 4px;
    }

    .card-system { grid-column: 1 / -1; }

    .bottom-bar {
      display: flex; justify-content: flex-end; padding-top: 10px;
    }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  </style>
</head>
<body>

  <nav class="topnav">
    <div class="topnav-brand"><span>RFID</span> Хронометраж</div>
    <a href="/start-list">Стартовый лист</a>
    <a href="/">Хронометраж</a>
    <a href="/protocol">Протокол</a>
    <a href="/settings" class="active">Настройки</a>
    <a href="/judge">Судья</a>
  </nav>

  <div class="page-content">
    <div class="page-header">
      <div class="page-title"><span>Настройки</span> системы</div>
      <button class="btn btn-accent" onclick="saveSettings()" style="padding:8px 28px; font-size:12px">
        Сохранить настройки
      </button>
    </div>

    <div class="main-grid">
      <div class="card">
        <div class="card-title">RFID-ридер</div>
        <div class="form-grid">
          <div class="form-row">
            <label>IP-адрес ридера</label>
            <input type="text" id="s-reader-ip" placeholder="169.254.1.1">
          </div>
          <div class="form-row">
            <label>Порт</label>
            <input type="number" id="s-reader-port" placeholder="5084">
          </div>
        </div>
        <div class="form-row">
          <label>TX Power (dBm)</label>
          <input type="number" id="s-tx-power" step="0.5" min="0" max="32.5" placeholder="30.0">
          <div class="form-hint">Рекомендуется 27–31 dBm</div>
        </div>
        <div class="form-row">
          <label>Активные антенны</label>
          <div class="checkbox-row">
            <label class="cb-item"><input type="checkbox" id="s-ant-1" value="1"> 1</label>
            <label class="cb-item"><input type="checkbox" id="s-ant-2" value="2"> 2</label>
            <label class="cb-item"><input type="checkbox" id="s-ant-3" value="3"> 3</label>
            <label class="cb-item"><input type="checkbox" id="s-ant-4" value="4"> 4</label>
          </div>
        </div>
        <div class="conn-row">
          <button class="btn" onclick="checkConnection()">Проверить подключение</button>
          <span class="status-badge wait" id="conn-status">Не проверено</span>
        </div>
      </div>

      <div class="card">
        <div class="card-title">Параметры фильтрации</div>
        <div class="form-grid">
          <div class="form-row">
            <label>RSSI Window (сек)</label>
            <input type="number" id="s-rssi-window" step="0.1" min="0.5" max="10">
            <div class="form-hint">Окно сбора считываний метки (по умолч. 2.0)</div>
          </div>
          <div class="form-row">
            <label>MIN_LAP_TIME (сек)</label>
            <input type="number" id="s-min-lap" step="1" min="5" max="3600">
            <div class="form-hint">Антидребезг между проездами</div>
          </div>
        </div>
        <div style="margin-top:4px; padding-top:6px; border-top:1px solid var(--border);">
          <div style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-dim); margin-bottom:6px;">Эмулятор</div>
          <div class="form-grid">
            <div class="form-row">
              <label>Режим</label>
              <div class="checkbox-row" style="padding-top:2px">
                <label class="cb-item"><input type="checkbox" id="s-use-emulator"> Включён</label>
              </div>
              <div class="form-hint">Ридер не подключается при эмуляции</div>
            </div>
            <div class="form-row">
              <label>Мин. время круга (сек)</label>
              <input type="number" id="s-emu-lap" step="1" min="5">
            </div>
          </div>
        </div>
      </div>

      <div class="card card-system" style="display:flex; flex-direction:row; align-items:center; justify-content:space-between; gap:14px;">
        <div style="display:flex; align-items:center; gap:6px;">
          <span style="font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:var(--text-dim);">Система</span>
        </div>
        <div class="info-row" style="margin-bottom:0; flex:1;">
          <div class="info-item">БД: <b id="si-db">—</b></div>
          <div class="info-item">Лог: <b id="si-log">—</b></div>
          <div class="info-item">Бэкапы: <b id="si-bk">—</b></div>
          <div class="info-item">Race: <b id="si-race">—</b></div>
          <div class="info-item">Участников: <b id="si-riders">—</b></div>
        </div>
        <div class="btn-row">
          <button class="btn btn-green" onclick="backupDB()">Бэкап БД</button>
          <button class="btn btn-danger" onclick="resetRace()">Сбросить гонку</button>
        </div>
      </div>
    </div>
  </div>

  <div class="toast" id="toast"></div>

<script>
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
</script>
</body>
</html>
"""


def register_settings(app, db: Database, config_state: ConfigState):

    @app.route("/settings")
    def settings_page():
        return render_template_string(SETTINGS_HTML)

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        return jsonify(config_state.get_all())

    @app.route("/api/settings", methods=["PUT"])
    def api_settings_put():
        data = request.get_json(force=True)
        config_state.update(**data)
        return jsonify({"ok": True})

    @app.route("/api/settings/check-reader", methods=["POST"])
    def api_check_reader():
        ip = config_state["reader_ip"]
        port = config_state["reader_port"]
        if config_state["use_emulator"]:
            return jsonify({"ok": True,
                            "message": "Режим эмулятора — ридер не нужен"})
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, int(port)))
            s.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False,
                            "error": f"Нет связи с {ip}:{port} — {e}"})

    @app.route("/api/settings/backup", methods=["POST"])
    def api_backup():
        try:
            db_path = db._db_path
            os.makedirs("backups", exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup_name = f"race_{ts}.db"
            backup_path = os.path.join("backups", backup_name)
            shutil.copy2(db_path, backup_path)
            return jsonify({"ok": True, "filename": backup_name})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/api/settings/reset-race", methods=["POST"])
    def api_reset_race():
        try:
            race_id = db.new_race(label="manual_reset")
            return jsonify({"ok": True, "race_id": race_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/api/settings/sys-info", methods=["GET"])
    def api_sys_info():
        def file_size(path):
            try:
                size = os.path.getsize(path)
                if size < 1024:
                    return f"{size} B"
                elif size < 1024 * 1024:
                    return f"{size / 1024:.1f} KB"
                else:
                    return f"{size / 1024 / 1024:.1f} MB"
            except Exception:
                return "—"

        backups_count = 0
        if os.path.isdir("backups"):
            backups_count = len([f for f in os.listdir("backups")
                                 if f.endswith(".db")])

        riders = db.get_riders()

        return jsonify({
            "db_size": file_size(db._db_path),
            "log_size": file_size("data/raw_log.csv"),
            "backups_count": backups_count,
            "race_id": db.get_current_race_id(),
            "riders_count": len(riders),
        })