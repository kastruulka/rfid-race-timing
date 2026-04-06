import io
import csv
from datetime import datetime
from flask import render_template, jsonify, request, Response
from .database import Database
from .race_engine import RaceEngine
from .request_helpers import get_json_body, require_int
from .security.auth import require_admin
from .csv_import import sanitize_for_export, parse_csv_text, import_riders


MIN_BIRTH_YEAR = 1900
MAX_NUMBER = 99999
MAX_NAME_LENGTH = 80
MAX_TEXT_LENGTH = 120
MAX_EPC_LENGTH = 64
MAX_CATEGORY_LAPS = 1000
MAX_CATEGORY_DISTANCE_KM = 1000.0


def _current_year() -> int:
    return datetime.now().year


def _clean_optional_text(value, *, max_length: int) -> str:
    return (value or "").strip()[:max_length]


def _parse_bool(value, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _validate_category_payload(data: dict) -> tuple[dict | None, tuple | None]:
    name = _clean_optional_text(data.get("name"), max_length=MAX_NAME_LENGTH)
    if not name:
        return None, (jsonify({"error": "Название обязательно"}), 400)

    try:
        laps = int(data.get("laps", 1))
    except (TypeError, ValueError):
        return None, (
            jsonify({"error": "Количество кругов должно быть целым числом"}),
            400,
        )

    if not (1 <= laps <= MAX_CATEGORY_LAPS):
        return None, (
            jsonify(
                {"error": f"Количество кругов должно быть от 1 до {MAX_CATEGORY_LAPS}"}
            ),
            400,
        )

    try:
        distance_km = float(data.get("distance_km", 0))
    except (TypeError, ValueError):
        return None, (jsonify({"error": "Дистанция круга должна быть числом"}), 400)

    if not (0 <= distance_km <= MAX_CATEGORY_DISTANCE_KM):
        return None, (
            jsonify(
                {
                    "error": f"Дистанция круга должна быть в диапазоне от 0 до {MAX_CATEGORY_DISTANCE_KM} км"
                }
            ),
            400,
        )

    return {
        "name": name,
        "laps": laps,
        "distance_km": distance_km,
        "has_warmup_lap": _parse_bool(data.get("has_warmup_lap"), default=True),
    }, None


def _validate_rider_payload(data: dict) -> tuple[dict | None, tuple | None]:
    number, err = require_int(data, "number", "Номер обязателен")
    if err:
        return None, err

    if not (1 <= number <= MAX_NUMBER):
        return None, (
            jsonify({"error": f"Стартовый номер должен быть от 1 до {MAX_NUMBER}"}),
            400,
        )

    last_name = _clean_optional_text(data.get("last_name"), max_length=MAX_NAME_LENGTH)
    if not last_name:
        return None, (jsonify({"error": "Номер и фамилия обязательны"}), 400)

    birth_year = None
    birth_year_raw = data.get("birth_year")
    if birth_year_raw not in (None, "", 0, "0"):
        try:
            birth_year = int(birth_year_raw)
        except (TypeError, ValueError):
            return None, (
                jsonify({"error": "Год рождения должен быть целым числом"}),
                400,
            )

        current_year = _current_year()
        if not (MIN_BIRTH_YEAR <= birth_year <= current_year):
            return None, (
                jsonify(
                    {
                        "error": f"Год рождения должен быть в диапазоне {MIN_BIRTH_YEAR}-{current_year}"
                    }
                ),
                400,
            )

    category_id = None
    category_id_raw = data.get("category_id")
    if category_id_raw not in (None, "", 0, "0"):
        try:
            category_id = int(category_id_raw)
        except (TypeError, ValueError):
            return None, (jsonify({"error": "Категория указана некорректно"}), 400)

    return {
        "number": number,
        "last_name": last_name,
        "first_name": _clean_optional_text(
            data.get("first_name"), max_length=MAX_NAME_LENGTH
        ),
        "birth_year": birth_year,
        "city": _clean_optional_text(data.get("city"), max_length=MAX_TEXT_LENGTH),
        "club": _clean_optional_text(data.get("club"), max_length=MAX_TEXT_LENGTH),
        "category_id": category_id,
        "epc": _clean_optional_text(data.get("epc"), max_length=MAX_EPC_LENGTH) or None,
    }, None


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
        payload, err = _validate_category_payload(data)
        if err:
            return err
        cid = db.add_category(**payload)
        return jsonify({"ok": True, "id": cid})

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    @require_admin
    def api_categories_update(cid):
        data, err = get_json_body()
        if err:
            return err
        payload, err = _validate_category_payload(data)
        if err:
            return err
        db.update_category(cid, **payload)
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
        payload, err = _validate_rider_payload(data)
        if err:
            return err
        number = payload["number"]

        existing = db.get_rider_by_number(number)
        if existing:
            return jsonify({"error": f"Номер {number} уже занят"}), 400

        epc = payload["epc"]
        if epc:
            epc_existing = db.get_rider_by_epc(epc)
            if epc_existing:
                return jsonify(
                    {"error": f"EPC уже привязан к #{epc_existing['number']}"}
                ), 400

        rid = db.add_rider(**payload)

        if engine:
            engine.reload_epc_map()

        _auto_enroll_rider(db, rid, payload["category_id"])

        return jsonify({"ok": True, "id": rid})

    @app.route("/api/riders/<int:rid>", methods=["PUT"])
    @require_admin
    def api_riders_update(rid):
        data, err = get_json_body()
        if err:
            return err
        payload, err = _validate_rider_payload(data)
        if err:
            return err

        existing = db.get_rider_by_number(payload["number"])
        if existing and existing["id"] != rid:
            return jsonify({"error": f"Номер {payload['number']} уже занят"}), 400

        if payload["epc"]:
            epc_existing = db.get_rider_by_epc(payload["epc"])
            if epc_existing and epc_existing["id"] != rid:
                return jsonify(
                    {"error": f"EPC уже привязан к #{epc_existing['number']}"}
                ), 400

        db.update_rider(rid, **payload)

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
    return
