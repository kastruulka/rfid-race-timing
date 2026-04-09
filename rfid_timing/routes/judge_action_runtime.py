import logging

from flask import jsonify

from ..database import Database
from ..http import actions
from ..http.request_helpers import get_json_body, require_int, safe_error
from ..race_engine import RaceEngine
from ..security.auth import require_admin
from .judge_action_helpers import check_lap_category_not_closed

logger = logging.getLogger(__name__)


def register_judge_runtime_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    require_engine=None,
):
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
            return (
                jsonify(
                    {"error": "Невозможно - участник не FINISHED или категория закрыта"}
                ),
                400,
            )
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
            return safe_error(e, "reset_category")

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
            return (
                jsonify(
                    {"error": "Невозможно - категория закрыта или участник не FINISHED"}
                ),
                400,
            )
        return jsonify({"ok": True})

    @app.route("/api/judge/rider-laps/<int:rid>", methods=["GET"])
    def api_judge_rider_laps(rid):
        result = db.get_result_by_rider(rid)
        if not result:
            return jsonify([])
        return jsonify(db.get_laps(result["id"]))

    @app.route("/api/judge/lap/<int:lap_id>", methods=["PUT"])
    @require_admin
    def api_judge_update_lap(lap_id):
        lap = db.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        err = check_lap_category_not_closed(db, lap)
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
        err = check_lap_category_not_closed(db, lap)
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
        except Exception as e:
            logger.exception("judge_notes_list failed")
            return safe_error(e, "judge_notes_list")

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
