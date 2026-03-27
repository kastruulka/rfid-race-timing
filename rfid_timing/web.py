import time
from flask import Flask, render_template, jsonify, request

from .event_store import EventStore
from .database import Database
from .race_engine import RaceEngine
from .start_list import register_start_list
from .protocol import register_protocol
from .settings import register_settings, ConfigState
from .judge import register_judge


def create_app(event_store: EventStore, reader_ip: str,
               antennas: set[int],
               db: Database = None,
               engine: RaceEngine = None,
               config_state: ConfigState = None) -> Flask:

    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template(
            "web.html",
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

                penalty_time_ms = r.get("penalty_time_ms") or 0
                extra_laps = r.get("extra_laps") or 0

                if total_time is not None and penalty_time_ms:
                    total_time += penalty_time_ms
                
                total_required = cat["laps"] + extra_laps
                laps_complete = (r["status"] == "RACING"
                                 and r.get("finish_time") is not None
                                 and laps_done >= total_required)
                
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
                    "penalty_time_ms": penalty_time_ms,
                    "extra_laps": extra_laps,
                    "dnf_reason": r.get("dnf_reason", ""),
                    "laps_complete": laps_complete,
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

        race_closed = db.is_race_closed()

        return jsonify({
            "feed": feed,
            "results": all_results,
            "status": status,
            "categories": [{"id": c["id"], "name": c["name"],
                            "laps": c["laps"]} for c in categories],
            "start_time": start_time_ms,
            "server_elapsed_ms": server_elapsed_ms,
            "race_closed": race_closed,
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

    register_start_list(app, db, engine)

    register_protocol(app, db, engine)

    if config_state is None:
        config_state = ConfigState()
    register_settings(app, db, config_state)

    register_judge(app, db, engine)

    return app