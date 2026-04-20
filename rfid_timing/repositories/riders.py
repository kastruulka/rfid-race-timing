import logging
import sqlite3
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..database.database import Database

logger = logging.getLogger(__name__)


class RidersRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def add_rider(
        self,
        number: int,
        last_name: str,
        first_name: str = "",
        birth_year: int = None,
        city: str = "",
        club: str = "",
        model: str = "",
        category_id: int = None,
        epc: str = None,
    ) -> int:
        cur = self._db._exec(
            """INSERT INTO rider (number, last_name, first_name, birth_year,
               city, club, model, category_id, epc)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                number,
                last_name,
                first_name,
                birth_year,
                city,
                club,
                model,
                category_id,
                epc,
            ),
        )
        self._db._commit()
        return cur.lastrowid

    def update_rider(self, rid: int, **kw) -> bool:
        return self._db._update_fields(
            "rider",
            rid,
            {
                "number",
                "last_name",
                "first_name",
                "birth_year",
                "city",
                "club",
                "model",
                "category_id",
                "epc",
            },
            **kw,
        )

    def delete_rider(self, rid: int) -> bool:
        try:
            with self._db._transaction():
                results = self._db._exec(
                    "SELECT id FROM result WHERE rider_id=?", (rid,)
                ).fetchall()
                for result in results:
                    self._db._exec("DELETE FROM lap WHERE result_id=?", (result["id"],))
                    self._db._exec(
                        "DELETE FROM penalty WHERE result_id=?", (result["id"],)
                    )
                self._db._exec("DELETE FROM result WHERE rider_id=?", (rid,))
                self._db._exec("DELETE FROM note WHERE rider_id=?", (rid,))
                self._db._exec("DELETE FROM start_protocol WHERE rider_id=?", (rid,))
                self._db._exec("DELETE FROM rider WHERE id=?", (rid,))
            return True
        except sqlite3.Error:
            logger.exception("Failed to delete rider #%d", rid)
            return False

    def get_rider(self, rid: int) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM rider WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None

    def get_riders(self, category_id: int = None) -> List[Dict]:
        if category_id:
            rows = self._db._exec(
                "SELECT * FROM rider WHERE category_id=? ORDER BY number",
                (category_id,),
            ).fetchall()
        else:
            rows = self._db._exec("SELECT * FROM rider ORDER BY number").fetchall()
        return [dict(row) for row in rows]

    def get_riders_with_category(self, category_id: int = None) -> List[Dict]:
        base = """
            SELECT r.*, c.name as category_name
            FROM rider r
            LEFT JOIN category c ON r.category_id = c.id
        """
        if category_id:
            rows = self._db._exec(
                base + " WHERE r.category_id = ? ORDER BY r.number", (category_id,)
            ).fetchall()
        else:
            rows = self._db._exec(base + " ORDER BY r.number").fetchall()
        return [dict(row) for row in rows]

    def get_rider_by_epc(self, epc: str) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM rider WHERE epc=?", (epc,)).fetchone()
        return dict(row) if row else None

    def get_rider_by_number(self, number: int) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM rider WHERE number=?", (number,)).fetchone()
        return dict(row) if row else None

    def get_epc_map(self) -> Dict[str, Dict]:
        rows = self._db._exec(
            "SELECT * FROM rider WHERE epc IS NOT NULL AND epc != ''"
        ).fetchall()
        return {row["epc"]: dict(row) for row in rows}
