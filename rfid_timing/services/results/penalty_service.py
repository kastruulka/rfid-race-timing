import logging
from typing import Optional, Dict

from ...database.database import Database
from ...infra.logger import RawLogger
from .result_state_service import ResultStateService

logger = logging.getLogger(__name__)

DNF_REASONS = {
    "voluntary": "Добровольный сход",
    "mechanical": "Механическая поломка",
    "injury": "Травма",
    "other": "Другое",
}


class PenaltyService:
    def __init__(self, db: Database, raw_logger: RawLogger):
        self.db = db
        self.raw_logger = raw_logger
        self.result_states = ResultStateService(db)

    @staticmethod
    def _rider_epc(rider: Optional[Dict]) -> str:
        return rider.get("epc", "") if rider else ""

    @staticmethod
    def _rider_number(rider: Optional[Dict], fallback: int = 0) -> int:
        return rider["number"] if rider else fallback

    def _notify_log(self, event: str, rider_id: int, **extra):
        rider = self.db.riders_repo.get_rider(rider_id)
        num = self._rider_number(rider, rider_id)
        epc = self._rider_epc(rider)
        details_parts = [f"rider={num}"]
        details_parts.extend(f"{k}={v}" for k, v in extra.items() if v)
        self.raw_logger.log_event(event, epc=epc, details=",".join(details_parts))
        return rider, num

    def _is_result_category_closed(self, result: Optional[Dict]) -> bool:
        if not result:
            return False
        category_id = result.get("category_id")
        return bool(
            category_id and self.db.category_state_repo.is_category_closed(category_id)
        )

    def _sync_finish_state(self, result_id: int):
        self.result_states.sync_projected_state(result_id)

    def set_dnf(
        self,
        rider_id: int,
        reason_code: str = "",
        reason_text: str = "",
        on_status_change=None,
    ) -> bool:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if self._is_result_category_closed(result):
            return False
        if not result or result["status"] not in ("RACING", "DNS", "FINISHED"):
            return False

        reason = DNF_REASONS.get(reason_code, reason_text or reason_code)
        self.result_states.set_dnf(result["id"], reason)
        self.db.penalties_repo.add_penalty(result["id"], "DNF", value=0, reason=reason)

        rider, num = self._notify_log("DNF", rider_id, reason=reason)
        logger.info("#%d — DNF: %s", num, reason)

        if on_status_change and rider:
            on_status_change(
                {
                    "event": "DNF",
                    "rider_number": rider["number"],
                    "rider_name": f"{rider['last_name']} {rider['first_name']}",
                    "reason": reason,
                }
            )
        return True

    def set_dsq(
        self,
        rider_id: int,
        reason: str = "",
        on_status_change=None,
    ) -> bool:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if self._is_result_category_closed(result):
            return False
        if not result:
            return False

        self.result_states.set_dsq(result["id"], reason)
        self.db.penalties_repo.add_penalty(result["id"], "DSQ", reason=reason)

        rider, num = self._notify_log("DSQ", rider_id, reason=reason)
        logger.info("#%d — DSQ: %s", num, reason)

        if on_status_change and rider:
            on_status_change(
                {
                    "event": "DSQ",
                    "rider_number": rider["number"],
                    "rider_name": f"{rider['last_name']} {rider['first_name']}",
                    "reason": reason,
                }
            )
        return True

    def add_time_penalty(
        self, rider_id: int, seconds: float, reason: str = ""
    ) -> Optional[Dict]:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if self._is_result_category_closed(result):
            return None
        if not result:
            return None
        pid = self.db.penalties_repo.add_penalty(
            result["id"], "TIME_PENALTY", value=seconds, reason=reason
        )
        self.db.penalties_repo.recalc_penalties(result["id"])
        self._sync_finish_state(result["id"])

        _, num = self._notify_log("TIME_PENALTY", rider_id, sec=seconds, reason=reason)
        logger.info("#%d — штраф +%.0f сек: %s", num, seconds, reason)
        return {"id": pid, "type": "TIME_PENALTY", "value": seconds, "reason": reason}

    def add_extra_lap(
        self, rider_id: int, laps: int = 1, reason: str = ""
    ) -> Optional[Dict]:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if self._is_result_category_closed(result):
            return None
        if not result:
            return None
        pid = self.db.penalties_repo.add_penalty(
            result["id"], "EXTRA_LAP", value=laps, reason=reason
        )
        self.db.penalties_repo.recalc_penalties(result["id"])
        self._sync_finish_state(result["id"])

        _, num = self._notify_log("EXTRA_LAP", rider_id, laps=laps, reason=reason)
        logger.info("#%d — штрафной круг (+%d): %s", num, laps, reason)
        return {"id": pid, "type": "EXTRA_LAP", "value": laps, "reason": reason}

    def add_warning(self, rider_id: int, reason: str = "") -> Optional[Dict]:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if self._is_result_category_closed(result):
            return None
        if not result:
            return None
        pid = self.db.penalties_repo.add_penalty(
            result["id"], "WARNING", value=0, reason=reason
        )

        _, num = self._notify_log("WARNING", rider_id, reason=reason)
        logger.info("#%d — предупреждение: %s", num, reason)
        return {"id": pid, "type": "WARNING", "value": 0, "reason": reason}

    def remove_penalty(self, penalty_id: int) -> bool:
        penalty = self.db.penalties_repo.get_penalty_by_id(penalty_id)
        if not penalty:
            return False

        result_id = penalty["result_id"]
        result = self.db.results_repo.get_result_by_id(result_id)
        if self._is_result_category_closed(result):
            return False
        penalty_type = penalty["type"]

        self.db.penalties_repo.delete_penalty(penalty_id)
        self.db.penalties_repo.recalc_penalties(result_id)

        if penalty_type in ("DNF", "DSQ"):
            self.result_states.restore_projected_state(result_id)
        else:
            self._sync_finish_state(result_id)

        refreshed_result = self.db.results_repo.get_result_by_id(result_id)
        if refreshed_result and refreshed_result.get("category_id"):
            self.result_states.assign_places(refreshed_result["category_id"])

        logger.info(
            "Штраф #%d (%s) удалён, пересчёт result #%d",
            penalty_id,
            penalty_type,
            result_id,
        )
        return True

    def get_rider_penalties(self, rider_id: int) -> list:
        result = self.db.results_repo.get_result_by_rider(rider_id)
        if not result:
            return []
        return self.db.penalties_repo.get_penalties(result["id"])
