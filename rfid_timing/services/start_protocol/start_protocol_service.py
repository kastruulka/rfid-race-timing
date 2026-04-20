from __future__ import annotations

from dataclasses import dataclass

from ...database.database import Database


@dataclass(frozen=True)
class LaunchPlanEntry:
    entry_id: int
    planned_time: float


def format_protocol_entry(entry: dict) -> dict:
    return {
        "entry_id": entry["id"],
        "rider_id": entry["rider_id"],
        "rider_number": entry["rider_number"],
        "rider_name": f"{entry['last_name']} {entry.get('first_name', '')}".strip(),
        "category_id": entry["category_id"],
        "category_name": entry.get("category_name"),
        "position": entry["position"],
        "planned_time": entry.get("planned_time"),
        "actual_time": entry.get("actual_time"),
        "status": entry.get("status", "WAITING"),
    }


def get_protocol_entries(db: Database, category_ids: list[int]) -> list[dict]:
    if not category_ids:
        return []

    race_id = db.get_current_race_id()
    if race_id is None:
        return []

    placeholders = ",".join("?" for _ in category_ids)
    rows = db._exec(
        f"""
        SELECT sp.*, rd.number as rider_number,
               rd.last_name, rd.first_name,
               rd.club, rd.city,
               cat.name as category_name
        FROM start_protocol sp
        JOIN rider rd ON sp.rider_id = rd.id
        JOIN category cat ON sp.category_id = cat.id
        WHERE sp.race_id=? AND sp.category_id IN ({placeholders})
        ORDER BY sp.position, sp.id
        """,
        (race_id, *category_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def clear_protocol_for_categories(db: Database, category_ids: list[int]) -> None:
    if not category_ids:
        return
    race_id = db.get_current_race_id()
    if race_id is None:
        return
    placeholders = ",".join("?" for _ in category_ids)
    db._exec(
        f"DELETE FROM start_protocol WHERE race_id=? AND category_id IN ({placeholders})",
        (race_id, *category_ids),
    )


def normalize_protocol_entries(
    db: Database,
    category_ids: list[int],
    entries: list[dict] | None,
    rider_ids: list[int] | None,
) -> list[dict]:
    allowed_ids = {int(category_id) for category_id in category_ids}
    normalized_entries: list[dict] = []

    if entries is not None:
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError("Некорректная запись очереди старта")
            rider_id = int(entry.get("rider_id"))
            category_id = int(entry.get("category_id"))
            if category_id not in allowed_ids:
                raise ValueError(
                    "Участник добавлен из категории вне выбранного набора"
                )
            rider = db.get_rider(rider_id)
            if not rider or int(rider.get("category_id") or 0) != category_id:
                raise ValueError(
                    "Участник не найден или не принадлежит выбранной категории"
                )
            normalized_entries.append(
                {
                    "rider_id": rider_id,
                    "category_id": category_id,
                    "position": index,
                }
            )
        return normalized_entries

    if rider_ids is None:
        return []

    if len(category_ids) != 1:
        raise ValueError("Для нескольких категорий требуется передать entries")

    category_id = category_ids[0]
    for index, rider_id in enumerate(rider_ids, start=1):
        rider = db.get_rider(int(rider_id))
        if not rider or int(rider.get("category_id") or 0) != category_id:
            raise ValueError(
                "Участник не найден или не принадлежит выбранной категории"
            )
        normalized_entries.append(
            {
                "rider_id": int(rider_id),
                "category_id": category_id,
                "position": index,
            }
        )
    return normalized_entries


def reset_entries_to_waiting(
    db: Database, entries: list[dict], scheduler, category_ids: list[int]
) -> None:
    if scheduler:
        for category_id in category_ids:
            scheduler.stop_category(category_id)
        return

    for entry in entries:
        if entry.get("status") == "STARTED":
            continue
        db.update_start_protocol_entry(
            entry["id"],
            planned_time=None,
            actual_time=None,
            status="WAITING",
        )


def save_protocol_entries(
    db: Database,
    category_ids: list[int],
    queue_entries: list[dict],
    interval_sec: float,
) -> int:
    race_id = db.get_current_race_id()
    with db._transaction():
        clear_protocol_for_categories(db, category_ids)
        for index, entry in enumerate(queue_entries, start=1):
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, status)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    race_id,
                    entry["category_id"],
                    entry["rider_id"],
                    index,
                    interval_sec,
                    "WAITING",
                ),
            )
    return len(queue_entries)


def save_protocol_preserving_started(
    db: Database,
    category_ids: list[int],
    queue_entries: list[dict],
    interval_sec: float,
) -> int:
    race_id = db.get_current_race_id()
    existing_entries = get_protocol_entries(db, category_ids)
    started_entries = [
        entry for entry in existing_entries if entry.get("status") == "STARTED"
    ]
    started_ids = {int(entry["rider_id"]) for entry in started_entries}
    remaining_entries = [
        entry for entry in queue_entries if int(entry["rider_id"]) not in started_ids
    ]

    with db._transaction():
        clear_protocol_for_categories(db, category_ids)
        position = 1
        for entry in started_entries:
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, planned_time, actual_time, status)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    race_id,
                    entry["category_id"],
                    entry["rider_id"],
                    position,
                    entry.get("interval_sec", interval_sec),
                    None,
                    db._normalize_db_value("actual_time", entry.get("actual_time")),
                    "STARTED",
                ),
            )
            position += 1

        for entry in remaining_entries:
            db._exec(
                """
                INSERT INTO start_protocol
                    (race_id, category_id, rider_id, position, interval_sec, status)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    race_id,
                    entry["category_id"],
                    entry["rider_id"],
                    position,
                    interval_sec,
                    "WAITING",
                ),
            )
            position += 1

    return len(started_entries) + len(remaining_entries)


def remaining_protocol_entries(entries: list[dict]) -> list[dict]:
    return [entry for entry in entries if entry.get("status") != "STARTED"]


def build_launch_plan(
    remaining_entries: list[dict],
    now_ms: float,
    resume_delay_ms: float,
) -> list[LaunchPlanEntry]:
    plan: list[LaunchPlanEntry] = []
    for index, entry in enumerate(remaining_entries):
        interval = entry.get("interval_sec", 30)
        planned_time = now_ms + resume_delay_ms + (index * interval * 1000)
        plan.append(
            LaunchPlanEntry(
                entry_id=int(entry["id"]),
                planned_time=planned_time,
            )
        )
    return plan


def apply_launch_plan(db: Database, launch_plan: list[LaunchPlanEntry]) -> None:
    for planned_entry in launch_plan:
        db.update_start_protocol_entry(
            planned_entry.entry_id,
            planned_time=planned_entry.planned_time,
            actual_time=None,
            status="PLANNED",
        )

