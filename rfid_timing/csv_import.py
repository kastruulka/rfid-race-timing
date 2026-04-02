import csv
import io
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from .database import Database

logger = logging.getLogger(__name__)


_COLUMN_ALIASES: Dict[str, str] = {
    "number": "number",
    "last_name": "last_name",
    "first_name": "first_name",
    "birth_year": "birth_year",
    "city": "city",
    "club": "club",
    "category": "category",
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
    "Number": "number",
    "Номер": "number",
    "Фамилия": "last_name",
    "Имя": "first_name",
    "Год": "birth_year",
    "Город": "city",
    "Команда": "club",
    "Клуб": "club",
    "Категория": "category",
    "EPC": "epc",
}

_REQUIRED_COLUMNS = {"number", "last_name"}

MAX_ROWS = 5000
MAX_NUMBER = 99999
MIN_BIRTH_YEAR = 1920
MAX_BIRTH_YEAR = 2025
MAX_FIELD_LEN = 200

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

    cat_cache = {}
    for c in db.get_categories():
        cat_cache[c["name"].lower().strip()] = c["id"]

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
                f"Строка {i}: номер {number} вне диапазона 1–{MAX_NUMBER}"
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
                if birth_year < MIN_BIRTH_YEAR or birth_year > MAX_BIRTH_YEAR:
                    result.warnings.append(
                        f"Строка {i}: год рождения {birth_year} вне диапазона — пропущен"
                    )
                    birth_year = None
            except ValueError:
                pass

        city = _get_field(row, col_map, "city")[:MAX_FIELD_LEN]
        club = _get_field(row, col_map, "club")[:MAX_FIELD_LEN]
        cat_name = _get_field(row, col_map, "category")[:MAX_FIELD_LEN]
        epc = _get_field(row, col_map, "epc")[:MAX_FIELD_LEN] or None

        cat_id = None
        if cat_name:
            cat_key = cat_name.lower().strip()
            if cat_key in cat_cache:
                cat_id = cat_cache[cat_key]
            else:
                cat_id = db.add_category(name=cat_name)
                cat_cache[cat_key] = cat_id

        if epc and db.get_rider_by_epc(epc):
            result.warnings.append(f"Строка {i}: EPC '{epc}' уже привязан — пропущен")
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
