import io
import csv
import time
from flask import render_template, jsonify, request, Response
from .database import Database
from .race_engine import RaceEngine
from .request_helpers import get_json_body
from .settings import require_admin
from .csv_import import sanitize_for_export, parse_csv_text, import_riders


def register_start_list(app, db: Database, engine: RaceEngine = None):

    @app.route("/start-list")
    def start_list_page():
        return render_template("start_list.html")

    @app.route("/api/categories", methods=["GET"])
    def api_categories_list():
        cats = db.get_categories()
        for c in cats:
            riders = db.get_riders(category_id=c["id"])
            c["rider_count"] = len(riders)
        return jsonify(cats)

    @app.route("/api/categories", methods=["POST"])
    @require_admin
    def api_categories_create():
        data, err = get_json_body()
        if err:
            return err
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Название обязательно"}), 400
        laps = data.get("laps", 1)
        distance_km = data.get("distance_km", 0)
        cid = db.add_category(name=name, laps=laps, distance_km=distance_km)
        return jsonify({"ok": True, "id": cid})

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    @require_admin
    def api_categories_update(cid):
        data, err = get_json_body()
        if err:
            return err
        db.update_category(cid, **data)
        return jsonify({"ok": True})

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    @require_admin
    def api_categories_delete(cid):
        ok = db.delete_category(cid)
        if not ok:
            return jsonify(
                {"error": "Нельзя удалить — есть участники в этой категории"}
            ), 400
        return jsonify({"ok": True})

    @app.route("/api/riders", methods=["GET"])
    def api_riders_list():
        cat_id = request.args.get("category_id", type=int)
        riders = db.get_riders_with_category(category_id=cat_id)
        return jsonify(riders)

    @app.route("/api/riders", methods=["POST"])
    @require_admin
    def api_riders_create():
        data, err = get_json_body()
        if err:
            return err
        number = data.get("number")
        last_name = data.get("last_name", "").strip()
        if not number or not last_name:
            return jsonify({"error": "Номер и фамилия обязательны"}), 400

        existing = db.get_rider_by_number(int(number))
        if existing:
            return jsonify({"error": f"Номер {number} уже занят"}), 400

        epc = data.get("epc")
        if epc:
            epc_existing = db.get_rider_by_epc(epc)
            if epc_existing:
                return jsonify(
                    {"error": f"EPC уже привязан к #{epc_existing['number']}"}
                ), 400

        rid = db.add_rider(
            number=int(number),
            last_name=last_name,
            first_name=data.get("first_name", ""),
            birth_year=data.get("birth_year"),
            city=data.get("city", ""),
            club=data.get("club", ""),
            category_id=data.get("category_id"),
            epc=epc,
        )

        if engine:
            engine.reload_epc_map()

        _auto_enroll_rider(db, rid, data.get("category_id"))

        return jsonify({"ok": True, "id": rid})

    @app.route("/api/riders/<int:rid>", methods=["PUT"])
    @require_admin
    def api_riders_update(rid):
        data, err = get_json_body()
        if err:
            return err

        if "number" in data:
            existing = db.get_rider_by_number(int(data["number"]))
            if existing and existing["id"] != rid:
                return jsonify({"error": f"Номер {data['number']} уже занят"}), 400

        if "epc" in data and data["epc"]:
            epc_existing = db.get_rider_by_epc(data["epc"])
            if epc_existing and epc_existing["id"] != rid:
                return jsonify(
                    {"error": f"EPC уже привязан к #{epc_existing['number']}"}
                ), 400

        db.update_rider(rid, **data)

        if engine:
            engine.reload_epc_map()

        return jsonify({"ok": True})

    @app.route("/api/riders/<int:rid>", methods=["DELETE"])
    @require_admin
    def api_riders_delete(rid):
        ok = db.delete_rider(rid)
        if not ok:
            return jsonify({"error": "Не удалось удалить участника"}), 400
        if engine:
            engine.reload_epc_map()
        return jsonify({"ok": True})

    @app.route("/api/riders/export")
    def api_riders_export():
        riders = db.get_riders_with_category()
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
                "epc",
            ]
        )
        for r in riders:
            writer.writerow(
                [
                    sanitize_for_export(r["number"]),
                    sanitize_for_export(r["last_name"]),
                    sanitize_for_export(r["first_name"]),
                    sanitize_for_export(r.get("birth_year", "")),
                    sanitize_for_export(r.get("city", "")),
                    sanitize_for_export(r.get("club", "")),
                    sanitize_for_export(r.get("category_name", "")),
                    sanitize_for_export(r.get("epc", "")),
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


def _auto_enroll_rider(db: Database, rider_id: int, raw_cat_id):
    cat_id = None
    if raw_cat_id is not None:
        try:
            cat_id = int(raw_cat_id)
        except (ValueError, TypeError):
            return

    race_id = db.get_current_race_id()
    if not cat_id or not race_id:
        return

    existing_result = db.get_result_by_rider(rider_id)
    if existing_result:
        return

    others = db.get_results_by_category(cat_id)
    start_time = None
    for r in others:
        st = r.get("start_time")
        if st:
            start_time = st
            break

    if start_time is None:
        start_time = time.time() * 1000

    db.create_result(
        rider_id=rider_id,
        category_id=cat_id,
        start_time=start_time,
        status="RACING",
    )
