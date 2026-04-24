import logging

from flask import jsonify

from ...database.database import Database
from ...http import actions
from ...http.request_helpers import get_json_body, require_int, safe_error
from ...app.race_engine import RaceEngine
from ...security.auth import require_admin
from ...domain.timing import is_time_limit_mode, lap_times_fit_time_limit
from ...services.results.result_state_service import ResultStateService
from .judge_action_helpers import check_lap_category_not_closed

logger = logging.getLogger(__name__)


def register_judge_runtime_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    require_engine=None,
):
    result_states = ResultStateService(db)

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
        result = db.results_repo.get_result_by_rider(rid)
        if not result or result["status"] != "FINISHED":
            return jsonify({"error": "Участник не FINISHED"}), 400
        start = result.get("start_time") or 0
        absolute_finish = int(start) + int(finish_time_ms)
        try:
            ok = engine.edit_finish_time(rid, absolute_finish)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
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
        result = db.results_repo.get_result_by_rider(rid)
        if not result:
            return jsonify([])
        return jsonify(db.laps_repo.get_laps(result["id"]))

    @app.route("/api/judge/lap/<int:lap_id>", methods=["PUT"])
    @require_admin
    def api_judge_update_lap(lap_id):
        lap = db.laps_repo.get_lap_by_id(lap_id)
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
        result = db.results_repo.get_result_by_id(lap["result_id"])
        category = (
            db.categories_repo.get_category(result["category_id"]) if result else None
        )
        if category and is_time_limit_mode(category):
            laps = db.laps_repo.get_laps(lap["result_id"])
            candidate_times = []
            for current_lap in laps:
                if current_lap["id"] == lap_id:
                    candidate_times.append(int(lap_time_ms))
                else:
                    candidate_times.append(int(current_lap.get("lap_time") or 0))
            if not lap_times_fit_time_limit(category, candidate_times):
                return (
                    jsonify(
                        {
                            "error": "Новое время круга выводит участника за лимит времени категории"
                        }
                    ),
                    400,
                )
        db.laps_repo.update_lap(lap_id, lap_time=int(lap_time_ms), source="EDITED")
        db.laps_repo.recalc_lap_timestamps(lap["result_id"])
        if result:
            result_states.sync_projected_state(result["id"])
            if result.get("category_id"):
                result_states.assign_places(result["category_id"])
        return jsonify({"ok": True})

    @app.route("/api/judge/lap/<int:lap_id>", methods=["DELETE"])
    @require_admin
    def api_judge_delete_lap(lap_id):
        lap = db.laps_repo.get_lap_by_id(lap_id)
        if not lap:
            return jsonify({"error": "Круг не найден"}), 404
        err = check_lap_category_not_closed(db, lap)
        if err:
            return err
        result = db.results_repo.get_result_by_id(lap["result_id"])
        db.laps_repo.delete_lap(lap_id)
        db.laps_repo.renumber_laps(lap["result_id"])
        if result:
            result_states.sync_projected_state(result["id"])
            if result.get("category_id"):
                result_states.assign_places(result["category_id"])
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
        rider = db.riders_repo.get_rider(rid)
        if rider and rider.get("category_id"):
            if db.category_state_repo.is_category_closed(rider["category_id"]):
                return jsonify({"error": "Категория закрыта"}), 400
        body, status = actions.action_manual_lap(engine, rid)
        return jsonify(body), status

    @app.route("/api/judge/notes", methods=["GET"])
    def api_judge_notes_list():
        try:
            return jsonify(db.notes_repo.get_notes())
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
        nid = db.notes_repo.add_note(text=text, rider_id=int(rid) if rid else None)
        return jsonify({"ok": True, "id": nid})

    @app.route("/api/judge/notes/<int:nid>", methods=["DELETE"])
    @require_admin
    def api_judge_notes_delete(nid):
        db.notes_repo.delete_note(nid)
        return jsonify({"ok": True})
