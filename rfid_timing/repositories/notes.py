import time
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from ..database import Database


class NotesRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def add_note(self, text: str, rider_id: int = None, race_id: int = None) -> int:
        race_id = self._db._resolve_race(race_id)
        cur = self._db._exec(
            """INSERT INTO note (race_id, rider_id, text, created_at)
               VALUES (?,?,?,?)""",
            (
                race_id,
                rider_id,
                text,
                self._db._normalize_db_value("created_at", time.time()),
            ),
        )
        self._db._commit()
        return cur.lastrowid

    def get_notes(self, race_id: int = None) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._db._exec(
            """
            SELECT n.*, rd.number as rider_number,
                   rd.last_name, rd.first_name
            FROM note n
            LEFT JOIN rider rd ON n.rider_id = rd.id
            WHERE n.race_id = ?
            ORDER BY n.created_at DESC
        """,
            (race_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, note_id: int) -> bool:
        self._db._exec("DELETE FROM note WHERE id=?", (note_id,))
        self._db._commit()
        return True

    def delete_notes_by_category(self, category_id: int, race_id: int = None) -> int:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return 0

        cur = self._db._exec(
            """
            DELETE FROM note
            WHERE race_id = ?
              AND rider_id IN (
                  SELECT id
                  FROM rider
                  WHERE category_id = ?
              )
            """,
            (race_id, category_id),
        )
        return cur.rowcount or 0
