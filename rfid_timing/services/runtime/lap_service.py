import json
import logging
import time
from typing import Callable, Dict, Optional

from ...database.database import Database
from ...infra.logger import RawLogger
from ..results.result_state_service import ResultStateService
from ...domain.timing import (
    calc_finish_time,
    calc_required_laps,
    get_finish_mode,
    get_time_limit_ms,
    is_finish_reached,
    is_time_limit_reached,
    is_time_limit_mode,
)

logger = logging.getLogger(__name__)


class LapService:
    def __init__(
        self,
        db: Database,
        raw_logger: RawLogger,
        on_lap: Optional[Callable] = None,
        on_finish: Optional[Callable] = None,
        lookup_rider_by_epc: Optional[Callable[[str], Optional[Dict]]] = None,
        min_start_to_first_pass_ms: int = 3000,
        finalize_time_limit_category: Optional[Callable[[int, int], int]] = None,
    ):
        self.db = db
        self.raw_logger = raw_logger
        self.on_lap = on_lap
        self.on_finish = on_finish
        self.lookup_rider_by_epc = lookup_rider_by_epc
        self.min_start_to_first_pass_ms = min_start_to_first_pass_ms
        self.finalize_time_limit_category = finalize_time_limit_category
        self.result_states = ResultStateService(db)

    def _is_after_category_time_limit(
        self,
        category: Optional[Dict],
        result: Dict,
        timestamp_ms: int,
    ) -> bool:
        if not is_time_limit_mode(category):
            return False

        category_id = result.get("category_id")
        category_state = (
            self.db.get_category_state(category_id) if category_id is not None else None
        )
        started_at = (
            category_state.get("started_at")
            if category_state and category_state.get("started_at") is not None
            else result.get("start_time")
        )
        return is_time_limit_reached(category, started_at, timestamp_ms)

    def record_lap(
        self,
        rider: Dict,
        result: Dict,
        timestamp_ms: int,
        source: str = "RFID",
        rssi: float = 0,
        antenna: int = 0,
    ) -> Optional[Dict]:
        current_laps = self.db.count_laps(result["id"])
        last_lap = self.db.get_last_lap(result["id"])
        category = self.db.get_category(result["category_id"])
        has_warmup_lap = (
            True if category is None else bool(category.get("has_warmup_lap", 1))
        )
        finish_mode = get_finish_mode(category)
        total_required = calc_required_laps(result, category)
        penalty_time_ms = result.get("penalty_time_ms") or 0

        if self._is_after_category_time_limit(category, result, timestamp_ms):
            if self.finalize_time_limit_category and result.get("category_id"):
                self.finalize_time_limit_category(result["category_id"], timestamp_ms)
            logger.info(
                "#%d %s - skip lap after category time limit (%s sec)",
                rider["number"],
                rider["last_name"],
                int((get_time_limit_ms(category) or 0) / 1000),
            )
            return None

        if last_lap:
            lap_time_ms = timestamp_ms - int(last_lap["timestamp"])
        else:
            lap_time_ms = timestamp_ms - int(float(result["start_time"]))

        if last_lap is None and lap_time_ms < self.min_start_to_first_pass_ms:
            logger.info(
                "#%d %s - skip false first pass %.1f sec after start",
                rider["number"],
                rider["last_name"],
                lap_time_ms / 1000.0,
            )
            return None

        if last_lap is None:
            lap_number = 0 if has_warmup_lap else 1
        else:
            lap_number = current_laps + 1

        segment_data = json.dumps({str(lap_number): timestamp_ms})
        self.db.record_lap(
            result_id=result["id"],
            lap_number=lap_number,
            timestamp=timestamp_ms,
            lap_time=lap_time_ms,
            segment=segment_data,
            source=source,
        )

        total_time_ms = timestamp_ms - int(result["start_time"]) + penalty_time_ms

        if lap_number == 0:
            logger.info(
                "#%d %s - warmup lap (%.1f sec)",
                rider["number"],
                rider["last_name"],
                lap_time_ms / 1000.0,
            )
        else:
            logger.info(
                "#%d %s - lap %d/%d (%.1f sec)",
                rider["number"],
                rider["last_name"],
                lap_number,
                total_required,
                lap_time_ms / 1000.0,
            )

        lap_data = {
            "rider_id": rider["id"],
            "rider_number": rider["number"],
            "rider_name": f"{rider['last_name']} {rider['first_name']}",
            "category": category["name"] if category else "?",
            "lap_number": lap_number,
            "lap_time": lap_time_ms,
            "total_time": total_time_ms,
            "timestamp": timestamp_ms,
            "rssi": rssi,
            "antenna": antenna,
            "laps_done": lap_number if lap_number > 0 else 0,
            "laps_required": total_required,
            "penalty_time_ms": penalty_time_ms,
            "extra_laps": result.get("extra_laps") or 0,
            "source": source,
            "status": "RACING",
            "finish_mode": finish_mode,
            "time_limit_sec": category.get("time_limit_sec") if category else None,
        }

        if is_finish_reached(lap_number, total_required):
            finish_time_ms = calc_finish_time(timestamp_ms, penalty_time_ms)
            self.result_states.set_finished(result["id"], finish_time_ms)
            lap_data["status"] = "FINISHED"

            penalty_info = (
                f" (penalty: +{penalty_time_ms / 1000.0:.1f} sec)"
                if penalty_time_ms
                else ""
            )
            logger.info(
                "#%d %s - FINISH! Total time: %.1f sec%s",
                rider["number"],
                rider["last_name"],
                total_time_ms / 1000.0,
                penalty_info,
            )
            self.raw_logger.log_event(
                "FINISH",
                epc=rider.get("epc", ""),
                details=f"rider={rider['number']}",
            )
            if self.on_finish:
                self.on_finish(lap_data)
        elif is_time_limit_mode(category) and total_time_ms >= int(
            get_time_limit_ms(category) or 0
        ):
            finish_time_ms = calc_finish_time(timestamp_ms, penalty_time_ms)
            self.result_states.set_finished(result["id"], finish_time_ms)
            lap_data["status"] = "FINISHED"

            logger.info(
                "#%d %s - FINISH by time limit with penalties: %.1f sec",
                rider["number"],
                rider["last_name"],
                total_time_ms / 1000.0,
            )
            self.raw_logger.log_event(
                "FINISH",
                epc=rider.get("epc", ""),
                details=f"rider={rider['number']},mode=time-limit",
            )
            if self.on_finish:
                self.on_finish(lap_data)

        if self.on_lap:
            self.on_lap(lap_data)

        return lap_data

    def on_tag_pass(
        self, epc: str, timestamp: float, rssi: float = 0, antenna: int = 0
    ):
        self.raw_logger.log_pass(timestamp, epc, rssi, antenna)
        timestamp_ms = int(timestamp * 1000)

        rider = self.lookup_rider_by_epc(epc) if self.lookup_rider_by_epc else None
        if not rider:
            logger.debug("Unknown tag: %s", epc)
            return

        result = self.db.get_result_by_rider(rider["id"])
        if not result or result["status"] != "RACING":
            return
        if result.get("category_id") and self.db.is_category_closed(
            result["category_id"]
        ):
            return

        self.record_lap(
            rider,
            result,
            timestamp_ms,
            source="RFID",
            rssi=rssi,
            antenna=antenna,
        )

    def manual_lap(self, rider_id: int, timestamp: float = None) -> Optional[Dict]:
        if timestamp is None:
            timestamp = time.time() * 1000

        rider = self.db.get_rider(rider_id)
        if not rider:
            return None

        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "RACING":
            return None
        if result.get("category_id") and self.db.is_category_closed(
            result["category_id"]
        ):
            return None

        self.raw_logger.log_event(
            "MANUAL_LAP",
            epc=rider.get("epc", ""),
            details=f"rider={rider['number']}",
        )
        return self.record_lap(rider, result, int(timestamp), source="MANUAL")
