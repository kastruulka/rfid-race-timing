from typing import Dict, Optional

from ...database.database import Database
from ...domain.timing import (
    build_dnf_result_update,
    build_dsq_result_update,
    build_finished_result_update,
    build_racing_result_update,
    calc_total_time_with_penalty,
    derive_result_state,
    get_finish_mode,
    sort_results,
)


class ResultStateService:
    def __init__(self, db: Database):
        self.db = db

    def set_finished(self, result_id: int, finish_time_ms: int) -> None:
        self.db.update_result(result_id, **build_finished_result_update(finish_time_ms))

    def set_racing(self, result_id: int) -> None:
        self.db.update_result(result_id, **build_racing_result_update())

    def set_dnf(self, result_id: int, reason: str) -> None:
        self.db.update_result(result_id, **build_dnf_result_update(reason))

    def set_dsq(self, result_id: int, reason: str = "") -> None:
        self.db.update_result(result_id, **build_dsq_result_update(reason))

    def sync_projected_state(self, result_id: int) -> None:
        result = self.db.get_result_by_id(result_id)
        if not result:
            return

        category = self.db.get_category(result.get("category_id"))
        last_lap = self.db.get_last_lap(result_id)
        derived = derive_result_state(
            result,
            category,
            laps_done=self.db.count_laps(result_id),
            last_lap_ts=last_lap["timestamp"] if last_lap else None,
        )

        if derived["status"] == "FINISHED":
            self.set_finished(result_id, int(derived["finish_time"]))
            return

        if result.get("status") == "FINISHED" or result.get("finish_time") is not None:
            self.set_racing(result_id)

    def assign_places(self, category_id: int) -> int:
        results = []
        for row in self.db.get_results_with_lap_summary(category_id=category_id):
            enriched = dict(row)
            enriched["finish_mode"] = get_finish_mode(
                {
                    "finish_mode": row.get("cat_finish_mode"),
                    "time_limit_sec": row.get("cat_time_limit_sec"),
                }
            )
            enriched["total_time"] = calc_total_time_with_penalty(
                row,
                row.get("last_lap_ts"),
            )
            results.append(enriched)

        finished = [
            result for result in sort_results(results) if result["status"] == "FINISHED"
        ]
        finished_ids = {result["result_id"] for result in finished}
        for result in results:
            if result["result_id"] not in finished_ids and result.get("place") is not None:
                self.db.update_result(result["result_id"], place=None)

        for place, result in enumerate(finished, start=1):
            self.db.update_result(result["result_id"], place=place)

        return len(finished)

