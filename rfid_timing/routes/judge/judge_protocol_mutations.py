import time

from flask import jsonify

from ...database.database import Database
from ...http import actions
from ...http.request_helpers import get_json_body, require_int, safe_error
from ...app.race_engine import RaceEngine
from ...security.auth import require_admin
from ...services.start_protocol.start_protocol_service import (
    apply_launch_plan,
    build_launch_plan,
    clear_protocol_for_categories,
    format_protocol_entry,
    get_protocol_entries,
    normalize_protocol_entries,
    remaining_protocol_entries,
    reset_entries_to_waiting,
    save_protocol_entries,
    save_protocol_preserving_started,
)
from .judge_protocol_shared import parse_category_ids, parse_query_category_ids


def register_judge_protocol_mutation_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    scheduler=None,
    require_engine=None,
):
    @app.route("/api/judge/start-protocol", methods=["POST"])
    @require_admin
    def api_start_protocol_save():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = parse_category_ids(data)
            queue_entries = normalize_protocol_entries(
                db,
                category_ids,
                data.get("entries"),
                data.get("rider_ids", []),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        interval = float(data.get("interval_sec", 30))
        existing_entries = get_protocol_entries(db, category_ids)
        has_started_entries = any(
            entry.get("status") == "STARTED" for entry in existing_entries
        )

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)

        if has_started_entries:
            count = save_protocol_preserving_started(
                db,
                category_ids=category_ids,
                queue_entries=queue_entries,
                interval_sec=interval,
            )
        else:
            count = save_protocol_entries(
                db,
                category_ids=category_ids,
                queue_entries=queue_entries,
                interval_sec=interval,
            )
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol", methods=["DELETE"])
    @require_admin
    def api_start_protocol_clear():
        category_ids = parse_query_category_ids()
        if category_ids:
            if scheduler:
                for category_id in category_ids:
                    scheduler.stop_category(category_id)
            if len(category_ids) == 1:
                db.start_protocol_repo.clear_start_protocol(category_ids[0])
            else:
                clear_protocol_for_categories(db, category_ids)
                db._commit()
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/auto-fill", methods=["POST"])
    @require_admin
    def api_start_protocol_autofill():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        interval = float(data.get("interval_sec", 30))
        queue_entries = []
        for category_id in category_ids:
            if db.category_state_repo.is_category_closed(category_id):
                continue
            for rider in db.riders_repo.get_riders(category_id=category_id):
                if db.results_repo.has_active_unfinished_race(rider["id"]):
                    continue
                queue_entries.append(
                    {
                        "rider_id": rider["id"],
                        "category_id": rider["category_id"],
                    }
                )

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)

        count = save_protocol_entries(
            db,
            category_ids=category_ids,
            queue_entries=queue_entries,
            interval_sec=interval,
        )
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

        try:
            category_ids = parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        resume_delay_ms = float(data.get("resume_delay_ms", 0) or 0)
        entries = get_protocol_entries(db, category_ids)
        if not entries:
            return jsonify({"error": "Стартовый протокол пуст"}), 400

        remaining_entries = remaining_protocol_entries(entries)
        if not remaining_entries:
            return jsonify({"error": "Все участники из протокола уже стартовали"}), 400

        now_ms = time.time() * 1000
        apply_launch_plan(
            db,
            build_launch_plan(remaining_entries, now_ms, resume_delay_ms),
        )

        if scheduler:
            scheduler.launch()

        if resume_delay_ms > 0:
            planned = [
                format_protocol_entry(entry)
                for entry in get_protocol_entries(db, category_ids)
            ]
            return jsonify(
                {
                    "ok": True,
                    "planned": planned,
                    "first_start_ms": now_ms + resume_delay_ms,
                }
            )

        first_entry = format_protocol_entry(remaining_entries[0])
        first_entry["planned_time"] = now_ms
        db.start_protocol_repo.update_start_protocol_entry(
            first_entry["entry_id"], status="STARTING"
        )

        try:
            body, status = actions.action_individual_start(
                engine,
                first_entry["rider_id"],
                start_time=now_ms,
            )
        except Exception as exc:
            reset_entries_to_waiting(db, remaining_entries, scheduler, category_ids)
            return safe_error(exc, "start_protocol_launch")

        if status != 200:
            reset_entries_to_waiting(db, remaining_entries, scheduler, category_ids)
            return jsonify(body), status

        db.start_protocol_repo.update_start_protocol_entry(
            first_entry["entry_id"],
            actual_time=now_ms,
            status="STARTED",
        )

        planned = [
            format_protocol_entry(entry)
            for entry in get_protocol_entries(db, category_ids)
        ]
        return jsonify({"ok": True, "planned": planned, "first_start_ms": now_ms})

    @app.route("/api/judge/start-protocol/stop", methods=["POST"])
    @require_admin
    def api_start_protocol_stop():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)
        return jsonify({"ok": True})

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
            db.start_protocol_repo.update_start_protocol_entry(
                int(entry_id),
                actual_time=actual_time,
                status="STARTED",
            )
        return jsonify(body), status
