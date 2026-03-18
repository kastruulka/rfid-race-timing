from flask import Flask, render_template_string, jsonify, request

from .event_store import EventStore
from .database import Database
from .race_engine import RaceEngine


TIMER_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Хронометраж</title>
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
      --mono: 'JetBrains Mono', monospace;
      --sans: 'Montserrat', system-ui, sans-serif;
      --radius: 10px;
    }

    * { margin: 0; padding: 0; box-sizing: border-box; }

    body {
      font-family: var(--sans);
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
    }

    /* ── Header ── */
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }
    .header-title {
      font-weight: 900;
      font-size: 18px;
      letter-spacing: -0.02em;
      text-transform: uppercase;
    }
    .header-title span { color: var(--accent); }

    .reader-status {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-dim);
    }
    .status-dot {
      width: 10px; height: 10px;
      border-radius: 50%;
      background: var(--green);
      box-shadow: 0 0 8px var(--green);
      animation: pulse-dot 2s infinite;
    }
    @keyframes pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }

    /* ── Main timer ── */
    .timer-bar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 32px;
      padding: 20px 24px;
      background: linear-gradient(180deg, var(--surface2) 0%, var(--bg) 100%);
      border-bottom: 1px solid var(--border);
    }
    .main-clock {
      font-family: var(--mono);
      font-size: 56px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: var(--accent);
      text-shadow: 0 0 30px var(--accent-glow);
      min-width: 320px;
      text-align: center;
    }
    .stat-badges {
      display: flex;
      gap: 12px;
    }
    .badge {
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 8px 18px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      min-width: 80px;
    }
    .badge-num {
      font-family: var(--mono);
      font-size: 28px;
      font-weight: 700;
      line-height: 1;
    }
    .badge-label {
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      margin-top: 4px;
    }
    .badge.racing .badge-num { color: var(--accent); }
    .badge.finished .badge-num { color: var(--green); }
    .badge.dnf .badge-num { color: var(--red); }

    /* ── Layout ── */
    .main-grid {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 0;
      height: calc(100vh - 160px);
    }

    /* ── Feed (left) ── */
    .feed-panel {
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .panel-header {
      padding: 14px 18px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    .feed-list {
      flex: 1;
      overflow-y: auto;
      padding: 4px 0;
    }
    .feed-item {
      display: grid;
      grid-template-columns: 54px 1fr auto;
      align-items: center;
      gap: 12px;
      padding: 10px 18px;
      border-bottom: 1px solid rgba(42, 53, 72, 0.5);
      animation: feed-in 0.3s ease-out;
    }
    @keyframes feed-in {
      from { opacity: 0; transform: translateX(-20px); }
      to { opacity: 1; transform: translateX(0); }
    }
    .feed-number {
      font-family: var(--mono);
      font-size: 20px;
      font-weight: 700;
      color: var(--accent);
      text-align: center;
    }
    .feed-info {
      min-width: 0;
    }
    .feed-name {
      font-weight: 600;
      font-size: 14px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .feed-detail {
      font-size: 11px;
      color: var(--text-dim);
      margin-top: 2px;
    }
    .feed-time {
      font-family: var(--mono);
      font-size: 13px;
      font-weight: 700;
      color: var(--green);
      text-align: right;
      white-space: nowrap;
    }
    .feed-item.finish-item {
      background: var(--green-glow);
    }
    .feed-item.finish-item .feed-time {
      color: var(--green);
      font-size: 14px;
    }
    .feed-item.warmup .feed-detail { color: var(--yellow); }

    /* ── Results table (right) ── */
    .results-panel {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .results-scroll {
      flex: 1;
      overflow-y: auto;
    }
    .results-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    .results-table thead {
      position: sticky;
      top: 0;
      z-index: 2;
    }
    .results-table th {
      padding: 10px 14px;
      text-align: left;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--text-dim);
      background: var(--surface);
      border-bottom: 2px solid var(--border);
    }
    .results-table th.num { text-align: center; width: 60px; }
    .results-table th.time { text-align: right; }

    .results-table td {
      padding: 10px 14px;
      border-bottom: 1px solid rgba(42, 53, 72, 0.4);
      vertical-align: middle;
    }
    .results-table tr:hover { background: rgba(56, 189, 248, 0.04); }
    .results-table .col-pos { text-align: center; font-weight: 700; color: var(--text-dim); width: 44px; }
    .results-table .col-num {
      text-align: center;
      font-family: var(--mono);
      font-weight: 700;
      font-size: 16px;
      color: var(--accent);
    }
    .results-table .col-name { font-weight: 600; }
    .results-table .col-club { color: var(--text-dim); font-size: 13px; }
    .results-table .col-laps {
      font-family: var(--mono);
      text-align: center;
    }
    .results-table .col-time {
      font-family: var(--mono);
      font-weight: 700;
      text-align: right;
      white-space: nowrap;
    }
    .results-table .col-gap {
      font-family: var(--mono);
      font-size: 13px;
      text-align: right;
      color: var(--text-dim);
    }
    .results-table .col-status {
      text-align: center;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    .status-tag {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
    }
    .status-RACING  { background: var(--accent-glow); color: var(--accent); }
    .status-FINISHED { background: var(--green-glow); color: var(--green); }
    .status-DNF     { background: var(--red-glow); color: var(--red); }
    .status-DSQ     { background: var(--red-glow); color: var(--red); }
    .status-DNS     { background: rgba(100,116,139,0.15); color: var(--text-dim); }

    .col-lastlap {
      font-family: var(--mono);
      font-size: 13px;
      text-align: right;
      color: var(--text-dim);
    }

    /* ── Controls bar ── */
    .controls-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 18px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
      gap: 12px;
    }
    .controls-group {
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .btn {
      font-family: var(--sans);
      font-size: 12px;
      font-weight: 700;
      padding: 7px 16px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface2);
      color: var(--text);
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      transition: all 0.15s;
    }
    .btn:hover { border-color: var(--accent); background: var(--accent-glow); }
    .btn-danger { border-color: rgba(239,68,68,0.3); }
    .btn-danger:hover { border-color: var(--red); background: var(--red-glow); color: var(--red); }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    /* ── Responsive ── */
    @media (max-width: 900px) {
      .main-grid { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
      .feed-panel { border-right: none; border-bottom: 1px solid var(--border); }
      .main-clock { font-size: 36px; min-width: auto; }
      .timer-bar { gap: 16px; flex-wrap: wrap; }
    }
  </style>
</head>
<body>

  <!-- Header -->
  <div class="header">
    <div class="header-title"><span>RFID</span> Хронометраж</div>
    <div class="reader-status">
      <div class="status-dot" id="status-dot"></div>
      <span id="reader-label">{{ reader_ip }} / Антенны: {{ antennas }}</span>
    </div>
  </div>

  <!-- Timer bar -->
  <div class="timer-bar">
    <div class="main-clock" id="main-clock">00:00:00</div>
    <div class="stat-badges">
      <div class="badge racing">
        <div class="badge-num" id="cnt-racing">0</div>
        <div class="badge-label">В гонке</div>
      </div>
      <div class="badge finished">
        <div class="badge-num" id="cnt-finished">0</div>
        <div class="badge-label">Финиш</div>
      </div>
      <div class="badge dnf">
        <div class="badge-num" id="cnt-dnf">0</div>
        <div class="badge-label">DNF</div>
      </div>
    </div>
  </div>

  <!-- Main content -->
  <div class="main-grid">

    <!-- Left: live feed -->
    <div class="feed-panel">
      <div class="panel-header">Лента проездов</div>
      <div class="feed-list" id="feed-list"></div>
    </div>

    <!-- Right: results table -->
    <div class="results-panel">
      <div class="controls-bar">
        <div class="controls-group">
          <select id="category-select" class="btn" style="min-width:140px;">
            <option value="">Все категории</option>
          </select>
        </div>
        <div class="controls-group" id="action-buttons">
        </div>
      </div>
      <div class="results-scroll">
        <table class="results-table">
          <thead>
            <tr>
              <th class="num">#</th>
              <th class="num">Номер</th>
              <th>Участник</th>
              <th>Команда</th>
              <th class="num">Круги</th>
              <th class="time">Посл. круг</th>
              <th class="time">Общее время</th>
              <th class="time">Отстав.</th>
              <th class="num">Статус</th>
            </tr>
          </thead>
          <tbody id="results-body"></tbody>
        </table>
      </div>
    </div>

  </div>

<script>
// ─── State ───
let raceStartTime = null;
let clockInterval = null;

function fmtMs(ms) {
  if (!ms && ms !== 0) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${s.toFixed(1).padStart(4,'0')}`;
  return `${String(m).padStart(2,'0')}:${s.toFixed(1).padStart(4,'0')}`;
}

function fmtClock(ms) {
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

function updateClock() {
  if (!raceStartTime) return;
  const elapsed = Date.now() - raceStartTime;
  document.getElementById('main-clock').textContent = fmtClock(elapsed);
}

// ─── Fetch state ───
async function fetchState() {
  try {
    const resp = await fetch('/api/state');
    const data = await resp.json();
    updateFeed(data.feed);
    updateResults(data.results);
    updateCounters(data.status);
    updateCategories(data.categories);

    if (data.start_time && !raceStartTime) {
      raceStartTime = data.start_time;
      if (!clockInterval) clockInterval = setInterval(updateClock, 200);
    }
  } catch (e) {
    console.error('Fetch error', e);
  }
}

// ─── Feed ───
function updateFeed(feed) {
  const list = document.getElementById('feed-list');
  const html = feed.map(item => {
    const isFinish = item.status === 'FINISHED';
    const isWarmup = item.lap_number === 0;
    let cls = 'feed-item';
    if (isFinish) cls += ' finish-item';
    if (isWarmup) cls += ' warmup';

    const lapLabel = isWarmup ? 'разгонный' :
      (isFinish ? 'ФИНИШ' : `круг ${item.lap_number}/${item.laps_required}`);

    return `
      <div class="${cls}">
        <div class="feed-number">${item.rider_number}</div>
        <div class="feed-info">
          <div class="feed-name">${item.rider_name}</div>
          <div class="feed-detail">${lapLabel} · ${item.time_str}</div>
        </div>
        <div class="feed-time">${fmtMs(item.lap_time)}</div>
      </div>`;
  }).join('');
  list.innerHTML = html;
}

// ─── Results ───
function updateResults(results) {
  const tbody = document.getElementById('results-body');
  let html = '';
  let leaderTime = null;

  results.forEach((r, i) => {
    const pos = r.status === 'FINISHED' ? (i + 1) : '—';
    if (r.status === 'FINISHED' && leaderTime === null) leaderTime = r.total_time;

    const gap = (r.status === 'FINISHED' && leaderTime !== null && r.total_time !== leaderTime)
      ? '+' + fmtMs(r.total_time - leaderTime)
      : '';

    html += `<tr>
      <td class="col-pos">${pos}</td>
      <td class="col-num">${r.number}</td>
      <td class="col-name">${r.name}</td>
      <td class="col-club">${r.club || ''}</td>
      <td class="col-laps">${r.laps_done}/${r.laps_required}</td>
      <td class="col-lastlap">${fmtMs(r.last_lap_time)}</td>
      <td class="col-time">${fmtMs(r.total_time)}</td>
      <td class="col-gap">${gap}</td>
      <td class="col-status"><span class="status-tag status-${r.status}">${r.status}</span></td>
    </tr>`;
  });

  tbody.innerHTML = html;
}

// ─── Counters ───
function updateCounters(status) {
  document.getElementById('cnt-racing').textContent = status.RACING || 0;
  document.getElementById('cnt-finished').textContent = status.FINISHED || 0;
  document.getElementById('cnt-dnf').textContent = (status.DNF || 0) + (status.DSQ || 0);
}

// ─── Categories dropdown ───
let catsLoaded = false;
function updateCategories(cats) {
  if (catsLoaded || !cats || cats.length === 0) return;
  const sel = document.getElementById('category-select');
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(opt);
  });
  catsLoaded = true;
}

// ─── Init ───
fetchState();
setInterval(fetchState, 1000);
</script>
</body>
</html>
"""


def create_app(event_store: EventStore, reader_ip: str,
               antennas: set[int],
               db: Database = None,
               engine: RaceEngine = None) -> Flask:

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            TIMER_HTML,
            reader_ip=reader_ip,
            antennas=", ".join(str(a) for a in sorted(antennas)),
        )

    @app.route("/api/state")
    def api_state():
        """
        Возвращает всё, что нужно фронтенду:
        - feed: последние проезды (из event_store + данные из БД)
        - results: таблица результатов
        - status: счётчики по статусам
        - categories: список категорий
        - start_time: время старта (мс, для таймера на фронтенде)
        """
        if not db or not engine:
            return jsonify({
                "feed": [],
                "results": [],
                "status": {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0},
                "categories": [],
                "start_time": None,
            })

        categories = db.get_categories()
        cat_id = request.args.get("category_id", type=int)

        start_time_ms = None
        for cat in categories:
            results = db.get_results_by_category(cat["id"])
            for r in results:
                if r.get("start_time"):
                    st = r["start_time"]
                    if st < 1e12:
                        st = st * 1000
                    if start_time_ms is None or st < start_time_ms:
                        start_time_ms = st

        all_results = []
        target_cats = [c for c in categories if c["id"] == cat_id] \
                      if cat_id else categories

        for cat in target_cats:
            cat_results = db.get_results_by_category(cat["id"])
            for r in cat_results:
                laps = db.get_laps(r["id"])
                laps_done = sum(1 for l in laps if l["lap_number"] > 0)
                last = laps[-1] if laps else None

                total_time = None
                if r.get("finish_time") and r.get("start_time"):
                    total_time = r["finish_time"] - r["start_time"]
                elif last and r.get("start_time"):
                    total_time = last["timestamp"] - r["start_time"]

                all_results.append({
                    "rider_id": r["rider_id"],
                    "number": r["number"],
                    "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                    "club": r.get("club", ""),
                    "city": r.get("city", ""),
                    "status": r["status"],
                    "laps_done": laps_done,
                    "laps_required": cat["laps"],
                    "total_time": total_time,
                    "last_lap_time": last["lap_time"] if last else None,
                    "finish_time": r.get("finish_time"),
                })

        def sort_key(r):
            if r["status"] == "FINISHED":
                return (0, r["total_time"] or 0)
            elif r["status"] == "RACING":
                return (1, -r["laps_done"], r["total_time"] or 0)
            elif r["status"] == "DNF":
                return (2, 0)
            elif r["status"] == "DSQ":
                return (3, 0)
            else:
                return (4, 0)

        all_results.sort(key=sort_key)

        status = engine.get_race_status(cat_id)

        feed = []
        events = event_store.get_events()
        for ev in events[:50]:  # последние 50
            rider = db.get_rider_by_epc(ev.epc)
            if not rider:
                continue

            result = db.get_result_by_rider(rider["id"])
            cat = db.get_category(rider["category_id"]) if rider.get("category_id") else None

            laps = db.get_laps(result["id"]) if result else []
            matched_lap = None
            for l in reversed(laps):
                matched_lap = l
                break

            lap_number = matched_lap["lap_number"] if matched_lap else "?"
            lap_time = matched_lap["lap_time"] if matched_lap else None
            laps_done = sum(1 for l in laps if l["lap_number"] > 0)

            is_finished = result and result["status"] == "FINISHED"

            feed.append({
                "rider_number": rider["number"],
                "rider_name": f"{rider['last_name']} {rider.get('first_name', '')}".strip(),
                "lap_number": lap_number,
                "lap_time": lap_time,
                "laps_required": cat["laps"] if cat else "?",
                "time_str": ev.timestamp_str,
                "status": "FINISHED" if is_finished else "RACING",
            })

        return jsonify({
            "feed": feed,
            "results": all_results,
            "status": status,
            "categories": [{"id": c["id"], "name": c["name"],
                            "laps": c["laps"]} for c in categories],
            "start_time": start_time_ms,
        })


    @app.route("/api/events")
    def api_events():
        events = event_store.get_events()
        return jsonify([
            {
                "timestamp": e.timestamp_str,
                "epc": e.epc,
                "epc_short": e.epc_short,
                "rssi": e.rssi,
                "antenna": e.antenna,
            }
            for e in events
        ])

    @app.route("/api/action", methods=["POST"])
    def api_action():
        """
        Действия:
          {"action": "mass_start", "category_id": 1}
          {"action": "individual_start", "rider_id": 5}
          {"action": "manual_lap", "rider_id": 5}
          {"action": "dnf", "rider_id": 5}
          {"action": "dsq", "rider_id": 5, "reason": "..."}
        """
        if not engine:
            return jsonify({"error": "Engine not available"}), 500

        data = request.get_json(force=True)
        action = data.get("action", "")

        try:
            if action == "mass_start":
                info = engine.mass_start(data["category_id"])
                return jsonify({"ok": True, "info": info})

            elif action == "individual_start":
                info = engine.individual_start(data["rider_id"])
                return jsonify({"ok": True, "info": info})

            elif action == "manual_lap":
                result = engine.manual_lap(data["rider_id"])
                return jsonify({"ok": True, "result": result})

            elif action == "dnf":
                ok = engine.set_dnf(data["rider_id"])
                return jsonify({"ok": ok})

            elif action == "dsq":
                ok = engine.set_dsq(data["rider_id"],
                                     data.get("reason", ""))
                return jsonify({"ok": ok})

            else:
                return jsonify({"error": f"Unknown action: {action}"}), 400

        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return app