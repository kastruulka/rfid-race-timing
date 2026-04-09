import time

from flask import jsonify, request

from ..http import actions
from ..database import Database
from ..http.request_helpers import get_json_body, require_int, safe_error
from ..race_engine import RaceEngine
from ..security.auth import require_admin


def _format_protocol_entry(entry: dict) -> dict:
    return {
        "entry_id": entry["id"],
        "rider_id": entry["rider_id"],
        "rider_number": entry["rider_number"],
        "rider_name": f"{entry['last_name']} {entry.get('first_name', '')}".strip(),
        "position": entry["position"],
        "planned_time": entry.get("planned_time"),
        "actual_time": entry.get("actual_time"),
        "status": entry.get("status", "WAITING"),
    }


def _reset_entries_to_waiting(
    db: Database, entries: list[dict], scheduler, category_id: int
):
    if scheduler:
        scheduler.stop_category(category_id)
        return

    for entry in entries:
        if entry.get("status") == "STARTED":
            continue
        db.update_start_protocol_entry(
            entry["id"],
            planned_time=None,
            actual_time=None,
            status="WAITING",
        )


def _save_protocol_preserving_started(
    db: Database,
    category_id: int,
    rider_ids: list[int],
    interval_sec: float,
) -> int:
    race_id = db.get_current_race_id()
    existing_entries = db.get_start_protocol(category_id, race_id=race_id)
    started_entries = [
        entry for entry in existing_entries if entry.get("status") == "STARTED"
    ]
    started_ids = {int(entry["rider_id"]) for entry in started_entries}

    remaining_rider_ids = [
        int(rider_id) for rider_id in rider_ids if int(rider_id) not in started_ids
    ]

    with db._transaction():
        db._exec(
            "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        )

        position = 1
        for entry in started_entries:
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, planned_time, actual_time, status)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    race_id,
                    category_id,
                    entry["rider_id"],
                    position,
                    entry.get("interval_sec", interval_sec),
                    None,
                    entry.get("actual_time"),
                    "STARTED",
                ),
            )
            position += 1

        for rider_id in remaining_rider_ids:
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, status)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    race_id,
                    category_id,
                    rider_id,
                    position,
                    interval_sec,
                    "WAITING",
                ),
            )
            position += 1

    return len(started_entries) + len(remaining_rider_ids)


def register_judge_protocol_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    scheduler=None,
    require_engine=None,
):
    @app.route("/api/judge/start-protocol", methods=["GET"])
    def api_start_protocol_get():
        cat_id = request.args.get("category_id", type=int)
        if not cat_id:
            return jsonify([])
        return jsonify(db.get_start_protocol(cat_id))

    @app.route("/api/judge/start-protocol", methods=["POST"])
    @require_admin
    def api_start_protocol_save():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        interval = float(data.get("interval_sec", 30))
        rider_ids = [int(rid) for rid in data.get("rider_ids", [])]
        existing_entries = db.get_start_protocol(cat_id)
        has_started_entries = any(
            entry.get("status") == "STARTED" for entry in existing_entries
        )

        if scheduler:
            scheduler.stop_category(cat_id)

        if has_started_entries:
            count = _save_protocol_preserving_started(
                db,
                category_id=cat_id,
                rider_ids=rider_ids,
                interval_sec=interval,
            )
        else:
            entries = [
                {"rider_id": rider_id, "position": i + 1, "interval_sec": interval}
                for i, rider_id in enumerate(rider_ids)
            ]
            count = db.save_start_protocol(cat_id, entries)
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol", methods=["DELETE"])
    @require_admin
    def api_start_protocol_clear():
        cat_id = request.args.get("category_id", type=int)
        if cat_id:
            if scheduler:
                scheduler.stop_category(cat_id)
            db.clear_start_protocol(cat_id)
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/auto-fill", methods=["POST"])
    @require_admin
    def api_start_protocol_autofill():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        interval = float(data.get("interval_sec", 30))
        riders_list = db.get_riders(category_id=cat_id)
        entries = [
            {"rider_id": rider["id"], "position": i + 1, "interval_sec": interval}
            for i, rider in enumerate(riders_list)
        ]
        if scheduler:
            scheduler.stop_category(cat_id)
        count = db.save_start_protocol(cat_id, entries)
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol/launch", methods=["POST"])
    @require_admin
    def api_start_protocol_launch():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        resume_delay_ms = float(data.get("resume_delay_ms", 0) or 0)

        entries = db.get_start_protocol(cat_id)
        if not entries:
            return jsonify({"error": "Стартовый протокол пуст"}), 400

        remaining_entries = [
            entry for entry in entries if entry.get("status") != "STARTED"
        ]
        if not remaining_entries:
            return jsonify({"error": "Все участники из протокола уже стартовали"}), 400

        now_ms = time.time() * 1000
        for i, entry in enumerate(remaining_entries):
            interval = entry.get("interval_sec", 30)
            planned_time = now_ms + resume_delay_ms + (i * interval * 1000)
            db.update_start_protocol_entry(
                entry["id"],
                planned_time=planned_time,
                actual_time=None,
                status="PLANNED",
            )

        if scheduler:
            scheduler.launch()

        if resume_delay_ms > 0:
            planned = [
                _format_protocol_entry(entry) for entry in db.get_start_protocol(cat_id)
            ]
            return jsonify(
                {
                    "ok": True,
                    "planned": planned,
                    "first_start_ms": now_ms + resume_delay_ms,
                }
            )

        first_entry = _format_protocol_entry(remaining_entries[0])
        first_entry["planned_time"] = now_ms
        db.update_start_protocol_entry(first_entry["entry_id"], status="STARTING")

        try:
            body, status = actions.action_individual_start(
                engine,
                first_entry["rider_id"],
                start_time=now_ms,
            )
        except Exception as exc:
            _reset_entries_to_waiting(db, remaining_entries, scheduler, cat_id)
            return safe_error(exc, "start_protocol_launch")

        if status != 200:
            _reset_entries_to_waiting(db, remaining_entries, scheduler, cat_id)
            return jsonify(body), status

        db.update_start_protocol_entry(
            first_entry["entry_id"],
            actual_time=now_ms,
            status="STARTED",
        )

        planned = [
            _format_protocol_entry(entry) for entry in db.get_start_protocol(cat_id)
        ]
        return jsonify({"ok": True, "planned": planned, "first_start_ms": now_ms})

    @app.route("/api/judge/start-protocol/stop", methods=["POST"])
    @require_admin
    def api_start_protocol_stop():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        if scheduler:
            scheduler.stop_category(cat_id)
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/status", methods=["GET"])
    def api_start_protocol_status():
        cat_id = request.args.get("category_id", type=int)
        if not cat_id:
            return jsonify({"running": False})

        entries = db.get_start_protocol(cat_id)
        if not entries:
            return jsonify({"running": False})

        has_planned = any(
            entry["status"] in {"PLANNED", "STARTING"} for entry in entries
        )
        has_started = any(entry["status"] == "STARTED" for entry in entries)
        if not has_planned and not has_started:
            return jsonify({"running": False})

        return jsonify(
            {
                "running": has_planned,
                "planned": [_format_protocol_entry(entry) for entry in entries],
            }
        )

    @app.route("/api/judge/start-protocol/start-rider", methods=["POST"])
    @require_admin
    def api_start_protocol_start_rider():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id")
        if err:
            return err

        planned_time = data.get("planned_time")
        start_time = float(planned_time) if planned_time else None

        try:
            body, status = actions.action_individual_start(
                engine,
                rid,
                start_time=start_time,
            )
        except Exception as exc:
            return safe_error(exc, "start_protocol_start_rider")

        if status != 200:
            return jsonify(body), status

        entry_id = data.get("entry_id")
        actual_time = start_time or (time.time() * 1000)
        if entry_id:
            db.update_start_protocol_entry(
                int(entry_id),
                actual_time=actual_time,
                status="STARTED",
            )
        return jsonify(body), status
