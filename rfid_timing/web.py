import time
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
    }

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
    }
    .header-title {
      font-weight: 900; font-size: 18px;
      letter-spacing: -0.02em; text-transform: uppercase;
    }
    .header-title span { color: var(--accent); }
    .reader-status {
      display: flex; align-items: center; gap: 8px;
      font-size: 13px; font-weight: 600; color: var(--text-dim);
    }
    .status-dot {
      width: 10px; height: 10px; border-radius: 50%;
      background: var(--green); box-shadow: 0 0 8px var(--green);
      animation: pulse-dot 2s infinite;
    }
    @keyframes pulse-dot {
      0%,100% { opacity:1; } 50% { opacity:0.5; }
    }

    .timer-bar {
      display: flex; align-items: center; justify-content: center;
      gap: 32px; padding: 20px 24px;
      background: linear-gradient(180deg, var(--surface2) 0%, var(--bg) 100%);
      border-bottom: 1px solid var(--border);
    }
    .main-clock {
      font-family: var(--mono); font-size: 56px; font-weight: 700;
      letter-spacing: 0.04em; color: var(--accent);
      text-shadow: 0 0 30px var(--accent-glow);
      min-width: 320px; text-align: center;
    }
    .stat-badges { display: flex; gap: 12px; }
    .badge {
      display: flex; flex-direction: column; align-items: center;
      padding: 8px 18px; background: var(--surface);
      border: 1px solid var(--border); border-radius: var(--radius);
      min-width: 80px;
    }
    .badge-num {
      font-family: var(--mono); font-size: 28px;
      font-weight: 700; line-height: 1;
    }
    .badge-label {
      font-size: 10px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-dim); margin-top: 4px;
    }
    .badge.racing .badge-num { color: var(--accent); }
    .badge.finished .badge-num { color: var(--green); }
    .badge.dnf .badge-num { color: var(--red); }

    .main-grid {
      display: grid; grid-template-columns: 340px 1fr;
      height: calc(100vh - 160px);
    }

    /* Feed */
    .feed-panel {
      border-right: 1px solid var(--border);
      display: flex; flex-direction: column; overflow: hidden;
    }
    .panel-header {
      padding: 14px 18px; font-size: 12px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.1em;
      color: var(--text-dim); background: var(--surface);
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .feed-list { flex: 1; overflow-y: auto; padding: 4px 0; }

    .feed-item {
      display: grid; grid-template-columns: 54px 1fr auto;
      align-items: center; gap: 12px; padding: 10px 18px;
      border-bottom: 1px solid rgba(42,53,72,0.5);
    }
    .feed-item.new-item { animation: feed-in 0.3s ease-out; }
    @keyframes feed-in {
      from { opacity:0; transform:translateX(-20px); }
      to { opacity:1; transform:translateX(0); }
    }
    .feed-number {
      font-family: var(--mono); font-size: 20px;
      font-weight: 700; color: var(--accent); text-align: center;
    }
    .feed-name { font-weight: 600; font-size: 14px; white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis; }
    .feed-detail { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
    .feed-time {
      font-family: var(--mono); font-size: 13px; font-weight: 700;
      color: var(--green); text-align: right; white-space: nowrap;
    }
    .feed-item.finish-item { background: var(--green-glow); }
    .feed-item.warmup .feed-detail { color: var(--yellow); }

    /* Results */
    .results-panel { display: flex; flex-direction: column; overflow: hidden; }
    .results-scroll { flex: 1; overflow-y: auto; }
    .controls-bar {
      display: flex; align-items: center; padding: 10px 18px;
      background: var(--surface); border-bottom: 1px solid var(--border);
    }

    .results-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .results-table thead { position: sticky; top: 0; z-index: 2; }
    .results-table th {
      padding: 10px 14px; text-align: left; font-size: 11px;
      font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-dim); background: var(--surface);
      border-bottom: 2px solid var(--border);
    }
    .results-table td {
      padding: 10px 14px;
      border-bottom: 1px solid rgba(42,53,72,0.4);
    }
    .results-table tr:hover { background: rgba(56,189,248,0.04); }

    .col-pos { text-align: center; font-weight: 700; color: var(--text-dim); width: 44px; }
    .col-num { text-align: center; font-family: var(--mono); font-weight: 700; font-size: 16px; color: var(--accent); }
    .col-name { font-weight: 600; }
    .col-club { color: var(--text-dim); font-size: 13px; }
    .col-laps { font-family: var(--mono); text-align: center; }
    .col-time { font-family: var(--mono); font-weight: 700; text-align: right; white-space: nowrap; }
    .col-gap { font-family: var(--mono); font-size: 13px; text-align: right; color: var(--text-dim); }
    .col-lastlap { font-family: var(--mono); font-size: 13px; text-align: right; color: var(--text-dim); }
    .col-status { text-align: center; }
    th.c-center { text-align: center; }
    th.c-right { text-align: right; }

    .status-tag {
      display: inline-block; padding: 3px 10px; border-radius: 4px;
      font-size: 11px; font-weight: 700;
    }
    .status-RACING  { background: var(--accent-glow); color: var(--accent); }
    .status-FINISHED { background: var(--green-glow); color: var(--green); }
    .status-DNF     { background: var(--red-glow); color: var(--red); }
    .status-DSQ     { background: var(--red-glow); color: var(--red); }
    .status-DNS     { background: rgba(100,116,139,0.15); color: var(--text-dim); }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    @media (max-width: 900px) {
      .main-grid { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
      .feed-panel { border-right: none; border-bottom: 1px solid var(--border); }
      .main-clock { font-size: 36px; min-width: auto; }
      .timer-bar { gap: 16px; flex-wrap: wrap; }
    }
  </style>
</head>
<body>

  <div class="header">
    <div class="header-title"><span>RFID</span> Хронометраж</div>
    <div class="reader-status">
      <div class="status-dot"></div>
      <span>{{ reader_ip }} / Антенны: {{ antennas }}</span>
    </div>
  </div>

  <div class="timer-bar">
    <div class="main-clock" id="main-clock">00:00.0</div>
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

  <div class="main-grid">
    <div class="feed-panel">
      <div class="panel-header">Лента проездов</div>
      <div class="feed-list" id="feed-list"></div>
    </div>

    <div class="results-panel">
      <div class="controls-bar">
        <select id="category-select" style="
          font-family:var(--sans); font-size:12px; font-weight:700;
          padding:7px 16px; border:1px solid var(--border); border-radius:6px;
          background:var(--surface2); color:var(--text); cursor:pointer;
        ">
          <option value="">Все категории</option>
        </select>
      </div>
      <div class="results-scroll">
        <table class="results-table">
          <thead>
            <tr>
              <th class="c-center">#</th>
              <th class="c-center">Номер</th>
              <th>Участник</th>
              <th>Команда</th>
              <th class="c-center">Круги</th>
              <th class="c-right">Посл. круг</th>
              <th class="c-right">Общее время</th>
              <th class="c-right">Отстав.</th>
              <th class="c-center">Статус</th>
            </tr>
          </thead>
          <tbody id="results-body"></tbody>
        </table>
      </div>
    </div>
  </div>

<script>

function fmtMs(ms) {
  if (ms === null || ms === undefined) return '—';
  const totalSec = Math.abs(ms) / 1000;
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return String(m).padStart(2, '0') + ':' + s.toFixed(1).padStart(4, '0');
}

let serverElapsedMs = null;   // elapsed на момент последнего ответа сервера
let perfAtSync = null;        // performance.now() в момент синхронизации
let clockTimer = null;
let lastFeedIds = '';         // для предотвращения мигания

function updateClock() {
  if (serverElapsedMs === null) return;
  const localDelta = performance.now() - perfAtSync;
  const elapsed = serverElapsedMs + localDelta;
  document.getElementById('main-clock').textContent = fmtMs(elapsed);
}

function getSelectedCategory() {
  const sel = document.getElementById('category-select');
  return sel ? sel.value : '';
}

async function fetchState() {
  try {
    const catId = getSelectedCategory();
    const qs = catId ? '?category_id=' + encodeURIComponent(catId) : '';
    const resp = await fetch('/api/state' + qs);
    const data = await resp.json();

    if (data.server_elapsed_ms !== null && data.server_elapsed_ms !== undefined) {
      serverElapsedMs = data.server_elapsed_ms;
      perfAtSync = performance.now();
      if (!clockTimer) clockTimer = setInterval(updateClock, 100);
    }

    updateFeed(data.feed);
    updateResults(data.results);
    updateCounters(data.status);
    updateCategories(data.categories);
  } catch (e) {
    console.error('Fetch error', e);
  }
}

function updateFeed(feed) {
  const hash = feed.map(f => f.lap_id).join('|');
  if (hash === lastFeedIds) return;
  lastFeedIds = hash;

  const list = document.getElementById('feed-list');
  const hadChildren = list.children.length > 0;

  list.innerHTML = feed.map((item, i) => {
    const isFinishLap = item.is_finish_lap;
    const isWarmup = item.lap_number === 0;
    let cls = 'feed-item';
    if (isFinishLap) cls += ' finish-item';
    if (isWarmup) cls += ' warmup';
    if (hadChildren && i === 0) cls += ' new-item';

    const lapLabel = isWarmup ? 'разгонный' :
      (isFinishLap ? 'ФИНИШ · круг ' + item.lap_number + '/' + item.laps_required
                   : 'круг ' + item.lap_number + '/' + item.laps_required);

    return '<div class="' + cls + '">' +
      '<div class="feed-number">' + item.rider_number + '</div>' +
      '<div class="feed-info">' +
        '<div class="feed-name">' + item.rider_name + '</div>' +
        '<div class="feed-detail">' + lapLabel + ' · ' + item.time_str + '</div>' +
      '</div>' +
      '<div class="feed-time">' + fmtMs(item.lap_time) + '</div>' +
    '</div>';
  }).join('');
}

function updateResults(results) {
  const tbody = document.getElementById('results-body');
  let leaderTime = null;

  tbody.innerHTML = results.map((r, i) => {
    const pos = r.status === 'FINISHED' ? String(i + 1) : '—';
    if (r.status === 'FINISHED' && leaderTime === null) leaderTime = r.total_time;

    const gap = (r.status === 'FINISHED' && leaderTime !== null && r.total_time !== leaderTime)
      ? '+' + fmtMs(r.total_time - leaderTime) : '';

    return '<tr>' +
      '<td class="col-pos">' + pos + '</td>' +
      '<td class="col-num">' + r.number + '</td>' +
      '<td class="col-name">' + r.name + '</td>' +
      '<td class="col-club">' + (r.club || '') + '</td>' +
      '<td class="col-laps">' + r.laps_done + '/' + r.laps_required + '</td>' +
      '<td class="col-lastlap">' + fmtMs(r.last_lap_time) + '</td>' +
      '<td class="col-time">' + fmtMs(r.total_time) + '</td>' +
      '<td class="col-gap">' + gap + '</td>' +
      '<td class="col-status"><span class="status-tag status-' + r.status + '">' + r.status + '</span></td>' +
    '</tr>';
  }).join('');
}

function updateCounters(st) {
  document.getElementById('cnt-racing').textContent = st.RACING || 0;
  document.getElementById('cnt-finished').textContent = st.FINISHED || 0;
  document.getElementById('cnt-dnf').textContent = (st.DNF || 0) + (st.DSQ || 0);
}

let catsLoaded = false;
function updateCategories(cats) {
  if (catsLoaded || !cats || !cats.length) return;
  const sel = document.getElementById('category-select');
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
  });
  catsLoaded = true;
}

document.getElementById('category-select').addEventListener('change', () => {
  fetchState();
});
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
        if not db or not engine:
            return jsonify({"feed": [], "results": [], "status": {
                "RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0},
                "categories": [], "start_time": None,
                "server_elapsed_ms": None})

        now_ms = int(time.time() * 1000)

        categories = db.get_categories()
        cat_id = request.args.get("category_id", type=int)

        start_time_ms = None
        for cat in categories:
            for r in db.get_results_by_category(cat["id"]):
                st = r.get("start_time")
                if st:
                    st = int(st)
                    if start_time_ms is None or st < start_time_ms:
                        start_time_ms = st

        server_elapsed_ms = None
        if start_time_ms is not None:
            server_elapsed_ms = now_ms - start_time_ms

        all_results = []
        target_cats = [c for c in categories if c["id"] == cat_id] if cat_id else categories

        for cat in target_cats:
            for r in db.get_results_by_category(cat["id"]):
                laps = db.get_laps(r["id"])
                laps_done = sum(1 for l in laps if l["lap_number"] > 0)
                last = laps[-1] if laps else None

                total_time = None
                if r.get("finish_time") and r.get("start_time"):
                    total_time = int(r["finish_time"]) - int(r["start_time"])
                elif last and r.get("start_time"):
                    total_time = int(last["timestamp"]) - int(r["start_time"])

                all_results.append({
                    "rider_id": r["rider_id"],
                    "number": r["number"],
                    "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                    "club": r.get("club", ""),
                    "status": r["status"],
                    "laps_done": laps_done,
                    "laps_required": cat["laps"],
                    "total_time": total_time,
                    "last_lap_time": int(last["lap_time"]) if last and last["lap_time"] else None,
                    "finish_time": int(r["finish_time"]) if r.get("finish_time") else None,
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
            return (4, 0)

        all_results.sort(key=sort_key)

        feed = []
        db_history = db.get_feed_history(limit=50, category_id=cat_id)
        for item in db_history:
            ts_sec = item["timestamp"] / 1000.0
            time_str = time.strftime('%H:%M:%S', time.localtime(ts_sec))

            lap_number = item["lap_number"]
            laps_required = item["laps_required"] if item.get("laps_required") else 1
            is_finish_lap = (lap_number > 0 and lap_number >= laps_required)

            feed.append({
                "lap_id": item["lap_id"],
                "rider_number": item["rider_number"],
                "rider_name": f"{item['last_name']} {item.get('first_name', '')}".strip(),
                "lap_number": lap_number,
                "lap_time": int(item["lap_time"]) if item.get("lap_time") else None,
                "laps_required": laps_required,
                "time_str": time_str,
                "is_finish_lap": is_finish_lap,
            })

        status = engine.get_race_status(cat_id)

        return jsonify({
            "feed": feed,
            "results": all_results,
            "status": status,
            "categories": [{"id": c["id"], "name": c["name"],
                            "laps": c["laps"]} for c in categories],
            "start_time": start_time_ms,
            "server_elapsed_ms": server_elapsed_ms,
        })

    @app.route("/api/events")
    def api_events():
        events = event_store.get_events()
        return jsonify([{
            "timestamp": e.timestamp_str, "epc": e.epc,
            "epc_short": e.epc_short, "rssi": e.rssi, "antenna": e.antenna,
        } for e in events])

    @app.route("/api/action", methods=["POST"])
    def api_action():
        if not engine:
            return jsonify({"error": "Engine not available"}), 500
        data = request.get_json(force=True)
        action = data.get("action", "")
        try:
            if action == "mass_start":
                return jsonify({"ok": True, "info": engine.mass_start(data["category_id"])})
            elif action == "individual_start":
                return jsonify({"ok": True, "info": engine.individual_start(data["rider_id"])})
            elif action == "manual_lap":
                return jsonify({"ok": True, "result": engine.manual_lap(data["rider_id"])})
            elif action == "dnf":
                return jsonify({"ok": engine.set_dnf(data["rider_id"])})
            elif action == "dsq":
                return jsonify({"ok": engine.set_dsq(data["rider_id"], data.get("reason", ""))})
            else:
                return jsonify({"error": f"Unknown action: {action}"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    return app