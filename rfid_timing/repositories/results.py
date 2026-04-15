from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..database import Database


class ResultsRepository:
    def __init__(self, db: "Database"):
        self._db = db

    def create_result(
        self,
        rider_id: int,
        category_id: int,
        start_time: float = None,
        status: str = "DNS",
        race_id: int = None,
    ) -> int:
        race_id = self._db._resolve_race(race_id)
        with self._db._transaction():
            existing = self._db._exec(
                """SELECT id FROM result
                   WHERE rider_id=? AND race_id=?
                   LIMIT 1""",
                (rider_id, race_id),
            ).fetchone()
            if existing:
                return int(existing["id"])

            cur = self._db._exec(
                """INSERT INTO result
                   (rider_id, category_id, race_id, start_time, status)
                   VALUES (?,?,?,?,?)""",
                (
                    rider_id,
                    category_id,
                    race_id,
                    self._db._normalize_db_value("start_time", start_time),
                    status,
                ),
            )
            return cur.lastrowid

    def update_result(self, result_id: int, **kw):
        self._db._update_fields(
            "result",
            result_id,
            {
                "start_time",
                "finish_time",
                "status",
                "place",
                "dnf_reason",
                "penalty_time_ms",
                "extra_laps",
            },
            **kw,
        )

    def get_status_counts(
        self, race_id: int = None, category_id: int = None
    ) -> Dict[str, int]:
        race_id = self._db._resolve_race(race_id)
        counts = {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0, "DNS": 0}
        if race_id is None:
            return counts
        if category_id:
            rows = self._db._exec(
                "SELECT status, COUNT(*) as cnt FROM result WHERE race_id=? AND category_id=? GROUP BY status",
                (race_id, category_id),
            ).fetchall()
        else:
            rows = self._db._exec(
                "SELECT status, COUNT(*) as cnt FROM result WHERE race_id=? GROUP BY status",
                (race_id,),
            ).fetchall()
        for row in rows:
            counts[row["status"]] = row["cnt"]
        return counts

    def get_results_with_lap_summary(
        self, category_id: int = None, race_id: int = None
    ) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []

        base = """
            SELECT
                r.id as result_id,
                r.rider_id, r.category_id, r.start_time, r.finish_time,
                r.status, r.place, r.dnf_reason, r.penalty_time_ms, r.extra_laps,
                rd.number, rd.last_name, rd.first_name, rd.club, rd.city, rd.birth_year,
                c.laps as cat_laps, c.name as cat_name,
                COALESCE(ls.laps_done, 0) as laps_done,
                ls.last_lap_time, ls.last_lap_ts
            FROM result r
            JOIN rider rd ON rd.id = r.rider_id
            LEFT JOIN category c ON c.id = r.category_id
            LEFT JOIN (
                SELECT
                    result_id,
                    SUM(CASE WHEN lap_number > 0 THEN 1 ELSE 0 END) as laps_done,
                    MAX(CASE WHEN lap_number = (
                        SELECT MAX(lap_number) FROM lap l2 WHERE l2.result_id = lap.result_id
                    ) THEN lap_time END) as last_lap_time,
                    MAX(timestamp) as last_lap_ts
                FROM lap
                GROUP BY result_id
            ) ls ON ls.result_id = r.id
            WHERE r.race_id = ?
        """
        if category_id:
            rows = self._db._exec(
                base + " AND r.category_id = ?", (race_id, category_id)
            ).fetchall()
        else:
            rows = self._db._exec(base, (race_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_result_by_rider(self, rider_id: int, race_id: int = None) -> Optional[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return None
        row = self._db._exec(
            """SELECT * FROM result
               WHERE rider_id=? AND race_id=?
               LIMIT 1""",
            (rider_id, race_id),
        ).fetchone()
        return dict(row) if row else None

    def get_result_by_id(self, result_id: int) -> Optional[Dict]:
        row = self._db._exec("SELECT * FROM result WHERE id=?", (result_id,)).fetchone()
        return dict(row) if row else None

    def get_results_by_category(
        self, category_id: int, race_id: int = None
    ) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._db._exec(
            """SELECT r.*, rd.number, rd.last_name, rd.first_name,
                      rd.club, rd.city, rd.birth_year
               FROM result r
               JOIN rider rd ON rd.id = r.rider_id
               WHERE r.category_id = ? AND r.race_id = ?
               ORDER BY
                 CASE r.status
                   WHEN 'FINISHED' THEN 0
                   WHEN 'RACING'   THEN 1
                   WHEN 'DNS'      THEN 2
                   WHEN 'DNF'      THEN 3
                   WHEN 'DSQ'      THEN 4
                 END,
                 r.finish_time ASC NULLS LAST""",
            (category_id, race_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_category_for_result(self, result_id: int) -> Optional[int]:
        row = self._db._exec(
            "SELECT category_id FROM result WHERE id=?", (result_id,)
        ).fetchone()
        return row["category_id"] if row else None
