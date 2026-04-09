import logging
from typing import Dict

from ..database import Database
from ..infra.logger import RawLogger

logger = logging.getLogger(__name__)


class FinishService:
    def __init__(self, db: Database, raw_logger: RawLogger):
        self.db = db
        self.raw_logger = raw_logger

    def finish_all(self, category_id: int) -> dict:
        results = self.db.get_results_by_category(category_id)
        newly_finished = 0
        newly_dnf = 0

        for result in results:
            if result["status"] != "RACING":
                continue
            if result.get("finish_time"):
                self.db.update_result(result["id"], status="FINISHED")
                newly_finished += 1
            else:
                self.db.update_result(
                    result["id"], status="DNF", dnf_reason="Гонка завершена судьёй"
                )
                self.db.add_penalty(
                    result["id"], "DNF", value=0, reason="Гонка завершена судьёй"
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
            logger.info("Все категории завершены - гонка закрыта")

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

        self.db.update_result(result["id"], status="RACING", finish_time=None)

        rider = self.db.get_rider(rider_id)
        logger.info(
            "#%d %s - финиш отменён, возврат в RACING",
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
        if category_id and self.db.is_category_closed(category_id):
            return False

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
            "#%d %s - время финиша изменено: %s -> %s",
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
        results = self.db.get_results_by_category(category_id)
        finished = sorted(
            [result for result in results if result["status"] == "FINISHED"],
            key=lambda result: result["finish_time"],
        )
        for place, result in enumerate(finished, start=1):
            self.db.update_result(result["id"], place=place)
        logger.info(
            "Места рассчитаны для категории %d: %d финишировавших",
            category_id,
            len(finished),
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
