import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from ..database.database import Database

logger = logging.getLogger(__name__)


_COLUMN_ALIASES: Dict[str, str] = {
    "number": "number",
    "last_name": "last_name",
    "first_name": "first_name",
    "birth_year": "birth_year",
    "city": "city",
    "club": "club",
    "category": "category",
    "category_laps": "category_laps",
    "category_distance_km": "category_distance_km",
    "category_has_warmup_lap": "category_has_warmup_lap",
    "category_finish_mode": "category_finish_mode",
    "category_time_limit_sec": "category_time_limit_sec",
    "epc": "epc",
    "номер": "number",
    "фамилия": "last_name",
    "имя": "first_name",
    "год": "birth_year",
    "год_рождения": "birth_year",
    "город": "city",
    "клуб": "club",
    "команда": "club",
    "категория": "category",
    "круги": "category_laps",
    "кругов": "category_laps",
    "дистанция": "category_distance_km",
    "дистанция_км": "category_distance_km",
    "разгонный_круг": "category_has_warmup_lap",
    "Number": "number",
    "Category": "category",
    "CategoryLaps": "category_laps",
    "CategoryDistanceKm": "category_distance_km",
    "CategoryWarmupLap": "category_has_warmup_lap",
    "CategoryFinishMode": "category_finish_mode",
    "CategoryTimeLimitSec": "category_time_limit_sec",
    "EPC": "epc",
}

_REQUIRED_COLUMNS = {"number", "last_name"}

MAX_ROWS = 5000
MAX_NUMBER = 99999
MIN_BIRTH_YEAR = 1920
MAX_FIELD_LEN = 200
MAX_CATEGORY_LAPS = 1000
MAX_CATEGORY_DISTANCE_KM = 1000.0
MAX_CATEGORY_TIME_LIMIT_SEC = 24 * 60 * 60

_FORMULA_CHARS = frozenset("=+-@\t\r")


def sanitize_cell(value: str) -> str:
    if not value:
        return value
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    if cleaned and cleaned[0] in _FORMULA_CHARS:
        cleaned = "'" + cleaned
    return cleaned.strip()


def sanitize_for_export(value) -> str:
    s = str(value) if value is not None else ""
    return sanitize_cell(s)


@dataclass
class ImportResult:
    imported: int = 0
    skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def parse_csv_text(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw_bytes.decode("cp1251")


def _normalize_columns(fieldnames: List[str]) -> Dict[str, str]:
    mapping = {}
    for name in fieldnames:
        key = name.strip()
        canonical = _COLUMN_ALIASES.get(key)
        if canonical:
            mapping[key] = canonical
    return mapping


def _validate_schema(col_map: Dict[str, str]) -> Optional[str]:
    found = set(col_map.values())
    missing = _REQUIRED_COLUMNS - found
    if missing:
        labels = {"number": "номер", "last_name": "фамилия"}
        names = ", ".join(labels.get(m, m) for m in sorted(missing))
        return f"Не найдены обязательные столбцы: {names}"
    return None


def _get_field(row: dict, col_map: Dict[str, str], canonical: str) -> str:
    for orig, canon in col_map.items():
        if canon == canonical:
            val = row.get(orig, "")
            return sanitize_cell(val.strip()) if val else ""
    return ""


def get_max_birth_year() -> int:
    return date.today().year


def _parse_optional_int(value: str) -> Optional[int]:
    if not value:
        return None
    return int(value)


def _parse_optional_float(value: str) -> Optional[float]:
    if not value:
        return None
    normalized = value.replace(",", ".")
    return float(normalized)


def _parse_optional_bool(value: str) -> Optional[bool]:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "да"}:
        return True
    if normalized in {"0", "false", "no", "off", "нет"}:
        return False
    raise ValueError(value)


def import_riders(db: Database, csv_text: str) -> ImportResult:
    result = ImportResult()

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        result.errors.append("Файл пуст или не содержит заголовков")
        return result

    col_map = _normalize_columns(reader.fieldnames)
    schema_err = _validate_schema(col_map)
    if schema_err:
        result.errors.append(schema_err)
        found_names = sorted(set(col_map.values()))
        if found_names:
            result.errors.append(f"Распознанные столбцы: {', '.join(found_names)}")
        result.errors.append(f"Столбцы в файле: {', '.join(reader.fieldnames)}")
        return result

    cat_cache: Dict[str, Dict] = {}
    for category in db.get_categories():
        cat_cache[category["name"].lower().strip()] = dict(category)

    for i, row in enumerate(reader, start=2):
        if result.imported + result.skipped >= MAX_ROWS:
            result.warnings.append(
                f"Достигнут лимит {MAX_ROWS} строк, остальные пропущены"
            )
            break

        num_str = _get_field(row, col_map, "number")
        last_name = _get_field(row, col_map, "last_name")

        if not num_str or not last_name:
            result.warnings.append(f"Строка {i}: пропущена (нет номера/фамилии)")
            result.skipped += 1
            continue

        try:
            number = int(num_str)
        except ValueError:
            result.warnings.append(f"Строка {i}: неверный номер '{num_str}'")
            result.skipped += 1
            continue

        if number <= 0 or number > MAX_NUMBER:
            result.warnings.append(
                f"Строка {i}: номер {number} вне диапазона 1-{MAX_NUMBER}"
            )
            result.skipped += 1
            continue

        if db.get_rider_by_number(number):
            result.warnings.append(f"Строка {i}: номер {number} уже есть")
            result.skipped += 1
            continue

        if len(last_name) > MAX_FIELD_LEN:
            result.warnings.append(f"Строка {i}: фамилия слишком длинная")
            result.skipped += 1
            continue

        first_name = _get_field(row, col_map, "first_name")[:MAX_FIELD_LEN]

        birth_year = None
        by_str = _get_field(row, col_map, "birth_year")
        if by_str:
            try:
                birth_year = int(by_str)
                max_birth_year = get_max_birth_year()
                if birth_year < MIN_BIRTH_YEAR or birth_year > max_birth_year:
                    result.warnings.append(
                        f"Строка {i}: год рождения {birth_year} вне диапазона {MIN_BIRTH_YEAR}-{max_birth_year} - пропущен"
                    )
                    birth_year = None
            except ValueError:
                result.warnings.append(
                    f"Строка {i}: неверный год рождения '{by_str}' - пропущен"
                )

        city = _get_field(row, col_map, "city")[:MAX_FIELD_LEN]
        club = _get_field(row, col_map, "club")[:MAX_FIELD_LEN]
        cat_name = _get_field(row, col_map, "category")[:MAX_FIELD_LEN]
        epc = _get_field(row, col_map, "epc")[:MAX_FIELD_LEN] or None

        cat_id = None
        if cat_name:
            cat_key = cat_name.lower().strip()
            category = cat_cache.get(cat_key)

            if category is None:
                laps = 1
                laps_str = _get_field(row, col_map, "category_laps")
                if laps_str:
                    try:
                        laps = _parse_optional_int(laps_str) or 1
                        if laps < 1 or laps > MAX_CATEGORY_LAPS:
                            raise ValueError(laps_str)
                    except ValueError:
                        result.warnings.append(
                            f"Строка {i}: неверное число кругов '{laps_str}' для категории '{cat_name}', использовано значение 1"
                        )
                        laps = 1

                distance_km = 0.0
                distance_str = _get_field(row, col_map, "category_distance_km")
                if distance_str:
                    try:
                        distance_km = _parse_optional_float(distance_str) or 0.0
                        if distance_km < 0 or distance_km > MAX_CATEGORY_DISTANCE_KM:
                            raise ValueError(distance_str)
                    except ValueError:
                        result.warnings.append(
                            f"Строка {i}: неверная дистанция '{distance_str}' для категории '{cat_name}', использовано значение 0"
                        )
                        distance_km = 0.0

                has_warmup_lap = True
                warmup_str = _get_field(row, col_map, "category_has_warmup_lap")
                if warmup_str:
                    try:
                        parsed = _parse_optional_bool(warmup_str)
                        if parsed is not None:
                            has_warmup_lap = parsed
                    except ValueError:
                        result.warnings.append(
                            f"Строка {i}: неверный флаг разгонного круга '{warmup_str}' для категории '{cat_name}', использовано значение true"
                        )

                finish_mode = (
                    _get_field(row, col_map, "category_finish_mode") or "laps"
                ).strip().lower()
                if finish_mode not in {"laps", "time"}:
                    result.warnings.append(
                        f"Строка {i}: неверный режим финиша '{finish_mode}' для категории '{cat_name}', использовано значение laps"
                    )
                    finish_mode = "laps"

                time_limit_sec = None
                time_limit_str = _get_field(row, col_map, "category_time_limit_sec")
                if finish_mode == "time":
                    if time_limit_str:
                        try:
                            time_limit_sec = _parse_optional_int(time_limit_str)
                            if (
                                time_limit_sec is None
                                or time_limit_sec < 1
                                or time_limit_sec > MAX_CATEGORY_TIME_LIMIT_SEC
                            ):
                                raise ValueError(time_limit_str)
                        except ValueError:
                            result.warnings.append(
                                f"Строка {i}: неверный лимит времени '{time_limit_str}' для категории '{cat_name}', использовано значение 3600"
                            )
                            time_limit_sec = 3600
                    else:
                        time_limit_sec = 3600

                cat_id = db.add_category(
                    name=cat_name,
                    laps=laps,
                    distance_km=distance_km,
                    has_warmup_lap=has_warmup_lap,
                    finish_mode=finish_mode,
                    time_limit_sec=time_limit_sec,
                )
                category = db.get_category(cat_id)
                cat_cache[cat_key] = dict(category)
            else:
                cat_id = category["id"]

        if epc and db.get_rider_by_epc(epc):
            result.warnings.append(f"Строка {i}: EPC '{epc}' уже привязан - пропущен")
            epc = None

        db.add_rider(
            number=number,
            last_name=last_name,
            first_name=first_name,
            birth_year=birth_year,
            city=city,
            club=club,
            category_id=cat_id,
            epc=epc,
        )
        result.imported += 1

    return result
