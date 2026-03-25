import time
from flask import render_template, jsonify, request
from .database import Database
from .race_engine import RaceEngine


def register_judge(app, db: Database, engine: RaceEngine = None):

    @app.route("/judge")
    def judge_page():
        return render_template("judge.html")

    @app.route("/api/judge/rider-status/<int:rid>", methods=["GET"])
    def api_judge_rider_status(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify({"status": "DNS", "total_time_ms": None,
                            "dnf_reason": ""})
        total_time_ms = None
        if result.get("finish_time") and result.get("start_time"):
            total_time_ms = int(result["finish_time"]) - int(result["start_time"])
        return jsonify({
            "status": result["status"],
            "total_time_ms": total_time_ms,
            "finish_time": result.get("finish_time"),
            "start_time": result.get("start_time"),
            "dnf_reason": result.get("dnf_reason", ""),
            "penalty_time_ms": result.get("penalty_time_ms") or 0,
            "extra_laps": result.get("extra_laps") or 0,
        })

    @app.route("/api/judge/dnf", methods=["POST"])
    def api_judge_dnf():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dnf(int(rid),
                            reason_code=data.get("reason_code", ""),
                            reason_text=data.get("reason_text", ""))
        if not ok:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/dsq", methods=["POST"])
    def api_judge_dsq():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dsq(int(rid), reason=data.get("reason", ""))
        if not ok:
            return jsonify({"error": "Невозможно"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/time-penalty", methods=["POST"])
    def api_judge_time_penalty():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        seconds = data.get("seconds", 0)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_time_penalty(
            int(rid), float(seconds), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/extra-lap", methods=["POST"])
    def api_judge_extra_lap():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        laps = data.get("laps", 1)
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_extra_lap(
            int(rid), int(laps), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/warning", methods=["POST"])
    def api_judge_warning():
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid or not engine:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.add_warning(
            int(rid), reason=data.get("reason", ""))
        if not result:
            return jsonify({"error": "Участник не найден"}), 400
        return jsonify({"ok": True, "penalty": result})

    @app.route("/api/judge/penalty/<int:pid>", methods=["DELETE"])
    def api_judge_delete_penalty(pid):
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        ok = engine.remove_penalty(pid)
        if not ok:
            return jsonify({"error": "Штраф не найден"}), 404
        return jsonify({"ok": True})

    @app.route("/api/judge/log", methods=["GET"])
    def api_judge_log():
        try:
            penalties = db.get_penalties_by_race()
            return jsonify(penalties)
        except Exception:
            return jsonify([])

    @app.route("/api/judge/mass-start", methods=["POST"])
    def api_judge_mass_start():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        try:
            info = engine.mass_start(int(cat_id))
            return jsonify({"ok": True, "info": info})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/judge/unfinish-rider", methods=["POST"])
    def api_judge_unfinish_rider():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.unfinish_rider(int(rid))
        if not ok:
            return jsonify({"error":
                "Невозможно — участник не FINISHED или гонка закрыта"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/finish-race", methods=["POST"])
    def api_judge_finish_race():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        result = engine.finish_all(int(cat_id))
        return jsonify({"ok": True, **result})

    @app.route("/api/judge/edit-finish-time", methods=["POST"])
    def api_judge_edit_finish_time():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        data = request.get_json(force=True)
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
            return jsonify({"error":
                "Невозможно — гонка закрыта или участник не FINISHED"}), 400
        return jsonify({"ok": True})

    @app.route("/api/judge/notes", methods=["GET"])
    def api_judge_notes_list():
        try:
            return jsonify(db.get_notes())
        except Exception:
            return jsonify([])

    @app.route("/api/judge/notes", methods=["POST"])
    def api_judge_notes_create():
        data = request.get_json(force=True)
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

    @app.route("/api/judge/rider-laps/<int:rid>", methods=["GET"])
    def api_judge_rider_laps(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify([])
        return jsonify(db.get_laps(result["id"]))

    @app.route("/api/judge/lap/<int:lap_id>", methods=["PUT"])
    def api_judge_update_lap(lap_id):
        if db.is_race_closed():
            return jsonify({"error": "Гонка закрыта"}), 400
        data = request.get_json(force=True)
        lap_time_ms = data.get("lap_time_ms")
        if lap_time_ms is None:
            return jsonify({"error": "Время не указано"}), 400
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        db.update_lap(lap_id, lap_time=int(lap_time_ms), source="EDITED")
        _recalc_lap_timestamps(db, lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/lap/<int:lap_id>", methods=["DELETE"])
    def api_judge_delete_lap(lap_id):
        if db.is_race_closed():
            return jsonify({"error": "Гонка закрыта"}), 400
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        db.delete_lap(lap_id)
        _renumber_laps(db, lap["result_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/manual-lap", methods=["POST"])
    def api_judge_manual_lap():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        if db.is_race_closed():
            return jsonify({"error": "Гонка закрыта"}), 400
        data = request.get_json(force=True)
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.manual_lap(int(rid))
        if not result:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True, "result": result})


def _recalc_lap_timestamps(db, result_id):
    result = db._exec(
        "SELECT start_time, status, penalty_time_ms FROM result WHERE id=?",
        (result_id,)).fetchone()
    if not result:
        return
    laps = db.get_laps(result_id)
    current_ts = int(float(result["start_time"]))
    for l in laps:
        current_ts += int(l.get("lap_time") or 0)
        db._exec("UPDATE lap SET timestamp=? WHERE id=?",
                 (current_ts, l["id"]))
    db._commit()
    if result["status"] == "FINISHED" and laps:
        penalty_ms = result["penalty_time_ms"] or 0
        db.update_result(result_id, finish_time=current_ts + penalty_ms)


def _renumber_laps(db, result_id):
    laps = db.get_laps(result_id)
    for i, l in enumerate(laps):
        new_num = 0 if i == 0 else i
        if l["lap_number"] != new_num:
            db._exec("UPDATE lap SET lap_number=? WHERE id=?",
                     (new_num, l["id"]))
    db._commit()
    _recalc_lap_timestamps(db, result_id)