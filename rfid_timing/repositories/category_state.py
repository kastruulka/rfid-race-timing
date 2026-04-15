import time
from typing import Dict, List, Optional


class CategoryStateRepository:
    def __init__(self, db):
        self._db = db

    def set_category_started(
        self, category_id: int, started_at: float, race_id: int = None
    ):
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return
        existing = self._db._exec(
            "SELECT id, started_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        if existing:
            if existing["started_at"] is None:
                self._db._exec(
                    "UPDATE category_state SET started_at=? WHERE id=?",
                    (
                        self._db._normalize_db_value("started_at", started_at),
                        existing["id"],
                    ),
                )
        else:
            self._db._exec(
                "INSERT INTO category_state (race_id, category_id, started_at) VALUES (?,?,?)",
                (
                    race_id,
                    category_id,
                    self._db._normalize_db_value("started_at", started_at),
                ),
            )
        self._db._commit()

    def close_category(self, category_id: int, race_id: int = None):
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return
        now = self._db._normalize_db_value("closed_at", time.time())
        existing = self._db._exec(
            "SELECT id FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        if existing:
            self._db._exec(
                "UPDATE category_state SET closed_at=? WHERE id=?",
                (now, existing["id"]),
            )
        else:
            self._db._exec(
                "INSERT INTO category_state (race_id, category_id, closed_at) VALUES (?,?,?)",
                (race_id, category_id, now),
            )
        self._db._commit()

    def is_category_closed(self, category_id: int, race_id: int = None) -> bool:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return False
        row = self._db._exec(
            "SELECT closed_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        return row is not None and row["closed_at"] is not None

    def get_category_state(
        self, category_id: int, race_id: int = None
    ) -> Optional[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return None
        row = self._db._exec(
            "SELECT * FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        return dict(row) if row else None

    def get_all_category_states(self, race_id: int = None) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._db._exec(
            "SELECT * FROM category_state WHERE race_id=?",
            (race_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def are_all_categories_closed(self, race_id: int = None) -> bool:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return False
        states = self.get_all_category_states(race_id)
        if not states:
            return False
        return all(
            state["started_at"] is None or state["closed_at"] is not None
            for state in states
        )
