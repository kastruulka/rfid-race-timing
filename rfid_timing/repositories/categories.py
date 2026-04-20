import sqlite3
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..database.database import Database


class CategoriesRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def add_category(
        self,
        name: str,
        laps: int = 1,
        distance_km: float = 0,
        has_warmup_lap: bool = True,
        finish_mode: str = "laps",
        time_limit_sec: int = None,
    ) -> int:
        cur = self._db._exec(
            """
            INSERT INTO category
                (name, laps, distance_km, has_warmup_lap, finish_mode, time_limit_sec)
            VALUES (?,?,?,?,?,?)
            """,
            (
                name,
                laps,
                distance_km,
                1 if has_warmup_lap else 0,
                finish_mode,
                time_limit_sec,
            ),
        )
        self._db._commit()
        return cur.lastrowid

    def update_category(self, cid: int, **kw) -> bool:
        return self._db._update_fields(
            "category",
            cid,
            {
                "name",
                "laps",
                "distance_km",
                "has_warmup_lap",
                "finish_mode",
                "time_limit_sec",
            },
            **kw,
        )

    def delete_category(self, cid: int) -> bool:
        row = self._db._exec(
            "SELECT COUNT(*) as cnt FROM rider WHERE category_id=?",
            (cid,),
        ).fetchone()
        if row and row["cnt"] > 0:
            return False

        try:
            with self._db._transaction():
                result_rows = self._db._exec(
                    "SELECT id FROM result WHERE category_id=?",
                    (cid,),
                ).fetchall()
                for result in result_rows:
                    self._db._exec("DELETE FROM lap WHERE result_id=?", (result["id"],))
                    self._db._exec(
                        "DELETE FROM penalty WHERE result_id=?",
                        (result["id"],),
                    )

                self._db._exec("DELETE FROM result WHERE category_id=?", (cid,))
                self._db._exec("DELETE FROM category_state WHERE category_id=?", (cid,))
                self._db._exec("DELETE FROM start_protocol WHERE category_id=?", (cid,))
                self._db._exec("DELETE FROM category WHERE id=?", (cid,))
            return True
        except (sqlite3.IntegrityError, sqlite3.OperationalError):
            return False

    def get_categories(self) -> List[Dict]:
        rows = self._db._exec("SELECT * FROM category ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def get_category(self, cid: int) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM category WHERE id=?", (cid,)).fetchone()
        return dict(row) if row else None
