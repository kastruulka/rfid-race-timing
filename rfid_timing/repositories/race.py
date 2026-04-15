import time
from typing import Optional


class RaceRepository:
    def __init__(self, db):
        self._db = db

    def create_race(self, label: str = "") -> int:
        cur = self._db._exec(
            "INSERT INTO race (created_at, label) VALUES (?, ?)",
            (self._db._normalize_db_value("created_at", time.time()), label),
        )
        self._db._commit()
        return cur.lastrowid

    def get_current_race_id(self) -> Optional[int]:
        row = self._db._exec("SELECT id FROM race ORDER BY id DESC LIMIT 1").fetchone()
        return row["id"] if row else None

    def close_race(self, race_id: int = None):
        race_id = race_id or self.get_current_race_id()
        if race_id is None:
            return
        self._db._exec(
            "UPDATE race SET closed_at=? WHERE id=?",
            (self._db._normalize_db_value("closed_at", time.time()), race_id),
        )
        self._db._commit()

    def is_race_closed(self, race_id: int = None) -> bool:
        race_id = race_id or self.get_current_race_id()
        if race_id is None:
            return False
        row = self._db._exec(
            "SELECT closed_at FROM race WHERE id=?",
            (race_id,),
        ).fetchone()
        return row is not None and row["closed_at"] is not None

    def get_race_closed_at(self, race_id: int = None) -> Optional[float]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return None
        row = self._db._exec(
            "SELECT closed_at FROM race WHERE id=?",
            (race_id,),
        ).fetchone()
        return row["closed_at"] if row else None

    def get_earliest_start_time(
        self, race_id: int = None, category_id: int = None
    ) -> Optional[int]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return None
        if category_id:
            row = self._db._exec(
                "SELECT MIN(start_time) as mn FROM result WHERE race_id=? AND category_id=? AND start_time IS NOT NULL",
                (race_id, category_id),
            ).fetchone()
        else:
            row = self._db._exec(
                "SELECT MIN(start_time) as mn FROM result WHERE race_id=? AND start_time IS NOT NULL",
                (race_id,),
            ).fetchone()
        return int(row["mn"]) if row and row["mn"] is not None else None
