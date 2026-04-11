class CategoryResetService:
    def __init__(self, db):
        self._db = db

    def reset_category(self, category_id: int, race_id: int = None) -> dict:
        race_id = self._db._resolve_race(race_id)
        if race_id is None:
            return {"error": "no race"}

        with self._db._transaction():
            deleted_notes = self._db.delete_notes_by_category(
                category_id=category_id,
                race_id=race_id,
            )
            results = self._db._exec(
                "SELECT id FROM result WHERE category_id=? AND race_id=?",
                (category_id, race_id),
            ).fetchall()
            result_ids = [row["id"] for row in results]

            deleted_laps = 0
            for result_id in result_ids:
                row = self._db._exec(
                    "SELECT COUNT(*) as cnt FROM lap WHERE result_id=?",
                    (result_id,),
                ).fetchone()
                deleted_laps += row["cnt"] if row else 0
                self._db._exec("DELETE FROM lap WHERE result_id=?", (result_id,))
                self._db._exec("DELETE FROM penalty WHERE result_id=?", (result_id,))

            if result_ids:
                placeholders = ",".join("?" * len(result_ids))
                self._db._exec(
                    f"DELETE FROM result WHERE id IN ({placeholders})",
                    tuple(result_ids),
                )

            start_protocol_deleted = self._db._exec(
                "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            ).rowcount
            category_state_deleted = self._db._exec(
                "DELETE FROM category_state WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            ).rowcount

            race_row = self._db._exec(
                "SELECT closed_at FROM race WHERE id=?",
                (race_id,),
            ).fetchone()
            category_had_data = bool(
                result_ids or start_protocol_deleted > 0 or category_state_deleted > 0
            )
            if category_had_data and race_row and race_row["closed_at"] is not None:
                self._db._exec("UPDATE race SET closed_at=NULL WHERE id=?", (race_id,))

        return {
            "deleted_results": len(result_ids),
            "deleted_laps": deleted_laps,
            "deleted_notes": deleted_notes,
        }
