import time

from flask import jsonify, request

from ..database import Database
from ..http import actions
from ..http.request_helpers import get_json_body, require_int, safe_error
from ..race_engine import RaceEngine
from ..security.auth import require_admin


def _format_protocol_entry(entry: dict) -> dict:
    return {
        "entry_id": entry["id"],
        "rider_id": entry["rider_id"],
        "rider_number": entry["rider_number"],
        "rider_name": f"{entry['last_name']} {entry.get('first_name', '')}".strip(),
        "category_id": entry["category_id"],
        "category_name": entry.get("category_name"),
        "position": entry["position"],
        "planned_time": entry.get("planned_time"),
        "actual_time": entry.get("actual_time"),
        "status": entry.get("status", "WAITING"),
    }


def _parse_category_ids(data: dict) -> list[int]:
    category_ids = data.get("category_ids")
    if category_ids is not None:
        if not isinstance(category_ids, list):
            raise ValueError("category_ids must be a list")
        raw_ids = category_ids
    elif data.get("category_id") is not None:
        raw_ids = [data.get("category_id")]
    else:
        raise ValueError("Категория не выбрана")

    normalized_ids: list[int] = []
    seen = set()
    for value in raw_ids:
        current_id = int(value)
        if current_id in seen:
            continue
        seen.add(current_id)
        normalized_ids.append(current_id)

    if not normalized_ids:
        raise ValueError("Категория не выбрана")
    return normalized_ids


def _parse_query_category_ids() -> list[int]:
    raw = request.args.get("category_ids", "").strip()
    if raw:
        return _parse_category_ids(
            {"category_ids": [part.strip() for part in raw.split(",") if part.strip()]}
        )

    category_id = request.args.get("category_id", type=int)
    if category_id is None:
        return []
    return [int(category_id)]


def _get_protocol_entries(db: Database, category_ids: list[int]) -> list[dict]:
    if not category_ids:
        return []

    race_id = db.get_current_race_id()
    if race_id is None:
        return []

    placeholders = ",".join("?" for _ in category_ids)
    rows = db._exec(
        f"""
        SELECT sp.*, rd.number as rider_number,
               rd.last_name, rd.first_name,
               rd.club, rd.city,
               cat.name as category_name
        FROM start_protocol sp
        JOIN rider rd ON sp.rider_id = rd.id
        JOIN category cat ON sp.category_id = cat.id
        WHERE sp.race_id=? AND sp.category_id IN ({placeholders})
        ORDER BY sp.position, sp.id
        """,
        (race_id, *category_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def _clear_protocol_for_categories(db: Database, category_ids: list[int]) -> None:
    if not category_ids:
        return
    race_id = db.get_current_race_id()
    if race_id is None:
        return
    placeholders = ",".join("?" for _ in category_ids)
    db._exec(
        f"DELETE FROM start_protocol WHERE race_id=? AND category_id IN ({placeholders})",
        (race_id, *category_ids),
    )


def _normalize_protocol_entries(
    db: Database,
    category_ids: list[int],
    entries: list[dict] | None,
    rider_ids: list[int] | None,
) -> list[dict]:
    allowed_ids = {int(category_id) for category_id in category_ids}
    normalized_entries: list[dict] = []

    if entries is not None:
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError("Некорректная запись очереди старта")
            rider_id = int(entry.get("rider_id"))
            category_id = int(entry.get("category_id"))
            if category_id not in allowed_ids:
                raise ValueError("Участник добавлен из категории вне выбранного набора")
            rider = db.get_rider(rider_id)
            if not rider or int(rider.get("category_id") or 0) != category_id:
                raise ValueError(
                    "Участник не найден или не принадлежит выбранной категории"
                )
            normalized_entries.append(
                {
                    "rider_id": rider_id,
                    "category_id": category_id,
                    "position": index,
                }
            )
        return normalized_entries

    if rider_ids is None:
        return []

    if len(category_ids) != 1:
        raise ValueError("Для нескольких категорий требуется передать entries")

    category_id = category_ids[0]
    for index, rider_id in enumerate(rider_ids, start=1):
        rider = db.get_rider(int(rider_id))
        if not rider or int(rider.get("category_id") or 0) != category_id:
            raise ValueError(
                "Участник не найден или не принадлежит выбранной категории"
            )
        normalized_entries.append(
            {
                "rider_id": int(rider_id),
                "category_id": category_id,
                "position": index,
            }
        )
    return normalized_entries


def _reset_entries_to_waiting(
    db: Database, entries: list[dict], scheduler, category_ids: list[int]
):
    if scheduler:
        for category_id in category_ids:
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


def _save_protocol_entries(
    db: Database,
    category_ids: list[int],
    queue_entries: list[dict],
    interval_sec: float,
) -> int:
    race_id = db.get_current_race_id()
    with db._transaction():
        _clear_protocol_for_categories(db, category_ids)
        for index, entry in enumerate(queue_entries, start=1):
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, status)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    race_id,
                    entry["category_id"],
                    entry["rider_id"],
                    index,
                    interval_sec,
                    "WAITING",
                ),
            )
    return len(queue_entries)


def _save_protocol_preserving_started(
    db: Database,
    category_ids: list[int],
    queue_entries: list[dict],
    interval_sec: float,
) -> int:
    race_id = db.get_current_race_id()
    existing_entries = _get_protocol_entries(db, category_ids)
    started_entries = [
        entry for entry in existing_entries if entry.get("status") == "STARTED"
    ]
    started_ids = {int(entry["rider_id"]) for entry in started_entries}
    remaining_entries = [
        entry for entry in queue_entries if int(entry["rider_id"]) not in started_ids
    ]

    with db._transaction():
        _clear_protocol_for_categories(db, category_ids)
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
                    entry["category_id"],
                    entry["rider_id"],
                    position,
                    entry.get("interval_sec", interval_sec),
                    None,
                    db._normalize_db_value("actual_time", entry.get("actual_time")),
                    "STARTED",
                ),
            )
            position += 1

        for entry in remaining_entries:
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, status)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    race_id,
                    entry["category_id"],
                    entry["rider_id"],
                    position,
                    interval_sec,
                    "WAITING",
                ),
            )
            position += 1

    return len(started_entries) + len(remaining_entries)


def register_judge_protocol_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    scheduler=None,
    require_engine=None,
):
    @app.route("/api/judge/start-protocol", methods=["GET"])
    def api_start_protocol_get():
        category_ids = _parse_query_category_ids()
        if not category_ids:
            return jsonify([])
        return jsonify(_get_protocol_entries(db, category_ids))

    @app.route("/api/judge/start-protocol", methods=["POST"])
    @require_admin
    def api_start_protocol_save():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = _parse_category_ids(data)
            queue_entries = _normalize_protocol_entries(
                db,
                category_ids,
                data.get("entries"),
                data.get("rider_ids", []),
            )
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        interval = float(data.get("interval_sec", 30))
        existing_entries = _get_protocol_entries(db, category_ids)
        has_started_entries = any(
            entry.get("status") == "STARTED" for entry in existing_entries
        )

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)

        if has_started_entries:
            count = _save_protocol_preserving_started(
                db,
                category_ids=category_ids,
                queue_entries=queue_entries,
                interval_sec=interval,
            )
        else:
            count = _save_protocol_entries(
                db,
                category_ids=category_ids,
                queue_entries=queue_entries,
                interval_sec=interval,
            )
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol", methods=["DELETE"])
    @require_admin
    def api_start_protocol_clear():
        category_ids = _parse_query_category_ids()
        if category_ids:
            if scheduler:
                for category_id in category_ids:
                    scheduler.stop_category(category_id)
            if len(category_ids) == 1:
                db.clear_start_protocol(category_ids[0])
            else:
                _clear_protocol_for_categories(db, category_ids)
                db._commit()
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/auto-fill", methods=["POST"])
    @require_admin
    def api_start_protocol_autofill():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = _parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        interval = float(data.get("interval_sec", 30))
        queue_entries = []
        for category_id in category_ids:
            for rider in db.get_riders(category_id=category_id):
                queue_entries.append(
                    {
                        "rider_id": rider["id"],
                        "category_id": rider["category_id"],
                    }
                )

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)

        count = _save_protocol_entries(
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
            category_ids = _parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        resume_delay_ms = float(data.get("resume_delay_ms", 0) or 0)
        entries = _get_protocol_entries(db, category_ids)
        if not entries:
            return jsonify({"error": "Стартовый протокол пуст"}), 400

        remaining_entries = [
            entry for entry in entries if entry.get("status") != "STARTED"
        ]
        if not remaining_entries:
            return jsonify({"error": "Все участники из протокола уже стартовали"}), 400

        now_ms = time.time() * 1000
        for index, entry in enumerate(remaining_entries):
            interval = entry.get("interval_sec", 30)
            planned_time = now_ms + resume_delay_ms + (index * interval * 1000)
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
                _format_protocol_entry(entry)
                for entry in _get_protocol_entries(db, category_ids)
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
            _reset_entries_to_waiting(db, remaining_entries, scheduler, category_ids)
            return safe_error(exc, "start_protocol_launch")

        if status != 200:
            _reset_entries_to_waiting(db, remaining_entries, scheduler, category_ids)
            return jsonify(body), status

        db.update_start_protocol_entry(
            first_entry["entry_id"],
            actual_time=now_ms,
            status="STARTED",
        )

        planned = [
            _format_protocol_entry(entry)
            for entry in _get_protocol_entries(db, category_ids)
        ]
        return jsonify({"ok": True, "planned": planned, "first_start_ms": now_ms})

    @app.route("/api/judge/start-protocol/stop", methods=["POST"])
    @require_admin
    def api_start_protocol_stop():
        data, err = get_json_body()
        if err:
            return err

        try:
            category_ids = _parse_category_ids(data)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        if scheduler:
            for category_id in category_ids:
                scheduler.stop_category(category_id)
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/status", methods=["GET"])
    def api_start_protocol_status():
        category_ids = _parse_query_category_ids()
        if not category_ids:
            return jsonify({"running": False})

        entries = _get_protocol_entries(db, category_ids)
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
