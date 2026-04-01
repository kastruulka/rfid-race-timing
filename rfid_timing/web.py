import logging
import time
from flask import Flask, render_template, jsonify, request

from .event_store import EventStore
from .database import Database
from .race_engine import RaceEngine
from .start_list import register_start_list
from .protocol import register_protocol
from .settings import register_settings, ConfigState
from .judge import register_judge
from .request_helpers import get_json_body, safe_400

logger = logging.getLogger(__name__)


def create_app(
    event_store: EventStore,
    reader_ip: str,
    antennas: set[int],
    db: Database = None,
    engine: RaceEngine = None,
    config_state: ConfigState = None,
    reader_mgr=None,
) -> Flask:

    app = Flask(__name__)

    @app.route("/")
    def index():
        if config_state:
            display_ip = (
                "ЭМУЛЯТОР"
                if config_state["use_emulator"]
                else config_state["reader_ip"]
            )
            display_ant = ", ".join(str(a) for a in sorted(config_state["antennas"]))
        else:
            display_ip = reader_ip
            display_ant = ", ".join(str(a) for a in sorted(antennas))
        return render_template("web.html", reader_ip=display_ip, antennas=display_ant)

    @app.route("/api/state")
    def api_state():
        empty_response = {
            "feed": [],
            "results": [],
            "categories": [],
            "status": {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0},
            "start_time": None,
            "server_elapsed_ms": None,
            "race_closed": False,
            "category_states": {},
        }
        if not db or not engine:
            return jsonify(empty_response)

        now_ms = int(time.time() * 1000)
        categories = db.get_categories()
        cat_id = request.args.get("category_id", type=int)
        race_closed = db.is_race_closed()

        category_states = _build_category_states(db, now_ms)
        start_time_ms = _find_earliest_start(db, categories)
        server_elapsed_ms = _calc_elapsed(db, start_time_ms, now_ms, race_closed)

        target_cats = (
            [c for c in categories if c["id"] == cat_id] if cat_id else categories
        )
        all_results = _build_results(db, target_cats)
        feed = _build_feed(db, cat_id)
        status = engine.get_race_status(cat_id)

        cat_closed = False
        cat_started = False
        if cat_id:
            cat_closed = db.is_category_closed(cat_id)
            cs = db.get_category_state(cat_id)
            cat_started = cs is not None and cs.get("started_at") is not None

        return jsonify(
            {
                "feed": feed,
                "results": all_results,
                "status": status,
                "categories": [
                    {"id": c["id"], "name": c["name"], "laps": c["laps"]}
                    for c in categories
                ],
                "start_time": start_time_ms,
                "server_elapsed_ms": server_elapsed_ms,
                "race_closed": race_closed,
                "category_closed": cat_closed,
                "category_started": cat_started,
                "category_states": category_states,
            }
        )

    @app.route("/api/events")
    def api_events():
        events = event_store.get_events()
        return jsonify(
            [
                {
                    "timestamp": e.timestamp_str,
                    "epc": e.epc,
                    "epc_short": e.epc_short,
                    "rssi": e.rssi,
                    "antenna": e.antenna,
                }
                for e in events
            ]
        )

    @app.route("/api/action", methods=["POST"])
    def api_action():
        if not engine:
            return jsonify({"error": "Engine not available"}), 500
        data, err = get_json_body()
        if err:
            return err
        action = data.get("action", "")
        try:
            if action == "mass_start":
                return jsonify(
                    {"ok": True, "info": engine.mass_start(data["category_id"])}
                )
            elif action == "individual_start":
                return jsonify(
                    {"ok": True, "info": engine.individual_start(data["rider_id"])}
                )
            elif action == "manual_lap":
                return jsonify(
                    {"ok": True, "result": engine.manual_lap(data["rider_id"])}
                )
            elif action == "dnf":
                return jsonify({"ok": engine.set_dnf(data["rider_id"])})
            elif action == "dsq":
                return jsonify(
                    {"ok": engine.set_dsq(data["rider_id"], data.get("reason", ""))}
                )
            else:
                return jsonify({"error": "Неизвестное действие"}), 400
        except Exception as e:
            return safe_400(e, "api_action")

    register_start_list(app, db, engine)
    register_protocol(app, db, engine)
    register_settings(app, db, config_state, reader_mgr=reader_mgr)
    register_judge(app, db, engine)

    return app


def _build_category_states(db: Database, now_ms: int) -> dict:
    states = {}
    for cs in db.get_all_category_states():
        cid = cs["category_id"]
        started = cs.get("started_at")
        closed = cs.get("closed_at")

        elapsed = None
        if started is not None:
            elapsed = (int(closed * 1000) if closed else now_ms) - int(started)

        states[str(cid)] = {
            "started_at": started,
            "closed_at": closed,
            "closed": closed is not None,
            "elapsed_ms": elapsed,
        }
    return states


def _find_earliest_start(db: Database, categories: list) -> int | None:
    start_time_ms = None
    for cat in categories:
        for r in db.get_results_by_category(cat["id"]):
            st = r.get("start_time")
            if st:
                st = int(st)
                if start_time_ms is None or st < start_time_ms:
                    start_time_ms = st
    return start_time_ms


def _calc_elapsed(db: Database, start_time_ms, now_ms: int, race_closed: bool):
    if start_time_ms is None:
        return None
    if not race_closed:
        return now_ms - start_time_ms

    race_id = db.get_current_race_id()
    closed_at_row = (
        db._exec("SELECT closed_at FROM race WHERE id=?", (race_id,)).fetchone()
        if race_id
        else None
    )
    if closed_at_row and closed_at_row["closed_at"]:
        return int(closed_at_row["closed_at"] * 1000) - start_time_ms
    return now_ms - start_time_ms


def _build_results(db: Database, target_cats: list) -> list:
    all_results = []

    for cat in target_cats:
        for r in db.get_results_by_category(cat["id"]):
            laps = db.get_laps(r["id"])
            laps_done = sum(1 for lap in laps if lap["lap_number"] > 0)
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

            all_results.append(
                {
                    "rider_id": r["rider_id"],
                    "number": r["number"],
                    "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                    "club": r.get("club", ""),
                    "status": r["status"],
                    "laps_done": laps_done,
                    "laps_required": cat["laps"],
                    "total_time": total_time,
                    "last_lap_time": int(last["lap_time"])
                    if last and last["lap_time"]
                    else None,
                    "finish_time": int(r["finish_time"])
                    if r.get("finish_time")
                    else None,
                    "penalty_time_ms": penalty_time_ms,
                    "extra_laps": extra_laps,
                    "dnf_reason": r.get("dnf_reason", ""),
                    "laps_complete": (
                        r["status"] == "RACING"
                        and r.get("finish_time") is not None
                        and laps_done >= total_required
                    ),
                }
            )

    def sort_key(r):
        status_order = {"FINISHED": 0, "RACING": 1, "DNF": 2, "DSQ": 3}
        order = status_order.get(r["status"], 4)
        if r["status"] == "RACING":
            return (order, -r["laps_done"], r["total_time"] or 0)
        return (order, r["total_time"] or 0)

    all_results.sort(key=sort_key)
    return all_results


def _build_feed(db: Database, category_id: int = None) -> list:
    feed = []
    for item in db.get_feed_history(limit=50, category_id=category_id):
        ts_sec = item["timestamp"] / 1000.0
        lap_number = item["lap_number"]
        laps_required = item.get("laps_required") or 1

        feed.append(
            {
                "lap_id": item["lap_id"],
                "rider_number": item["rider_number"],
                "rider_name": f"{item['last_name']} {item.get('first_name', '')}".strip(),
                "lap_number": lap_number,
                "lap_time": int(item["lap_time"]) if item.get("lap_time") else None,
                "laps_required": laps_required,
                "time_str": time.strftime("%H:%M:%S", time.localtime(ts_sec)),
                "is_finish_lap": lap_number > 0 and lap_number >= laps_required,
            }
        )
    return feed
