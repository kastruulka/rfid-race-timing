import logging
import time
import threading
from flask import render_template, jsonify, request
from .database import Database
from .race_engine import RaceEngine
from .request_helpers import get_json_body, require_int, make_require_engine, safe_400
from .settings import require_admin
from . import actions

logger = logging.getLogger(__name__)


class StartProtocolScheduler:
    def __init__(self, db: Database, engine: RaceEngine):
        self._db = db
        self._engine = engine
        self._lock = threading.Lock()
        self._timers: dict[int, list[threading.Timer]] = {}

    def launch_category(self, category_id: int, entries: list[dict]) -> None:
        with self._lock:
            self._cancel_category_locked(category_id)
            timers: list[threading.Timer] = []
            now_ms = time.time() * 1000
            for entry in entries:
                entry_id = int(entry.get("entry_id", entry.get("id")))
                delay_sec = max(0.0, (float(entry["planned_time"]) - now_ms) / 1000.0)
                timer = threading.Timer(
                    delay_sec,
                    self._start_entry,
                    args=(
                        entry_id,
                        int(entry["rider_id"]),
                        float(entry["planned_time"]),
                        int(category_id),
                    ),
                )
                timer.daemon = True
                timer.start()
                timers.append(timer)
            self._timers[category_id] = timers

    def stop_category(self, category_id: int) -> None:
        with self._lock:
            self._cancel_category_locked(category_id)

        for entry in self._db.get_start_protocol(category_id):
            if entry.get("status") == "PLANNED":
                self._db.update_start_protocol_entry(
                    int(entry["id"]),
                    planned_time=None,
                    actual_time=None,
                    status="WAITING",
                )

    def _cancel_category_locked(self, category_id: int) -> None:
        timers = self._timers.pop(category_id, [])
        for timer in timers:
            timer.cancel()

    def _start_entry(
        self, entry_id: int, rider_id: int, planned_time: float, category_id: int
    ) -> None:
        try:
            body, status = actions.action_individual_start(
                self._engine, rider_id, start_time=planned_time
            )
            if status == 200:
                self._db.update_start_protocol_entry(
                    entry_id,
                    actual_time=planned_time,
                    status="STARTED",
                )
            else:
                logger.warning(
                    "protocol start failed for category=%s rider=%s entry=%s: %s",
                    category_id,
                    rider_id,
                    entry_id,
                    body.get("error"),
                )
                self._db.update_start_protocol_entry(
                    entry_id,
                    actual_time=None,
                    status="ERROR",
                )
        except Exception:
            logger.exception(
                "protocol timer crashed for category=%s rider=%s entry=%s",
                category_id,
                rider_id,
                entry_id,
            )
            try:
                self._db.update_start_protocol_entry(
                    entry_id,
                    actual_time=None,
                    status="ERROR",
                )
            except Exception:
                logger.exception(
                    "failed to store protocol error state for entry=%s", entry_id
                )
        finally:
            with self._lock:
                timers = self._timers.get(category_id, [])
                self._timers[category_id] = [t for t in timers if t.is_alive()]
                if not self._timers[category_id]:
                    self._timers.pop(category_id, None)


def _format_protocol_entry(e: dict) -> dict:
    return {
        "entry_id": e["id"],
        "rider_id": e["rider_id"],
        "rider_number": e["rider_number"],
        "rider_name": f"{e['last_name']} {e.get('first_name', '')}".strip(),
        "position": e["position"],
        "planned_time": e.get("planned_time"),
        "actual_time": e.get("actual_time"),
        "status": e.get("status", "WAITING"),
    }


def register_judge(app, db: Database, engine: RaceEngine = None):

    require_engine = make_require_engine(engine)
    scheduler = StartProtocolScheduler(db, engine) if engine else None

    @app.route("/judge")
    def judge_page():
        return render_template("judge.html")

    @app.route("/api/judge/rider-status/<int:rid>", methods=["GET"])
    def api_judge_rider_status(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify({"status": "DNS", "total_time_ms": None, "dnf_reason": ""})
        total_time_ms = None
        if result.get("finish_time") and result.get("start_time"):
            total_time_ms = int(result["finish_time"]) - int(result["start_time"])
        return jsonify(
            {
                "status": result["status"],
                "total_time_ms": total_time_ms,
                "finish_time": result.get("finish_time"),
                "start_time": result.get("start_time"),
                "dnf_reason": result.get("dnf_reason", ""),
                "penalty_time_ms": result.get("penalty_time_ms") or 0,
                "extra_laps": result.get("extra_laps") or 0,
            }
        )

    @app.route("/api/judge/dnf", methods=["POST"])
    @require_admin
    def api_judge_dnf():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_dnf(
            engine,
            rid,
            reason_code=data.get("reason_code", ""),
            reason_text=data.get("reason_text", ""),
        )
        return jsonify(body), status

    @app.route("/api/judge/dsq", methods=["POST"])
    @require_admin
    def api_judge_dsq():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_dsq(engine, rid, reason=data.get("reason", ""))
        return jsonify(body), status

    @app.route("/api/judge/time-penalty", methods=["POST"])
    @require_admin
    def api_judge_time_penalty():
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        seconds = data.get("seconds", 0)
        result = engine.add_time_penalty(
            rid, float(seconds), reason=data.get("reason", "")
        )
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/extra-lap", methods=["POST"])
    @require_admin
    def api_judge_extra_lap():
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        laps = data.get("laps", 1)
        result = engine.add_extra_lap(rid, int(laps), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/warning", methods=["POST"])
    @require_admin
    def api_judge_warning():
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        result = engine.add_warning(rid, reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/penalty/<int:pid>", methods=["DELETE"])
    @require_admin
    def api_judge_delete_penalty(pid):
        err = require_engine()
        if err:
            return err
        ok = engine.remove_penalty(pid)
        if not ok:
            return jsonify({"error": "Штраф не найден"}), 404
        return jsonify({"ok": True})

    @app.route("/api/judge/log", methods=["GET"])
    def api_judge_log():
        try:
            return jsonify(db.get_penalties_by_race())
        except Exception:
            return jsonify([])

    @app.route("/api/judge/mass-start", methods=["POST"])
    @require_admin
    def api_judge_mass_start():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        body, status = actions.action_mass_start(engine, cat_id)
        return jsonify(body), status

    @app.route("/api/judge/individual-start", methods=["POST"])
    @require_admin
    def api_judge_individual_start():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_individual_start(engine, rid)
        return jsonify(body), status

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
        entries = [
            {"rider_id": int(rid), "position": i + 1, "interval_sec": interval}
            for i, rid in enumerate(data.get("rider_ids", []))
        ]
        if scheduler:
            scheduler.stop_category(cat_id)
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
            {"rider_id": r["id"], "position": i + 1, "interval_sec": interval}
            for i, r in enumerate(riders_list)
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

        entries = db.get_start_protocol(cat_id)
        if not entries:
            return jsonify({"error": "Стартовый протокол пуст"}), 400

        now_ms = time.time() * 1000
        planned = []
        for i, e in enumerate(entries):
            interval = e.get("interval_sec", 30)
            offset_ms = i * interval * 1000
            planned_time = now_ms + offset_ms
            db.update_start_protocol_entry(
                e["id"], planned_time=planned_time, status="PLANNED"
            )

            entry = _format_protocol_entry(e)
            entry["planned_time"] = planned_time
            entry["offset_sec"] = i * interval
            planned.append(entry)

        if scheduler:
            scheduler.launch_category(cat_id, planned)
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

        has_planned = any(e["status"] == "PLANNED" for e in entries)
        has_started = any(e["status"] == "STARTED" for e in entries)
        if not has_planned and not has_started:
            return jsonify({"running": False})

        return jsonify(
            {
                "running": has_planned,
                "planned": [_format_protocol_entry(e) for e in entries],
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

        body, status = actions.action_individual_start(
            engine, rid, start_time=start_time
        )
        if status != 200:
            return jsonify(body), status

        entry_id = data.get("entry_id")
        actual_time = start_time or (time.time() * 1000)
        if entry_id:
            db.update_start_protocol_entry(
                int(entry_id), actual_time=actual_time, status="STARTED"
            )
        return jsonify(body), status

    @app.route("/api/judge/unfinish-rider", methods=["POST"])
    @require_admin
    def api_judge_unfinish_rider():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        ok = engine.unfinish_rider(rid)
        if not ok:
            return jsonify(
                {"error": "Невозможно — участник не FINISHED или категория закрыта"}
            ), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/finish-race", methods=["POST"])
    @require_admin
    def api_judge_finish_race():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        result = engine.finish_all(cat_id)
        return jsonify({"ok": True, **result})

    @app.route("/api/judge/reset-category", methods=["POST"])
    @require_admin
    def api_judge_reset_category():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        try:
            info = engine.reset_category(cat_id)
            return jsonify({"ok": True, **info})
        except ValueError as e:
            logger.warning("reset_category: %s", e)
            return jsonify({"error": "Категория не найдена"}), 400
        except Exception as e:
            return safe_400(e, "reset_category")

    @app.route("/api/judge/edit-finish-time", methods=["POST"])
    @require_admin
    def api_judge_edit_finish_time():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не указан")
        if err:
            return err
        finish_time_ms = data.get("finish_time_ms")
        if finish_time_ms is None:
            return jsonify({"error": "Участник или время не указаны"}), 400
        result = db.get_result_by_rider(rid)
        if not result or result["status"] != "FINISHED":
            return jsonify({"error": "Участник не FINISHED"}), 400
        start = result.get("start_time") or 0
        absolute_finish = int(start) + int(finish_time_ms)
        ok = engine.edit_finish_time(rid, absolute_finish)
        if not ok:
            return jsonify(
                {"error": "Невозможно — категория закрыта или участник не FINISHED"}
            ), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/rider-laps/<int:rid>", methods=["GET"])
    def api_judge_rider_laps(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify([])
        return jsonify(db.get_laps(result["id"]))

    def _check_category_not_closed(lap):
        cat_id = db.get_category_for_result(lap["result_id"])
        if cat_id and db.is_category_closed(cat_id):
            return jsonify({"error": "Категория закрыта"}), 400
        return None

    @app.route("/api/judge/lap/<int:lap_id>", methods=["PUT"])
    @require_admin
    def api_judge_update_lap(lap_id):
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        err = _check_category_not_closed(lap)
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        lap_time_ms = data.get("lap_time_ms")
        if lap_time_ms is None:
            return jsonify({"error": "Время не указано"}), 400
        db.update_lap(lap_id, lap_time=int(lap_time_ms), source="EDITED")
        db.recalc_lap_timestamps(lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/lap/<int:lap_id>", methods=["DELETE"])
    @require_admin
    def api_judge_delete_lap(lap_id):
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        err = _check_category_not_closed(lap)
        if err:
            return err
        db.delete_lap(lap_id)
        db.renumber_laps(lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/manual-lap", methods=["POST"])
    @require_admin
    def api_judge_manual_lap():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        rider = db.get_rider(rid)
        if rider and rider.get("category_id"):
            if db.is_category_closed(rider["category_id"]):
                return jsonify({"error": "Категория закрыта"}), 400
        body, status = actions.action_manual_lap(engine, rid)
        return jsonify(body), status

    @app.route("/api/judge/notes", methods=["GET"])
    def api_judge_notes_list():
        try:
            return jsonify(db.get_notes())
        except Exception:
            return jsonify([])

    @app.route("/api/judge/notes", methods=["POST"])
    @require_admin
    def api_judge_notes_create():
        data, err = get_json_body()
        if err:
            return err
        text = data.get("text", "").strip()
        if not text:
            return jsonify({"error": "Текст заметки пуст"}), 400
        rid = data.get("rider_id")
        nid = db.add_note(text=text, rider_id=int(rid) if rid else None)
        return jsonify({"ok": True, "id": nid})

    @app.route("/api/judge/notes/<int:nid>", methods=["DELETE"])
    @require_admin
    def api_judge_notes_delete(nid):
        db.delete_note(nid)
        return jsonify({"ok": True})
