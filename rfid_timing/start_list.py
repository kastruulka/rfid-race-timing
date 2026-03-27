import csv
import io
import time
from flask import (
    render_template, jsonify, request, Response,
)
from .database import Database
from .race_engine import RaceEngine


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
    def api_categories_create():
        data = request.get_json(force=True)
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "Название обязательно"}), 400
        laps = data.get("laps", 1)
        distance_km = data.get("distance_km", 0)
        cid = db.add_category(name=name, laps=laps, distance_km=distance_km)
        return jsonify({"ok": True, "id": cid})

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    def api_categories_update(cid):
        data = request.get_json(force=True)
        db.update_category(cid, **data)
        return jsonify({"ok": True})

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    def api_categories_delete(cid):
        ok = db.delete_category(cid)
        if not ok:
            return jsonify({"error":
                "Нельзя удалить — есть участники в этой категории"}), 400
        return jsonify({"ok": True})


    @app.route("/api/riders", methods=["GET"])
    def api_riders_list():
        cat_id = request.args.get("category_id", type=int)
        riders = db.get_riders_with_category(category_id=cat_id)
        return jsonify(riders)

    @app.route("/api/riders", methods=["POST"])
    def api_riders_create():
        data = request.get_json(force=True)
        number = data.get("number")
        last_name = data.get("last_name", "").strip()
        if not number or not last_name:
            return jsonify({"error":
                "Номер и фамилия обязательны"}), 400

        existing = db.get_rider_by_number(int(number))
        if existing:
            return jsonify({"error":
                f"Номер {number} уже занят"}), 400

        epc = data.get("epc")
        if epc:
            epc_existing = db.get_rider_by_epc(epc)
            if epc_existing:
                return jsonify({"error":
                    f"EPC уже привязан к #{epc_existing['number']}"}), 400

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

        cat_id = data.get("category_id")
        if cat_id is not None:
            try:
                cat_id = int(cat_id)
            except (ValueError, TypeError):
                cat_id = None
 
        race_id = db.get_current_race_id()
        if cat_id and race_id:
            existing_result = db.get_result_by_rider(rid)
            if not existing_result:
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
                    rider_id=rid,
                    category_id=cat_id,
                    start_time=start_time,
                    status="RACING",
                )

        return jsonify({"ok": True, "id": rid})

    @app.route("/api/riders/<int:rid>", methods=["PUT"])
    def api_riders_update(rid):
        data = request.get_json(force=True)

        if "number" in data:
            existing = db.get_rider_by_number(int(data["number"]))
            if existing and existing["id"] != rid:
                return jsonify({"error":
                    f"Номер {data['number']} уже занят"}), 400

        if "epc" in data and data["epc"]:
            epc_existing = db.get_rider_by_epc(data["epc"])
            if epc_existing and epc_existing["id"] != rid:
                return jsonify({"error":
                    f"EPC уже привязан к #{epc_existing['number']}"}), 400

        db.update_rider(rid, **data)

        if engine:
            engine.reload_epc_map()

        return jsonify({"ok": True})

    @app.route("/api/riders/<int:rid>", methods=["DELETE"])
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
        writer.writerow([
            "number", "last_name", "first_name", "birth_year",
            "city", "club", "category", "epc",
        ])
        for r in riders:
            writer.writerow([
                r["number"], r["last_name"], r["first_name"],
                r.get("birth_year", ""), r.get("city", ""),
                r.get("club", ""), r.get("category_name", ""),
                r.get("epc", ""),
            ])
        csv_data = output.getvalue()
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    "attachment; filename=start_list.csv"
            },
        )


    @app.route("/api/riders/import", methods=["POST"])
    def api_riders_import():
        if "file" not in request.files:
            return jsonify({"error": "Файл не найден"}), 400

        file = request.files["file"]
        try:
            text = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            file.seek(0)
            text = file.read().decode("cp1251")

        reader_csv = csv.DictReader(io.StringIO(text))
        imported = 0
        errors = []

        cat_cache = {}
        for c in db.get_categories():
            cat_cache[c["name"].lower().strip()] = c["id"]

        for i, row in enumerate(reader_csv, start=2):
            num_str = (row.get("number") or row.get("номер")
                       or row.get("Number") or "").strip()
            last_name = (row.get("last_name") or row.get("фамилия")
                         or row.get("Фамилия") or "").strip()

            if not num_str or not last_name:
                errors.append(f"Строка {i}: пропущена (нет номера/фамилии)")
                continue

            try:
                number = int(num_str)
            except ValueError:
                errors.append(f"Строка {i}: неверный номер '{num_str}'")
                continue

            if db.get_rider_by_number(number):
                errors.append(f"Строка {i}: номер {number} уже есть")
                continue

            first_name = (row.get("first_name") or row.get("имя")
                          or row.get("Имя") or "").strip()
            birth_year = None
            by_str = (row.get("birth_year") or row.get("год")
                      or row.get("Год") or "").strip()
            if by_str:
                try:
                    birth_year = int(by_str)
                except ValueError:
                    pass

            city = (row.get("city") or row.get("город")
                    or row.get("Город") or "").strip()
            club = (row.get("club") or row.get("команда")
                    or row.get("Команда") or row.get("клуб")
                    or "").strip()
            cat_name = (row.get("category") or row.get("категория")
                        or row.get("Категория") or "").strip()
            epc = (row.get("epc") or row.get("EPC") or "").strip() or None

            cat_id = None
            if cat_name:
                cat_key = cat_name.lower().strip()
                if cat_key in cat_cache:
                    cat_id = cat_cache[cat_key]
                else:
                    cat_id = db.add_category(name=cat_name)
                    cat_cache[cat_key] = cat_id

            if epc and db.get_rider_by_epc(epc):
                errors.append(
                    f"Строка {i}: EPC '{epc}' уже привязан")
                epc = None

            db.add_rider(
                number=number, last_name=last_name,
                first_name=first_name, birth_year=birth_year,
                city=city, club=club, category_id=cat_id, epc=epc,
            )
            imported += 1

        if engine:
            engine.reload_epc_map()

        result = {"ok": True, "imported": imported}
        if errors:
            result["warnings"] = errors
        return jsonify(result)