from typing import Dict, List


class FeedRepository:
    def __init__(self, db):
        self._db = db

    def get_feed_history(
        self, limit: int = 50, race_id: int = None, category_id: int = None
    ) -> List[Dict]:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return []

        base = """
            SELECT
                l.id as lap_id, l.lap_number, l.lap_time, l.timestamp,
                rd.number as rider_number, rd.last_name, rd.first_name,
                c.laps as laps_required, r.extra_laps, r.status
            FROM lap l
            JOIN result r ON l.result_id = r.id
            JOIN rider rd ON r.rider_id = rd.id
            LEFT JOIN category c ON r.category_id = c.id
            WHERE r.race_id = ?
        """
        if category_id:
            rows = self._db._exec(
                base + " AND r.category_id = ? ORDER BY l.timestamp DESC LIMIT ?",
                (race_id, category_id, limit),
            ).fetchall()
        else:
            rows = self._db._exec(
                base + " ORDER BY l.timestamp DESC LIMIT ?",
                (race_id, limit),
            ).fetchall()

        return [dict(row) for row in rows]
