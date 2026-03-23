import io
import time
from flask import (
    render_template_string, jsonify, request, Response, send_file,
)
from .database import Database
from .race_engine import RaceEngine


def fmt_ms(ms):
    if ms is None:
        return "—"
    total_sec = abs(ms) / 1000.0
    m = int(total_sec // 60)
    s = total_sec % 60
    return f"{m:02d}:{s:04.1f}"


def fmt_gap(ms):
    if ms is None or ms == 0:
        return ""
    return "+" + fmt_ms(ms)


def fmt_speed(distance_km, time_ms):
    if not distance_km or not time_ms or time_ms <= 0:
        return "—"
    hours = time_ms / 1000.0 / 3600.0
    return f"{distance_km / hours:.1f}"



def build_protocol_data(db: Database, engine: RaceEngine,
                        category_id: int):
    """Собирает полные результаты для протокола."""
    category = db.get_category(category_id)
    if not category:
        return None, []

    engine.calculate_places(category_id)

    results = db.get_results_by_category(category_id)
    distance_total = (category.get("distance_km") or 0) * category["laps"]

    rows = []
    leader_time = None

    for r in results:
        laps = db.get_laps(r["id"])
        laps_done = sum(1 for l in laps if l["lap_number"] > 0)

        total_time = None
        if r.get("finish_time") and r.get("start_time"):
            total_time = int(r["finish_time"]) - int(r["start_time"])
        elif laps and r.get("start_time"):
            total_time = int(laps[-1]["timestamp"]) - int(r["start_time"])

        if r["status"] == "FINISHED" and leader_time is None:
            leader_time = total_time

        gap = None
        if (r["status"] == "FINISHED" and leader_time is not None
                and total_time is not None and total_time != leader_time):
            gap = total_time - leader_time

        lap_details = []
        for l in laps:
            if l["lap_number"] > 0:
                lap_details.append({
                    "number": l["lap_number"],
                    "time": fmt_ms(int(l["lap_time"]) if l.get("lap_time") else None),
                })

        rows.append({
            "place": r.get("place") or "",
            "number": r["number"],
            "last_name": r["last_name"],
            "first_name": r.get("first_name", ""),
            "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
            "birth_year": r.get("birth_year") or "",
            "club": r.get("club", ""),
            "city": r.get("city", ""),
            "status": r["status"],
            "laps_done": laps_done,
            "laps_required": category["laps"],
            "total_time": total_time,
            "total_time_str": fmt_ms(total_time),
            "gap": gap,
            "gap_str": fmt_gap(gap),
            "avg_speed": fmt_speed(distance_total, total_time),
            "lap_details": lap_details,
        })

    return category, rows


PROTOCOL_CONTENT_HTML = """
  <div class="protocol-header">
    <div class="protocol-title">{{ meta.title or 'Протокол результатов' }}</div>
    {% if meta.subtitle %}<div class="protocol-subtitle">{{ meta.subtitle }}</div>{% endif %}
    <div class="protocol-meta">
      {% if meta.date %}<span>{{ meta.date }}</span>{% endif %}
      {% if meta.location %}<span>{{ meta.location }}</span>{% endif %}
      {% if meta.weather %}<span>{{ meta.weather }}</span>{% endif %}
    </div>
  </div>

  <div class="protocol-category">{{ category.name }} — {{ category.laps }} кр.{% if category.distance_km %}, {{ category.distance_km }} км/кр.{% endif %}</div>

  <table>
    <thead>
      <tr>
        {% if cols.place %}<th class="c" style="width:36px">М</th>{% endif %}
        {% if cols.number %}<th class="c" style="width:44px">№</th>{% endif %}
        {% if cols.name %}<th>Участник</th>{% endif %}
        {% if cols.birth_year %}<th class="c" style="width:44px">Год</th>{% endif %}
        {% if cols.club %}<th>Команда</th>{% endif %}
        {% if cols.city %}<th>Город</th>{% endif %}
        {% if cols.time %}<th class="r" style="width:72px">Время</th>{% endif %}
        {% if cols.gap %}<th class="r" style="width:72px">Отстав.</th>{% endif %}
        {% if cols.laps %}<th>Круги</th>{% endif %}
        {% if cols.speed %}<th class="r" style="width:56px">Ср.ск.</th>{% endif %}
        {% if cols.status %}<th class="c" style="width:56px">Статус</th>{% endif %}
      </tr>
    </thead>
    <tbody>
      {% for r in rows %}
      <tr class="{% if r.place == 1 %}place-1{% elif r.place == 2 %}place-2{% elif r.place == 3 %}place-3{% endif %} {% if r.status in ('DNF','DSQ','DNS') %}status-{{ r.status|lower }}{% endif %}">
        {% if cols.place %}<td class="c mono" style="font-weight:700">{{ r.place or '—' }}</td>{% endif %}
        {% if cols.number %}<td class="c mono" style="font-weight:700">{{ r.number }}</td>{% endif %}
        {% if cols.name %}<td style="font-weight:600">{{ r.name }}</td>{% endif %}
        {% if cols.birth_year %}<td class="c">{{ r.birth_year or '' }}</td>{% endif %}
        {% if cols.club %}<td>{{ r.club }}</td>{% endif %}
        {% if cols.city %}<td>{{ r.city }}</td>{% endif %}
        {% if cols.time %}<td class="r mono">{{ r.total_time_str if r.status == 'FINISHED' else '—' }}</td>{% endif %}
        {% if cols.gap %}<td class="r mono">{{ r.gap_str }}</td>{% endif %}
        {% if cols.laps %}<td class="lap-details">{{ r.lap_details | map(attribute='time') | join(' / ') if r.lap_details else '—' }}</td>{% endif %}
        {% if cols.speed %}<td class="r mono">{{ r.avg_speed if r.status == 'FINISHED' else '—' }}</td>{% endif %}
        {% if cols.status %}<td class="c">{{ r.status }}</td>{% endif %}
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% if meta.chief_judge or meta.secretary %}
  <div class="footer">
    <div>
      {% if meta.chief_judge %}
      <div class="footer-line">{{ meta.chief_judge }}</div>
      <div class="footer-label">Главный судья</div>
      {% endif %}
    </div>
    <div>
      {% if meta.secretary %}
      <div class="footer-line">{{ meta.secretary }}</div>
      <div class="footer-label">Секретарь</div>
      {% endif %}
    </div>
  </div>
  {% endif %}
"""

PROTOCOL_PDF_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <style>
    @page { size: A4 landscape; margin: 14mm 12mm; }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 11px; color: #1a1a1a; line-height: 1.35;
    }
    .protocol-header { text-align: center; margin-bottom: 16px; }
    .protocol-title {
      font-size: 16px; font-weight: 800; text-transform: uppercase;
      letter-spacing: 0.03em; margin-bottom: 4px;
    }
    .protocol-subtitle { font-size: 12px; color: #444; margin-bottom: 2px; }
    .protocol-meta {
      display: flex; justify-content: center; gap: 24px;
      font-size: 10px; color: #666; margin-top: 6px; flex-wrap: wrap;
    }
    .protocol-category {
      font-size: 14px; font-weight: 700; margin: 12px 0 8px;
      padding-bottom: 4px; border-bottom: 2px solid #333;
    }
    table {
      width: 100%; border-collapse: collapse; font-size: 10.5px;
    }
    th {
      background: #f0f0f0; padding: 5px 6px; text-align: left;
      font-size: 9px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.04em; border-bottom: 2px solid #999;
    }
    td {
      padding: 4px 6px; border-bottom: 1px solid #ddd;
    }
    tr:nth-child(even) td { background: #fafafa; }
    .c { text-align: center; }
    .r { text-align: right; }
    .mono { font-family: 'Consolas', 'Courier New', monospace; }
    .place-1 td { background: #fff9db; }
    .place-2 td { background: #f0f0f0; }
    .place-3 td { background: #fdf0ec; }
    .status-dnf td, .status-dsq td, .status-dns td { color: #999; }
    .lap-details { font-size: 9px; color: #666; font-family: monospace; }
    .footer {
      margin-top: 28px; display: flex; justify-content: space-between;
      font-size: 10px; color: #444;
    }
    .footer-line { border-top: 1px solid #aaa; padding-top: 4px; min-width: 200px; }
    .footer-label { font-size: 9px; color: #888; }
  </style>
</head>
<body>
""" + PROTOCOL_CONTENT_HTML + """
</body>
</html>
"""


PROTOCOL_PAGE_HTML = r"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Генератор протоколов</title>
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

    .page {
      display: grid; grid-template-columns: 380px 1fr;
      height: calc(100vh - 52px);
    }

    .sidebar {
      border-right: 1px solid var(--border); display: flex;
      flex-direction: column; overflow-y: auto; padding: 20px;
    }
    .sidebar h2 {
      font-size: 14px; font-weight: 900; text-transform: uppercase;
      letter-spacing: -0.01em; margin-bottom: 18px;
    }
    .sidebar h2 span { color: var(--accent); }

    .section-title {
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.06em; color: var(--text-dim);
      margin: 18px 0 10px; padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
    }
    .section-title:first-of-type { margin-top: 0; }

    .form-row { margin-bottom: 12px; }
    .form-row label {
      display: block; font-size: 11px; font-weight: 700;
      text-transform: uppercase; letter-spacing: 0.06em;
      color: var(--text-dim); margin-bottom: 4px;
    }
    .form-row input, .form-row select {
      width: 100%; padding: 8px 12px; font-family: var(--sans); font-size: 13px;
      background: var(--surface2); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); outline: none;
    }
    .form-row input:focus, .form-row select:focus { border-color: var(--accent); }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }

    .checkbox-group { display: flex; flex-wrap: wrap; gap: 6px 14px; }
    .cb-item {
      display: flex; align-items: center; gap: 6px;
      font-size: 12px; font-weight: 600; cursor: pointer;
    }
    .cb-item input[type="checkbox"] {
      width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer;
    }

    .btn {
      display: inline-flex; align-items: center; justify-content: center; gap: 6px;
      padding: 10px 20px; font-family: var(--sans); font-size: 13px; font-weight: 700;
      border: 1px solid var(--border); border-radius: 8px;
      background: var(--surface2); color: var(--text); cursor: pointer;
      transition: background .15s, border-color .15s;
    }
    .btn:hover { background: var(--surface); border-color: var(--accent); }
    .btn-accent { background: var(--accent); color: var(--bg); border-color: var(--accent); }
    .btn-accent:hover { background: #2daae8; }
    .btn-green { background: var(--green); color: #fff; border-color: var(--green); }
    .btn-green:hover { background: #1eab54; }
    .actions-bar {
      display: flex; gap: 10px; margin-top: 22px;
    }
    .actions-bar .btn { flex: 1; }

    .preview-area {
      display: flex; flex-direction: column; overflow: hidden;
      background: var(--surface2);
    }
    .preview-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 12px 20px; background: var(--surface);
      border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .preview-header span {
      font-size: 12px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.1em; color: var(--text-dim);
    }
    .preview-scroll {
      flex: 1; overflow: auto; padding: 24px;
      display: flex; justify-content: center;
    }
    .preview-paper {
      background: #fff; color: #1a1a1a;
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
      font-size: 11px; line-height: 1.35;
      padding: 28px 32px; border-radius: 4px;
      box-shadow: 0 4px 24px rgba(0,0,0,0.4);
      max-width: 1100px; width: 100%; align-self: flex-start;
    }
    .preview-paper .protocol-header { text-align: center; margin-bottom: 16px; }
    .preview-paper .protocol-title {
      font-size: 16px; font-weight: 800; text-transform: uppercase;
      letter-spacing: 0.03em; margin-bottom: 4px; color: #1a1a1a;
    }
    .preview-paper .protocol-subtitle { font-size: 12px; color: #444; margin-bottom: 2px; }
    .preview-paper .protocol-meta {
      display: flex; justify-content: center; gap: 24px;
      font-size: 10px; color: #666; margin-top: 6px; flex-wrap: wrap;
    }
    .preview-paper .protocol-category {
      font-size: 14px; font-weight: 700; margin: 12px 0 8px;
      padding-bottom: 4px; border-bottom: 2px solid #333; color: #1a1a1a;
    }
    .preview-paper table {
      width: 100%; border-collapse: collapse; font-size: 10.5px;
    }
    .preview-paper th {
      background: #f0f0f0; padding: 5px 6px; text-align: left;
      font-size: 9px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.04em; border-bottom: 2px solid #999; color: #333;
    }
    .preview-paper td {
      padding: 4px 6px; border-bottom: 1px solid #ddd; color: #1a1a1a;
    }
    .preview-paper tr:nth-child(even) td { background: #fafafa; }
    .preview-paper .c { text-align: center; }
    .preview-paper .r { text-align: right; }
    .preview-paper .mono { font-family: 'Consolas', 'Courier New', monospace; }
    .preview-paper .place-1 td { background: #fff9db; }
    .preview-paper .place-2 td { background: #f0f0f0; }
    .preview-paper .place-3 td { background: #fdf0ec; }
    .preview-paper .status-dnf td,
    .preview-paper .status-dsq td,
    .preview-paper .status-dns td { color: #999; }
    .preview-paper .lap-details { font-size: 9px; color: #666; font-family: monospace; }
    .preview-paper .footer {
      margin-top: 28px; display: flex; justify-content: space-between;
      font-size: 10px; color: #444;
    }
    .preview-paper .footer-line { border-top: 1px solid #aaa; padding-top: 4px; min-width: 200px; }
    .preview-paper .footer-label { font-size: 9px; color: #888; }
    .preview-empty {
      display: flex; flex-direction: column; align-items: center;
      justify-content: center; color: var(--text-dim); padding: 60px;
    }
    .preview-empty .icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }

    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

    @media (max-width: 900px) {
      .page { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
      .sidebar { max-height: 50vh; overflow-y: auto; }
    }
  </style>
</head>
<body>

  <nav class="topnav">
    <div class="topnav-brand"><span>RFID</span> Хронометраж</div>
    <a href="/start-list">Стартовый лист</a>
    <a href="/">Хронометраж</a>
    <a href="/protocol" class="active">Протокол</a>
  </nav>

  <div class="page">
    <div class="sidebar">
      <h2><span>Генератор</span> протоколов</h2>

      <div class="section-title">Категория</div>
      <div class="form-row">
        <select id="p-category">
          <option value="">— Выберите категорию —</option>
        </select>
      </div>

      <div class="section-title">Метаданные гонки</div>
      <div class="form-row">
        <label>Название гонки</label>
        <input type="text" id="p-title" placeholder="Кубок города по велоспорту">
      </div>
      <div class="form-row">
        <label>Подзаголовок</label>
        <input type="text" id="p-subtitle" placeholder="III этап, шоссейная гонка">
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Дата</label>
          <input type="text" id="p-date" placeholder="23 марта 2026">
        </div>
        <div class="form-row">
          <label>Место</label>
          <input type="text" id="p-location" placeholder="г. Москва">
        </div>
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Погода</label>
          <input type="text" id="p-weather" placeholder="+15°C, ветер 3 м/с">
        </div>
      </div>
      <div class="form-grid">
        <div class="form-row">
          <label>Главный судья</label>
          <input type="text" id="p-judge" placeholder="Иванов И.И.">
        </div>
        <div class="form-row">
          <label>Секретарь</label>
          <input type="text" id="p-secretary" placeholder="Петрова А.С.">
        </div>
      </div>

      <div class="section-title">Столбцы протокола</div>
      <div class="checkbox-group">
        <label class="cb-item"><input type="checkbox" id="col-place" checked> Место</label>
        <label class="cb-item"><input type="checkbox" id="col-number" checked> Номер</label>
        <label class="cb-item"><input type="checkbox" id="col-name" checked> Имя</label>
        <label class="cb-item"><input type="checkbox" id="col-birth_year"> Год рожд.</label>
        <label class="cb-item"><input type="checkbox" id="col-club" checked> Команда</label>
        <label class="cb-item"><input type="checkbox" id="col-city" checked> Город</label>
        <label class="cb-item"><input type="checkbox" id="col-time" checked> Время</label>
        <label class="cb-item"><input type="checkbox" id="col-gap" checked> Отстав.</label>
        <label class="cb-item"><input type="checkbox" id="col-laps"> Круги</label>
        <label class="cb-item"><input type="checkbox" id="col-speed"> Ср. скорость</label>
        <label class="cb-item"><input type="checkbox" id="col-status" checked> Статус</label>
      </div>

      <div class="actions-bar">
        <button class="btn btn-accent" onclick="generatePreview()">Предпросмотр</button>
        <button class="btn btn-green" onclick="downloadPDF()">↓ PDF</button>
      </div>
    </div>

    <div class="preview-area">
      <div class="preview-header">
        <span>Предпросмотр</span>
      </div>
      <div class="preview-scroll" id="preview-scroll">
        <div class="preview-empty" id="preview-empty">
          <div class="icon">📋</div>
          <div>Выберите категорию и нажмите «Предпросмотр»</div>
        </div>
      </div>
    </div>
  </div>

<script>
async function api(url, method, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r;
}

function getConfig() {
  return {
    category_id: parseInt(document.getElementById('p-category').value) || null,
    meta: {
      title: document.getElementById('p-title').value.trim(),
      subtitle: document.getElementById('p-subtitle').value.trim(),
      date: document.getElementById('p-date').value.trim(),
      location: document.getElementById('p-location').value.trim(),
      weather: document.getElementById('p-weather').value.trim(),
      chief_judge: document.getElementById('p-judge').value.trim(),
      secretary: document.getElementById('p-secretary').value.trim(),
    },
    columns: {
      place: document.getElementById('col-place').checked,
      number: document.getElementById('col-number').checked,
      name: document.getElementById('col-name').checked,
      birth_year: document.getElementById('col-birth_year').checked,
      club: document.getElementById('col-club').checked,
      city: document.getElementById('col-city').checked,
      time: document.getElementById('col-time').checked,
      gap: document.getElementById('col-gap').checked,
      laps: document.getElementById('col-laps').checked,
      speed: document.getElementById('col-speed').checked,
      status: document.getElementById('col-status').checked,
    },
  };
}

async function loadCategories() {
  const resp = await api('/api/categories', 'GET');
  const cats = await resp.json();
  const sel = document.getElementById('p-category');
  cats.forEach(c => {
    const o = document.createElement('option');
    o.value = c.id;
    o.textContent = c.name + ' (' + c.laps + ' кр.)';
    sel.appendChild(o);
  });
}

async function generatePreview() {
  const cfg = getConfig();
  if (!cfg.category_id) { alert('Выберите категорию'); return; }

  const resp = await api('/api/protocol/preview', 'POST', cfg);
  const html = await resp.text();

  const scroll = document.getElementById('preview-scroll');
  const empty = document.getElementById('preview-empty');
  if (empty) empty.remove();

  let paper = scroll.querySelector('.preview-paper');
  if (!paper) {
    paper = document.createElement('div');
    paper.className = 'preview-paper';
    scroll.appendChild(paper);
  }
  paper.innerHTML = html;
}

async function downloadPDF() {
  const cfg = getConfig();
  if (!cfg.category_id) { alert('Выберите категорию'); return; }

  const resp = await api('/api/protocol/pdf', 'POST', cfg);
  if (!resp.ok) {
    const err = await resp.json();
    alert(err.error || 'Ошибка генерации PDF');
    return;
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'protocol.pdf';
  a.click();
  URL.revokeObjectURL(url);
}

loadCategories();
</script>
</body>
</html>
"""


def register_protocol(app, db: Database, engine: RaceEngine = None):

    @app.route("/protocol")
    def protocol_page():
        return render_template_string(PROTOCOL_PAGE_HTML)

    @app.route("/api/protocol/preview", methods=["POST"])
    def api_protocol_preview():
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        category, rows = build_protocol_data(db, engine, int(cat_id))
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        meta = data.get("meta", {})
        cols_raw = data.get("columns", {})
        cols = {k: cols_raw.get(k, True) for k in [
            "place", "number", "name", "birth_year", "club",
            "city", "time", "gap", "laps", "speed", "status"]}

        html = render_template_string(
            PROTOCOL_CONTENT_HTML,
            meta=meta, category=category, rows=rows, cols=cols,
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/protocol/pdf", methods=["POST"])
    def api_protocol_pdf():
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        category, rows = build_protocol_data(db, engine, int(cat_id))
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        meta = data.get("meta", {})
        cols_raw = data.get("columns", {})
        cols = {k: cols_raw.get(k, True) for k in [
            "place", "number", "name", "birth_year", "club",
            "city", "time", "gap", "laps", "speed", "status"]}

        html = render_template_string(
            PROTOCOL_PDF_HTML,
            meta=meta, category=category, rows=rows, cols=cols,
        )

        try:
            from weasyprint import HTML as WeasyprintHTML
            pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        except ImportError:
            return jsonify({"error":
                "weasyprint не установлен. "
                "Установите: pip install weasyprint"}), 500
        except Exception as e:
            return jsonify({"error": f"Ошибка PDF: {str(e)}"}), 500

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"protocol_{category['name']}.pdf",
        )