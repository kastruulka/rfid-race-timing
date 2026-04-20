from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..database.database import Database


class StartProtocolRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def save_start_protocol(
        self, category_id: int, entries: List[Dict], race_id: int = None
    ) -> int:
        race_id = self._db._resolve_race(race_id)
        with self._db._transaction():
            self._db._exec(
                "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            )
            for entry in entries:
                self._db._exec(
                    """INSERT INTO start_protocol
                       (race_id, category_id, rider_id, position, interval_sec, status)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        race_id,
                        category_id,
                        entry["rider_id"],
                        entry["position"],
                        entry.get("interval_sec", 30),
                        "WAITING",
                    ),
                )
        return len(entries)

    def get_start_protocol(self, category_id: int, race_id: int = None) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._db._exec(
            """
            SELECT sp.*, rd.number as rider_number,
                   rd.last_name, rd.first_name,
                   rd.club, rd.city
            FROM start_protocol sp
            JOIN rider rd ON sp.rider_id = rd.id
            WHERE sp.race_id=? AND sp.category_id=?
            ORDER BY sp.position
        """,
            (race_id, category_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_start_protocol_entry(self, entry_id: int, **kw):
        self._db._update_fields(
            "start_protocol", entry_id, {"planned_time", "actual_time", "status"}, **kw
        )

    def claim_due_start_protocol_entries(
        self, now_ms: float, limit: int = 20
    ) -> List[Dict]:
        with self._db._transaction():
            rows = self._db._exec(
                """
                SELECT id, race_id, category_id, rider_id, position, planned_time
                FROM start_protocol
                WHERE status='PLANNED'
                  AND planned_time IS NOT NULL
                  AND planned_time<=?
                ORDER BY planned_time, id
                LIMIT ?
                """,
                (now_ms, limit),
            ).fetchall()
            if not rows:
                return []

            claimed = []
            for row in rows:
                updated = self._db._exec(
                    """
                    UPDATE start_protocol
                    SET status='STARTING'
                    WHERE id=? AND status='PLANNED'
                    """,
                    (row["id"],),
                )
                if updated.rowcount == 1:
                    claimed.append(dict(row))

            return claimed

    def clear_start_protocol(self, category_id: int, race_id: int = None):
        race_id = self._db._resolve_race(race_id)
        self._db._exec(
            "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        )
        self._db._commit()
