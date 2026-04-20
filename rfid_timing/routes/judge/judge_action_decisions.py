import logging

from flask import jsonify

from ...database.database import Database
from ...http import actions
from ...http.request_helpers import get_json_body, require_int, safe_error
from ...app.race_engine import RaceEngine
from ...security.auth import require_admin
from .judge_action_helpers import (
    check_penalty_category_not_closed,
    check_rider_category_not_closed,
)

logger = logging.getLogger(__name__)


def register_judge_decision_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
    require_engine=None,
):
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
        err = check_rider_category_not_closed(db, rid)
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
        err = check_rider_category_not_closed(db, rid)
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
        err = check_rider_category_not_closed(db, rid)
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
        err = check_rider_category_not_closed(db, rid)
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
        err = check_rider_category_not_closed(db, rid)
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
        err = check_penalty_category_not_closed(db, pid)
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
        except Exception as e:
            logger.exception("judge_log failed")
            return safe_error(e, "judge_log")

    @app.route("/api/judge/mass-start", methods=["POST"])
    @require_admin
    def api_judge_mass_start():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err

        category_id = data.get("category_id")
        category_ids = data.get("category_ids")

        if category_id is None and not category_ids:
            return jsonify({"error": "Категория не выбрана"}), 400

        if category_id is not None:
            category_id, err = require_int(data, "category_id", "Категория не выбрана")
            if err:
                return err

        normalized_ids = None
        if category_ids is not None:
            if not isinstance(category_ids, list):
                return jsonify({"error": "Список категорий должен быть массивом"}), 400
            try:
                normalized_ids = [int(value) for value in category_ids]
            except (TypeError, ValueError):
                return (
                    jsonify(
                        {"error": "Список категорий содержит некорректные значения"}
                    ),
                    400,
                )

        try:
            body, status = actions.action_mass_start(
                engine,
                category_id=category_id,
                category_ids=normalized_ids,
            )
            return jsonify(body), status
        except Exception as e:
            return safe_error(e, "judge_mass_start")

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
        try:
            body, status = actions.action_individual_start(engine, rid)
            return jsonify(body), status
        except Exception as e:
            return safe_error(e, "judge_individual_start")
