from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..database import Database


class LapsRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def get_laps(self, result_id: int) -> List[Dict]:
        rows = self._db._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number", (result_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def count_laps(self, result_id: int) -> int:
        row = self._db._exec(
            "SELECT COUNT(*) as cnt FROM lap WHERE result_id=? AND lap_number>0",
            (result_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_last_lap(self, result_id: int) -> Optional[Dict]:
        row = self._db._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number DESC LIMIT 1",
            (result_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_lap_by_id(self, lap_id: int) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM lap WHERE id=?", (lap_id,)).fetchone()
        return dict(row) if row else None

    def record_lap(
        self,
        result_id: int,
        lap_number: int,
        timestamp: float,
        lap_time: float = None,
        segment: str = "{}",
        source: str = "RFID",
    ) -> int:
        cur = self._db._exec(
            """INSERT INTO lap
               (result_id, lap_number, timestamp, lap_time, segment, source)
               VALUES (?,?,?,?,?,?)""",
            (result_id, lap_number, timestamp, lap_time, segment, source),
        )
        self._db._commit()
        return cur.lastrowid

    def update_lap(self, lap_id: int, **kw) -> bool:
        return self._db._update_fields(
            "lap", lap_id, {"timestamp", "lap_time", "source"}, **kw
        )

    def delete_lap(self, lap_id: int) -> bool:
        self._db._exec("DELETE FROM lap WHERE id=?", (lap_id,))
        self._db._commit()
        return True

    def recalc_lap_timestamps(self, result_id: int):
        result = self._db.get_result_by_id(result_id)
        if not result:
            return
        laps = self.get_laps(result_id)
        current_ts = int(float(result["start_time"]))
        for lap in laps:
            current_ts += int(lap.get("lap_time") or 0)
            self._db._exec(
                "UPDATE lap SET timestamp=? WHERE id=?",
                (current_ts, lap["id"]),
            )
        self._db._commit()
        if result["status"] == "FINISHED" and laps:
            penalty_ms = result.get("penalty_time_ms") or 0
            self._db.update_result(result_id, finish_time=current_ts + penalty_ms)

    def renumber_laps(self, result_id: int):
        laps = self.get_laps(result_id)
        for i, lap in enumerate(laps):
            new_num = 0 if i == 0 else i
            if lap["lap_number"] != new_num:
                self._db._exec(
                    "UPDATE lap SET lap_number=? WHERE id=?",
                    (new_num, lap["id"]),
                )
        self._db._commit()
        self.recalc_lap_timestamps(result_id)
