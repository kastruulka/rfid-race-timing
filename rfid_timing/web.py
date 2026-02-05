from flask import Flask, render_template_string, jsonify

from .event_store import EventStore
from .models import TagEvent


INDEX_HTML = """
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>RFID Прототип — онлайн чтения</title>
  <style>
    body { font-family: sans-serif; margin: 20px; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
    th { background-color: #f0f0f0; }
    .epc { font-family: monospace; }
  </style>
</head>
<body>
  <h1>Онлайн чтения RFID</h1>
  <p>Источник: ридер {{ reader_ip }} / Антенны: {{ antennas }}</p>
  <p>Таблица обновляется автоматически каждые 1 секунду.</p>

  <table>
    <thead>
      <tr>
        <th>Время</th>
        <th>Антенна</th>
        <th>RSSI</th>
        <th>EPC (короткий)</th>
        <th>EPC (полный)</th>
      </tr>
    </thead>
    <tbody id="events-body"></tbody>
  </table>

  <script>
    async function loadEvents() {
      try {
        const resp = await fetch('/api/events');
        const data = await resp.json();
        const tbody = document.getElementById('events-body');
        tbody.innerHTML = '';

        data.forEach(ev => {
          const tr = document.createElement('tr');

          const tdTime = document.createElement('td');
          tdTime.textContent = ev.timestamp;
          tr.appendChild(tdTime);

          const tdAnt = document.createElement('td');
          tdAnt.textContent = ev.antenna;
          tr.appendChild(tdAnt);

          const tdRssi = document.createElement('td');
          tdRssi.textContent = ev.rssi;
          tr.appendChild(tdRssi);

          const tdEpcShort = document.createElement('td');
          tdEpcShort.textContent = ev.epc_short;
          tr.appendChild(tdEpcShort);

          const tdEpc = document.createElement('td');
          tdEpc.textContent = ev.epc;
          tdEpc.className = 'epc';
          tr.appendChild(tdEpc);

          tbody.appendChild(tr);
        });
      } catch (e) {
        console.error('Ошибка при загрузке событий', e);
      }
    }

    loadEvents();
    setInterval(loadEvents, 1000);
  </script>
</body>
</html>
"""


def create_app(event_store: EventStore, reader_ip: str, antennas: set[int]) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            INDEX_HTML,
            reader_ip=reader_ip,
            antennas=", ".join(str(a) for a in sorted(antennas)),
        )

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

    return app