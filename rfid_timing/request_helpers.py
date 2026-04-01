import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)


def get_json_body() -> tuple:
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"error": "Невалидный JSON"}), 400)
    return data, None


def safe_error(e: Exception, context: str = "") -> tuple:
    logger.exception("Внутренняя ошибка%s", f" ({context})" if context else "")
    return jsonify({"error": "Внутренняя ошибка сервера"}), 500


def safe_400(e: Exception, context: str = "") -> tuple:
    logger.warning("Ошибка запроса%s: %s", f" ({context})" if context else "", e)
    return jsonify({"error": "Неверный запрос"}), 400
