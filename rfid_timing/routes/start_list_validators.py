from datetime import datetime

from flask import jsonify

from ..http.request_helpers import require_int

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


def validate_category_payload(data: dict) -> tuple[dict | None, tuple | None]:
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


def validate_rider_payload(data: dict) -> tuple[dict | None, tuple | None]:
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
