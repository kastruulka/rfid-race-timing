import hashlib
import json
from typing import Any

from ..database.database import Database

SYNC_SCHEMA_VERSION = 1
DEFAULT_SOURCE_DEVICE_ID = "local-app"


def _normalize_timestamp_ms(value: Any) -> int | None:
    if value is None:
        return None

    timestamp = int(value)
    # Older penalty records may still be stored in seconds.
    if timestamp < 100_000_000_000:
        return timestamp * 1000
    return timestamp


def _build_start_records(
    db: Database, race_id: int, category_id: int
) -> list[dict[str, Any]]:
    rows = db._exec(
        """
        SELECT
            res.race_id,
            res.rider_id AS user_id,
            res.category_id,
            rd.number,
            rd.club,
            rd.city,
            rd.model,
            res.start_time
        FROM result res
        JOIN rider rd ON rd.id = res.rider_id
        WHERE res.race_id = ? AND res.category_id = ? AND res.start_time IS NOT NULL
        ORDER BY res.start_time, rd.number, res.rider_id
        """,
        (race_id, category_id),
    ).fetchall()
    return [
        {
            "race_id": int(row["race_id"]),
            "user_id": int(row["user_id"]),
            "category_id": int(row["category_id"]),
            "number": int(row["number"]),
            "club": row["club"] or "",
            "city": row["city"] or "",
            "model": row["model"] or "",
            "start_time": int(row["start_time"]),
        }
        for row in rows
    ]


def _build_pass_event_records(
    db: Database, race_id: int, category_id: int
) -> list[dict[str, Any]]:
    rows = db._exec(
        """
        SELECT
            res.race_id,
            res.rider_id AS user_id,
            res.category_id,
            lap.lap_number AS lap,
            lap.timestamp AS event_time,
            lap.source,
            res.start_time
        FROM lap
        JOIN result res ON res.id = lap.result_id
        WHERE res.race_id = ? AND res.category_id = ?
        ORDER BY lap.timestamp, lap.id
        """,
        (race_id, category_id),
    ).fetchall()

    pass_events: list[dict[str, Any]] = []
    for row in rows:
        event_time = int(row["event_time"])
        start_time = int(row["start_time"]) if row["start_time"] is not None else None
        lap_number = int(row["lap"])
        pass_events.append(
            {
                "race_id": int(row["race_id"]),
                "user_id": int(row["user_id"]),
                "category_id": int(row["category_id"]),
                "lap": lap_number,
                "segment": "warmup_lap" if lap_number == 0 else "lap",
                "event_time": event_time,
                "elapsed_ms": event_time - start_time
                if start_time is not None
                else None,
                "source": row["source"] or "RFID",
            }
        )
    return pass_events


def _build_penalty_records(
    db: Database, race_id: int, category_id: int
) -> list[dict[str, Any]]:
    rows = db._exec(
        """
        SELECT
            res.race_id,
            res.rider_id AS user_id,
            res.category_id,
            p.type,
            p.value,
            p.reason,
            p.created_at
        FROM penalty p
        JOIN result res ON res.id = p.result_id
        WHERE res.race_id = ? AND res.category_id = ?
        ORDER BY p.created_at, p.id
        """,
        (race_id, category_id),
    ).fetchall()
    return [
        {
            "race_id": int(row["race_id"]),
            "user_id": int(row["user_id"]),
            "category_id": int(row["category_id"]),
            "type": row["type"],
            "value": float(row["value"] or 0),
            "reason": row["reason"] or "",
            "created_at": _normalize_timestamp_ms(row["created_at"]),
        }
        for row in rows
    ]


def _build_result_records(
    db: Database, race_id: int, category_id: int
) -> list[dict[str, Any]]:
    rows = db._exec(
        """
        SELECT
            race_id,
            rider_id AS user_id,
            category_id,
            status,
            start_time,
            finish_time,
            place,
            penalty_time_ms,
            extra_laps,
            dnf_reason
        FROM result
        WHERE race_id = ? AND category_id = ?
        ORDER BY
            CASE status
                WHEN 'FINISHED' THEN 0
                WHEN 'RACING' THEN 1
                WHEN 'DNS' THEN 2
                WHEN 'DNF' THEN 3
                WHEN 'DSQ' THEN 4
                ELSE 5
            END,
            place IS NULL,
            place,
            finish_time,
            rider_id
        """,
        (race_id, category_id),
    ).fetchall()
    return [
        {
            "race_id": int(row["race_id"]),
            "user_id": int(row["user_id"]),
            "category_id": int(row["category_id"]),
            "status": row["status"],
            "start_time": int(row["start_time"])
            if row["start_time"] is not None
            else None,
            "finish_time": int(row["finish_time"])
            if row["finish_time"] is not None
            else None,
            "place": int(row["place"]) if row["place"] is not None else None,
            "penalty_time_ms": int(row["penalty_time_ms"] or 0),
            "extra_laps": int(row["extra_laps"] or 0),
            "dnf_reason": row["dnf_reason"] or "",
        }
        for row in rows
    ]


def build_sync_export_payload(
    db: Database,
    category_id: int,
    source_device_id: str = DEFAULT_SOURCE_DEVICE_ID,
) -> dict[str, Any]:
    race_id = db.get_current_race_id()
    if race_id is None:
        raise ValueError("Активная гонка не найдена")

    category = db.get_category(category_id)
    if not category:
        raise ValueError("Категория не найдена")

    return {
        "schema_version": SYNC_SCHEMA_VERSION,
        "source_device_id": source_device_id,
        "race_id": race_id,
        "starts": _build_start_records(db, race_id, category_id),
        "pass_events": _build_pass_event_records(db, race_id, category_id),
        "penalties": _build_penalty_records(db, race_id, category_id),
        "results": _build_result_records(db, race_id, category_id),
    }


def ingest_sync_payload(
    db: Database, payload: dict[str, Any], filename: str = ""
) -> dict[str, Any]:
    normalized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    file_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    previous_hash = getattr(db, "_last_sync_import_hash", None)
    is_duplicate = previous_hash == file_hash
    db._last_sync_import_hash = file_hash
    return {
        "ok": True,
        "duplicate": is_duplicate,
        "filename": filename,
        "rows_total": sum(
            len(payload.get(key, []))
            for key in ("starts", "pass_events", "penalties", "results")
        ),
    }
