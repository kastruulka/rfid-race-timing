import time
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..database import Database


class PenaltiesRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def add_penalty(
        self, result_id: int, penalty_type: str, value: float = 0, reason: str = ""
    ) -> int:
        cur = self._db._exec(
            """INSERT INTO penalty (result_id, type, value, reason, created_at)
               VALUES (?,?,?,?,?)""",
            (result_id, penalty_type, value, reason, time.time()),
        )
        self._db._commit()
        return cur.lastrowid

    def get_penalties(self, result_id: int) -> List[Dict]:
        rows = self._db._exec(
            "SELECT * FROM penalty WHERE result_id=? ORDER BY created_at", (result_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_penalty_by_id(self, penalty_id: int) -> Optional[Dict]:
        row = self._db._exec(
            "SELECT * FROM penalty WHERE id=?", (penalty_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_penalties_by_race(self, race_id: int = None) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._db._exec(
            """
            SELECT p.*, r.rider_id, r.category_id,
                   rd.number as rider_number,
                   rd.last_name, rd.first_name,
                   c.name as category_name
            FROM penalty p
            JOIN result r ON p.result_id = r.id
            JOIN rider rd ON r.rider_id = rd.id
            LEFT JOIN category c ON r.category_id = c.id
            WHERE r.race_id = ?
            ORDER BY p.created_at DESC
        """,
            (race_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_penalty(self, penalty_id: int) -> bool:
        self._db._exec("DELETE FROM penalty WHERE id=?", (penalty_id,))
        self._db._commit()
        return True

    def recalc_penalties(self, result_id: int):
        penalties = self.get_penalties(result_id)
        total_time_ms = 0
        total_extra_laps = 0
        for penalty in penalties:
            if penalty["type"] == "TIME_PENALTY":
                total_time_ms += int(penalty["value"] * 1000)
            elif penalty["type"] == "EXTRA_LAP":
                total_extra_laps += int(penalty["value"])
        self._db.update_result(
            result_id, penalty_time_ms=total_time_ms, extra_laps=total_extra_laps
        )
