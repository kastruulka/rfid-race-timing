import logging
import time
from flask import render_template, jsonify, request
from .database import Database
from .race_engine import RaceEngine
from .request_helpers import get_json_body, safe_400

logger = logging.getLogger(__name__)


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

    def _require_engine():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        return None

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
    def api_judge_dnf():
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dnf(
            int(rid),
            reason_code=data.get("reason_code", ""),
            reason_text=data.get("reason_text", ""),
        )
        if not ok:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/dsq", methods=["POST"])
    def api_judge_dsq():
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dsq(int(rid), reason=data.get("reason", ""))
        if not ok:
            return jsonify({"error": "Невозможно"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/time-penalty", methods=["POST"])
    def api_judge_time_penalty():
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        seconds = data.get("seconds", 0)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_time_penalty(
            int(rid), float(seconds), reason=data.get("reason", "")
        )
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/extra-lap", methods=["POST"])
    def api_judge_extra_lap():
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        laps = data.get("laps", 1)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_extra_lap(
            int(rid), int(laps), reason=data.get("reason", "")
        )
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/warning", methods=["POST"])
    def api_judge_warning():
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_warning(int(rid), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/penalty/<int:pid>", methods=["DELETE"])
    def api_judge_delete_penalty(pid):
        err = _require_engine()
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
    def api_judge_mass_start():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        try:
            info = engine.mass_start(int(cat_id))
            return jsonify({"ok": True, "info": info})
        except ValueError as e:
            logger.warning("mass_start: %s", e)
            return jsonify({"error": "Невозможно запустить категорию"}), 400
        except Exception as e:
            return safe_400(e, "mass_start")

    @app.route("/api/judge/individual-start", methods=["POST"])
    def api_judge_individual_start():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        try:
            info = engine.individual_start(int(rid))
            return jsonify({"ok": True, "info": info})
        except ValueError as e:
            logger.warning("individual_start: %s", e)
            return jsonify({"error": "Невозможно стартовать участника"}), 400
        except Exception as e:
            return safe_400(e, "individual_start")

    @app.route("/api/judge/start-protocol", methods=["GET"])
    def api_start_protocol_get():
        cat_id = request.args.get("category_id", type=int)
        if not cat_id:
            return jsonify([])
        return jsonify(db.get_start_protocol(cat_id))

    @app.route("/api/judge/start-protocol", methods=["POST"])
    def api_start_protocol_save():
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        interval = float(data.get("interval_sec", 30))
        entries = [
            {"rider_id": int(rid), "position": i + 1, "interval_sec": interval}
            for i, rid in enumerate(data.get("rider_ids", []))
        ]
        count = db.save_start_protocol(int(cat_id), entries)
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol", methods=["DELETE"])
    def api_start_protocol_clear():
        cat_id = request.args.get("category_id", type=int)
        if cat_id:
            db.clear_start_protocol(cat_id)
        return jsonify({"ok": True})

    @app.route("/api/judge/start-protocol/auto-fill", methods=["POST"])
    def api_start_protocol_autofill():
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        interval = float(data.get("interval_sec", 30))
        riders_list = db.get_riders(category_id=int(cat_id))
        entries = [
            {"rider_id": r["id"], "position": i + 1, "interval_sec": interval}
            for i, r in enumerate(riders_list)
        ]
        count = db.save_start_protocol(int(cat_id), entries)
        return jsonify({"ok": True, "count": count})

    @app.route("/api/judge/start-protocol/launch", methods=["POST"])
    def api_start_protocol_launch():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        entries = db.get_start_protocol(int(cat_id))
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

        return jsonify({"ok": True, "planned": planned, "first_start_ms": now_ms})

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
    def api_start_protocol_start_rider():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rider_id = data.get("rider_id")
        if not rider_id:
            return jsonify({"error": "rider_id required"}), 400
        try:
            planned_time = data.get("planned_time")
            start_time = float(planned_time) if planned_time else None

            info = engine.individual_start(int(rider_id), start_time=start_time)

            entry_id = data.get("entry_id")
            actual_time = start_time or (time.time() * 1000)
            if entry_id:
                db.update_start_protocol_entry(
                    int(entry_id), actual_time=actual_time, status="STARTED"
                )
            return jsonify({"ok": True, "info": info})
        except ValueError as e:
            logger.warning("start-rider: %s", e)
            return jsonify({"error": "Невозможно стартовать участника"}), 400
        except Exception as e:
            return safe_400(e, "start-rider")

    @app.route("/api/judge/unfinish-rider", methods=["POST"])
    def api_judge_unfinish_rider():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.unfinish_rider(int(rid))
        if not ok:
            return jsonify(
                {"error": "Невозможно — участник не FINISHED или категория закрыта"}
            ), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/finish-race", methods=["POST"])
    def api_judge_finish_race():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        result = engine.finish_all(int(cat_id))
        return jsonify({"ok": True, **result})

    @app.route("/api/judge/reset-category", methods=["POST"])
    def api_judge_reset_category():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        try:
            info = engine.reset_category(int(cat_id))
            return jsonify({"ok": True, **info})
        except ValueError as e:
            logger.warning("reset_category: %s", e)
            return jsonify({"error": "Категория не найдена"}), 400
        except Exception as e:
            return safe_400(e, "reset_category")

    @app.route("/api/judge/edit-finish-time", methods=["POST"])
    def api_judge_edit_finish_time():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        finish_time_ms = data.get("finish_time_ms")
        if not rid or finish_time_ms is None:
            return jsonify({"error": "Участник или время не указаны"}), 400
        result = db.get_result_by_rider(int(rid))
        if not result or result["status"] != "FINISHED":
            return jsonify({"error": "Участник не FINISHED"}), 400
        start = result.get("start_time") or 0
        absolute_finish = int(start) + int(finish_time_ms)
        ok = engine.edit_finish_time(int(rid), absolute_finish)
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
        result_row = db._exec(
            "SELECT category_id FROM result WHERE id=?", (lap["result_id"],)
        ).fetchone()
        if result_row and result_row["category_id"]:
            if db.is_category_closed(result_row["category_id"]):
                return jsonify({"error": "Категория закрыта"}), 400
        return None

    @app.route("/api/judge/lap/<int:lap_id>", methods=["PUT"])
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
        _recalc_lap_timestamps(db, lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/lap/<int:lap_id>", methods=["DELETE"])
    def api_judge_delete_lap(lap_id):
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        err = _check_category_not_closed(lap)
        if err:
            return err
        db.delete_lap(lap_id)
        _renumber_laps(db, lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/manual-lap", methods=["POST"])
    def api_judge_manual_lap():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        rider = db.get_rider(int(rid))
        if rider and rider.get("category_id"):
            if db.is_category_closed(rider["category_id"]):
                return jsonify({"error": "Категория закрыта"}), 400
        result = engine.manual_lap(int(rid))
        if not result:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True, "result": result})

    @app.route("/api/judge/notes", methods=["GET"])
    def api_judge_notes_list():
        try:
            return jsonify(db.get_notes())
        except Exception:
            return jsonify([])

    @app.route("/api/judge/notes", methods=["POST"])
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
    def api_judge_notes_delete(nid):
        db.delete_note(nid)
        return jsonify({"ok": True})


def _recalc_lap_timestamps(db, result_id):
    result = db._exec(
        "SELECT start_time, status, penalty_time_ms FROM result WHERE id=?",
        (result_id,),
    ).fetchone()
    if not result:
        return
    laps = db.get_laps(result_id)
    current_ts = int(float(result["start_time"]))
    for lap in laps:
        current_ts += int(lap.get("lap_time") or 0)
        db._exec("UPDATE lap SET timestamp=? WHERE id=?", (current_ts, lap["id"]))
    db._commit()
    if result["status"] == "FINISHED" and laps:
        penalty_ms = result["penalty_time_ms"] or 0
        db.update_result(result_id, finish_time=current_ts + penalty_ms)


def _renumber_laps(db, result_id):
    laps = db.get_laps(result_id)
    for i, lap in enumerate(laps):
        new_num = 0 if i == 0 else i
        if lap["lap_number"] != new_num:
            db._exec("UPDATE lap SET lap_number=? WHERE id=?", (new_num, lap["id"]))
    db._commit()
    _recalc_lap_timestamps(db, result_id)
