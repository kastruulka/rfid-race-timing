import logging
import time
from typing import Dict

from ...database.database import Database
from ...infra.logger import RawLogger
from .result_state_service import ResultStateService
from ...domain.timing import (
    get_time_limit_ms,
    is_time_limit_mode,
)

logger = logging.getLogger(__name__)


class FinishService:
    def __init__(self, db: Database, raw_logger: RawLogger):
        self.db = db
        self.raw_logger = raw_logger
        self.result_states = ResultStateService(db)

    def finalize_time_limit_category(
        self, category_id: int, now_ms: int | None = None
    ) -> int:
        category = self.db.get_category(category_id)
        if not category or not is_time_limit_mode(category):
            return 0
        if self.db.is_category_closed(category_id):
            return 0

        category_state = self.db.get_category_state(category_id)
        started_at = (
            category_state.get("started_at")
            if category_state and category_state.get("started_at") is not None
            else None
        )
        if started_at is None:
            return 0

        if now_ms is None:
            now_ms = int(self.db._normalize_db_value("finish_time", time.time() * 1000))
        deadline_ms = int(started_at) + int(get_time_limit_ms(category) or 0)
        if int(now_ms) <= deadline_ms:
            return 0

        finalized = 0
        for result in self.db.get_results_by_category(category_id):
            if result["status"] != "RACING":
                continue
            penalty_time_ms = result.get("penalty_time_ms") or 0
            self.result_states.set_finished(result["id"], deadline_ms + penalty_time_ms)
            finalized += 1

        return finalized

    def finalize_time_limit_categories(self, now_ms: int | None = None) -> int:
        total = 0
        for category in self.db.get_categories():
            total += self.finalize_time_limit_category(category["id"], now_ms=now_ms)
        return total

    def finish_all(self, category_id: int) -> dict:
        self.finalize_time_limit_category(category_id)
        results = self.db.get_results_by_category(category_id)
        newly_finished = 0
        newly_dnf = 0
        judge_stop_reason = "Гонка завершена судьёй"

        for result in results:
            if result["status"] != "RACING":
                continue
            if result.get("finish_time"):
                self.result_states.set_finished(
                    result["id"], int(result["finish_time"])
                )
                newly_finished += 1
            else:
                self.result_states.set_dnf(result["id"], judge_stop_reason)
                self.db.add_penalty(
                    result["id"], "DNF", value=0, reason=judge_stop_reason
                )
                newly_dnf += 1

        self.calculate_places(category_id)
        self.db.close_category(category_id)

        final_results = self.db.get_results_by_category(category_id)
        finished = sum(1 for result in final_results if result["status"] == "FINISHED")
        dnf_count = sum(
            1 for result in final_results if result["status"] in ("DNF", "DSQ")
        )

        if self.db.are_all_categories_closed():
            self.db.close_race()
            logger.info("Все категории завершены — гонка закрыта")

        logger.info(
            "Категория %d завершена: итоговый финиш: %d, итоговый DNF/DSQ: %d (новых финишей: %d, новых DNF: %d)",
            category_id,
            finished,
            dnf_count,
            newly_finished,
            newly_dnf,
        )
        return {
            "finished": finished,
            "dnf_count": dnf_count,
            "newly_finished": newly_finished,
            "newly_dnf": newly_dnf,
        }

    def unfinish_rider(self, rider_id: int) -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "FINISHED":
            return False

        category_id = result.get("category_id")
        if category_id and self.db.is_category_closed(category_id):
            return False

        last_lap = self.db.get_last_lap(result["id"])
        if last_lap:
            self.db.delete_lap(last_lap["id"])

        self.result_states.set_racing(result["id"])

        rider = self.db.get_rider(rider_id)
        logger.info(
            "#%d %s — финиш отменён, возврат в RACING",
            rider["number"] if rider else rider_id,
            rider["last_name"] if rider else "",
        )
        self.raw_logger.log_event(
            "UNFINISH",
            epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']}" if rider else "",
        )
        return True

    def edit_finish_time(self, rider_id: int, new_finish_time_ms: int) -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "FINISHED":
            return False

        category_id = result.get("category_id")
        category = self.db.get_category(category_id) if category_id else None
        if category_id and self.db.is_category_closed(category_id):
            return False
        if category and is_time_limit_mode(category):
            start_time_ms = int(float(result.get("start_time") or 0))
            limit_ms = int(get_time_limit_ms(category) or 0)
            if start_time_ms and int(new_finish_time_ms) - start_time_ms > limit_ms:
                raise ValueError("Финишное время превышает лимит времени категории")

        old_time = result.get("finish_time")
        penalty_ms = result.get("penalty_time_ms") or 0
        self.db.update_result(result["id"], finish_time=new_finish_time_ms)

        laps = self.db.get_laps(result["id"])
        if laps:
            last = laps[-1]
            new_last_ts = new_finish_time_ms - penalty_ms
            prev_ts = (
                laps[-2]["timestamp"]
                if len(laps) >= 2
                else int(float(result["start_time"]))
            )
            new_lap_time = new_last_ts - int(prev_ts)
            self.db.update_lap(last["id"], lap_time=new_lap_time, timestamp=new_last_ts)

        rider = self.db.get_rider(rider_id)
        logger.info(
            "#%d %s — время финиша изменено: %s → %s",
            rider["number"] if rider else rider_id,
            rider["last_name"] if rider else "",
            old_time,
            new_finish_time_ms,
        )
        self.raw_logger.log_event(
            "EDIT_FINISH",
            epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},old={old_time},new={new_finish_time_ms}",
        )
        return True

    def calculate_places(self, category_id: int):
        finished_count = self.result_states.assign_places(category_id)
        logger.info(
            "Места рассчитаны для категории %d: %d финишировавших",
            category_id,
            finished_count,
        )

    def reset_category(self, category_id: int) -> Dict:
        category = self.db.get_category(category_id)
        if not category:
            raise ValueError(f"Категория {category_id} не найдена")

        info = self.db.reset_category(category_id)

        self.raw_logger.log_event(
            "RESET_CATEGORY",
            details=(
                f"cat={category['name']},"
                f"results={info.get('deleted_results', 0)},"
                f"laps={info.get('deleted_laps', 0)}"
            ),
        )
        logger.info(
            "Категория '%s' сброшена: %d результатов, %d кругов удалено",
            category["name"],
            info.get("deleted_results", 0),
            info.get("deleted_laps", 0),
        )
        return {"category": category["name"], "category_id": category_id, **info}
