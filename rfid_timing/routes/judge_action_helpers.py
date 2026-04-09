from flask import jsonify

from ..database import Database


def check_rider_category_not_closed(db: Database, rider_id: int):
    result = db.get_result_by_rider(rider_id)
    category_id = result.get("category_id") if result else None
    if category_id and db.is_category_closed(category_id):
        return jsonify({"error": "Категория закрыта"}), 400
    return None


def check_penalty_category_not_closed(db: Database, penalty_id: int):
    penalty = db.get_penalty_by_id(penalty_id)
    if not penalty:
        return None
    result = db.get_result_by_id(penalty["result_id"])
    category_id = result.get("category_id") if result else None
    if category_id and db.is_category_closed(category_id):
        return jsonify({"error": "Категория закрыта"}), 400
    return None


def check_lap_category_not_closed(db: Database, lap: dict):
    category_id = db.get_category_for_result(lap["result_id"])
    if category_id and db.is_category_closed(category_id):
        return jsonify({"error": "Категория закрыта"}), 400
    return None
