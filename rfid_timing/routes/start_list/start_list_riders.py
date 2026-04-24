import csv
import io

from flask import Response, jsonify, request

from ...integrations.csv_import import (
    import_riders,
    parse_csv_text,
    sanitize_for_export,
)
from ...database.database import Database
from ...app.race_engine import RaceEngine
from ...http.request_helpers import get_json_body
from ...security.auth import require_admin
from .start_list_validators import validate_rider_payload


def register_start_list_rider_routes(
    app,
    db: Database,
    engine: RaceEngine = None,
):
    @app.route("/api/riders", methods=["GET"])
    def api_riders_list():
        cat_id = request.args.get("category_id", type=int)
        riders = db.riders_repo.get_riders_with_category(category_id=cat_id)
        return jsonify(riders)

    @app.route("/api/riders", methods=["POST"])
    @require_admin
    def api_riders_create():
        data, err = get_json_body()
        if err:
            return err
        payload, err = validate_rider_payload(data)
        if err:
            return err
        number = payload["number"]

        existing = db.riders_repo.get_rider_by_number(number)
        if existing:
            return jsonify({"error": f"Номер {number} уже занят"}), 400

        epc = payload["epc"]
        if epc:
            epc_existing = db.riders_repo.get_rider_by_epc(epc)
            if epc_existing:
                return (
                    jsonify({"error": f"EPC уже привязан к #{epc_existing['number']}"}),
                    400,
                )

        rid = db.riders_repo.add_rider(**payload)

        if engine:
            engine.reload_epc_map()

        return jsonify({"ok": True, "id": rid})

    @app.route("/api/riders/<int:rid>", methods=["PUT"])
    @require_admin
    def api_riders_update(rid):
        data, err = get_json_body()
        if err:
            return err
        payload, err = validate_rider_payload(data)
        if err:
            return err

        existing = db.riders_repo.get_rider_by_number(payload["number"])
        if existing and existing["id"] != rid:
            return jsonify({"error": f"Номер {payload['number']} уже занят"}), 400

        if payload["epc"]:
            epc_existing = db.riders_repo.get_rider_by_epc(payload["epc"])
            if epc_existing and epc_existing["id"] != rid:
                return (
                    jsonify({"error": f"EPC уже привязан к #{epc_existing['number']}"}),
                    400,
                )

        db.riders_repo.update_rider(rid, **payload)

        if engine:
            engine.reload_epc_map()

        return jsonify({"ok": True})

    @app.route("/api/riders/<int:rid>", methods=["DELETE"])
    @require_admin
    def api_riders_delete(rid):
        ok = db.riders_repo.delete_rider(rid)
        if not ok:
            return jsonify({"error": "Не удалось удалить участника"}), 400
        if engine:
            engine.reload_epc_map()
        return jsonify({"ok": True})

    @app.route("/api/riders/export")
    def api_riders_export():
        riders = db.riders_repo.get_riders_with_category()
        categories_by_id = {
            category["id"]: category for category in db.categories_repo.get_categories()
        }
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "number",
                "last_name",
                "first_name",
                "birth_year",
                "city",
                "club",
                "category",
                "category_laps",
                "category_distance_km",
                "category_has_warmup_lap",
                "category_finish_mode",
                "category_time_limit_sec",
                "epc",
            ]
        )
        for rider in riders:
            category = categories_by_id.get(rider.get("category_id"))
            writer.writerow(
                [
                    sanitize_for_export(rider["number"]),
                    sanitize_for_export(rider["last_name"]),
                    sanitize_for_export(rider["first_name"]),
                    sanitize_for_export(rider.get("birth_year", "")),
                    sanitize_for_export(rider.get("city", "")),
                    sanitize_for_export(rider.get("club", "")),
                    sanitize_for_export(rider.get("category_name", "")),
                    sanitize_for_export(category.get("laps", "") if category else ""),
                    sanitize_for_export(
                        category.get("distance_km", "") if category else ""
                    ),
                    sanitize_for_export(
                        category.get("has_warmup_lap", "") if category else ""
                    ),
                    sanitize_for_export(
                        category.get("finish_mode", "") if category else ""
                    ),
                    sanitize_for_export(
                        category.get("time_limit_sec", "") if category else ""
                    ),
                    sanitize_for_export(rider.get("epc", "")),
                ]
            )
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=start_list.csv"},
        )

    @app.route("/api/riders/import", methods=["POST"])
    @require_admin
    def api_riders_import():
        if "file" not in request.files:
            return jsonify({"error": "Файл не найден"}), 400

        file = request.files["file"]
        raw_bytes = file.read()
        if not raw_bytes:
            return jsonify({"error": "Файл пуст"}), 400

        csv_text = parse_csv_text(raw_bytes)
        result = import_riders(db, csv_text)

        if engine:
            engine.reload_epc_map()

        response = {"ok": True, "imported": result.imported, "skipped": result.skipped}
        if result.errors:
            response["ok"] = False
            response["errors"] = result.errors
            return jsonify(response), 400
        if result.warnings:
            response["warnings"] = result.warnings
        return jsonify(response)
