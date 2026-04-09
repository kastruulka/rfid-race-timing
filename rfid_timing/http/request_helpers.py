import logging
from typing import Any, Optional, Tuple

from flask import jsonify, request

logger = logging.getLogger(__name__)


def get_json_body() -> tuple:
    data = request.get_json(silent=True)
    if data is None:
        return None, (jsonify({"error": "Невалидный JSON"}), 400)
    return data, None


def require_int(data: dict, key: str, label: str = "") -> Tuple[Optional[int], Any]:
    raw = data.get(key)
    if raw is None:
        msg = label or f"Параметр '{key}' обязателен"
        return None, (jsonify({"error": msg}), 400)
    try:
        return int(raw), None
    except (ValueError, TypeError):
        msg = label or f"Параметр '{key}' должен быть числом"
        return None, (jsonify({"error": msg}), 400)


def make_require_engine(engine):
    def require_engine():
        if not engine:
            return jsonify({"error": "Engine unavailable"}), 500
        return None

    return require_engine


def safe_error(e: Exception, context: str = "") -> tuple:
    logger.exception("Внутренняя ошибка%s", f" ({context})" if context else "")
    return jsonify({"error": "Внутренняя ошибка сервера"}), 500


def safe_400(e: Exception, context: str = "") -> tuple:
    if not isinstance(e, (ValueError, TypeError)):
        return safe_error(e, context)
    logger.warning("Ошибка запроса%s: %s", f" ({context})" if context else "", e)
    return jsonify({"error": "Неверный запрос"}), 400
