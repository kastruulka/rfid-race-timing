from flask import jsonify

from ...database.database import Database
from ...http.request_helpers import get_json_body
from ...security.auth import require_admin
from .start_list_validators import validate_category_payload


def register_start_list_category_routes(app, db: Database):
    @app.route("/api/categories", methods=["GET"])
    def api_categories_list():
        cats = db.categories_repo.get_categories()
        for category in cats:
            riders = db.riders_repo.get_riders(category_id=category["id"])
            category["rider_count"] = len(riders)
        return jsonify(cats)

    @app.route("/api/categories", methods=["POST"])
    @require_admin
    def api_categories_create():
        data, err = get_json_body()
        if err:
            return err
        payload, err = validate_category_payload(data)
        if err:
            return err
        cid = db.categories_repo.add_category(**payload)
        return jsonify({"ok": True, "id": cid})

    @app.route("/api/categories/<int:cid>", methods=["PUT"])
    @require_admin
    def api_categories_update(cid):
        data, err = get_json_body()
        if err:
            return err
        payload, err = validate_category_payload(data)
        if err:
            return err
        db.categories_repo.update_category(cid, **payload)
        return jsonify({"ok": True})

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    @require_admin
    def api_categories_delete(cid):
        ok = db.categories_repo.delete_category(cid)
        if not ok:
            return (
                jsonify(
                    {
                        "error": "Нельзя удалить категорию: в ней есть участники или данные гонки"
                    }
                ),
                400,
            )
        return jsonify({"ok": True})
