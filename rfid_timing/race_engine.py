import logging
import threading
from typing import Any, Callable, Dict, Optional

from .database import Database
from .infra.logger import RawLogger
from .penalty_service import PenaltyService
from .services.finish_service import FinishService
from .services.lap_service import LapService
from .services.start_service import StartService

logger = logging.getLogger(__name__)
MIN_START_TO_FIRST_PASS_MS = 3000


class RaceEngine:
    def __init__(
        self,
        db: Database,
        raw_logger: RawLogger,
        on_lap: Callable = None,
        on_finish: Callable = None,
        on_status_change: Callable = None,
    ):
        self.db = db
        self.raw_logger = raw_logger
        self.on_lap = on_lap
        self.on_finish = on_finish
        self.on_status_change = on_status_change

        self.penalties = PenaltyService(db, raw_logger)
        self.finishes = FinishService(db, raw_logger)
        self.starts = StartService(db, raw_logger, on_status_change)
        self.laps = LapService(
            db,
            raw_logger,
            on_lap=on_lap,
            on_finish=on_finish,
            lookup_rider_by_epc=self._get_rider_by_epc,
            min_start_to_first_pass_ms=MIN_START_TO_FIRST_PASS_MS,
        )

        self._epc_map: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.reload_epc_map()

    # Backward-compatible helper kept for callers that still use the old engine API.
    def _is_prestart_result(
        self, result: Optional[Dict], category_id: int = None
    ) -> bool:
        return self.starts.is_prestart_result(result, category_id)

    def reload_epc_map(self):
        self._epc_map = self.db.get_epc_map()
        logger.info("EPC map loaded: %d tags bound", len(self._epc_map))

    def _get_rider_by_epc(self, epc: str) -> Optional[Dict]:
        with self._lock:
            return self._epc_map.get(epc)

    # Judge decisions
    def set_dnf(
        self, rider_id: int, reason_code: str = "", reason_text: str = ""
    ) -> bool:
        return self.penalties.set_dnf(
            rider_id, reason_code, reason_text, self.on_status_change
        )

    def set_dsq(self, rider_id: int, reason: str = "") -> bool:
        return self.penalties.set_dsq(rider_id, reason, self.on_status_change)

    def add_time_penalty(
        self, rider_id: int, seconds: float, reason: str = ""
    ) -> Optional[Dict]:
        return self.penalties.add_time_penalty(rider_id, seconds, reason)

    def add_extra_lap(
        self, rider_id: int, laps: int = 1, reason: str = ""
    ) -> Optional[Dict]:
        return self.penalties.add_extra_lap(rider_id, laps, reason)

    def add_warning(self, rider_id: int, reason: str = "") -> Optional[Dict]:
        return self.penalties.add_warning(rider_id, reason)

    def remove_penalty(self, penalty_id: int) -> bool:
        return self.penalties.remove_penalty(penalty_id)

    def get_rider_penalties(self, rider_id: int) -> list:
        return self.penalties.get_rider_penalties(rider_id)

    # Starts
    def mass_start(self, category_id: int, start_time: float = None) -> Dict[str, Any]:
        return self.starts.mass_start(category_id, start_time)

    def individual_start(
        self, rider_id: int, start_time: float = None
    ) -> Dict[str, Any]:
        return self.starts.individual_start(rider_id, start_time)

    # Laps
    def _record_lap(
        self,
        rider: Dict,
        result: Dict,
        timestamp_ms: int,
        source: str = "RFID",
        rssi: float = 0,
        antenna: int = 0,
    ) -> Optional[Dict]:
        return self.laps.record_lap(rider, result, timestamp_ms, source, rssi, antenna)

    def on_tag_pass(
        self, epc: str, timestamp: float, rssi: float = 0, antenna: int = 0
    ):
        self.laps.on_tag_pass(epc, timestamp, rssi, antenna)

    def manual_lap(self, rider_id: int, timestamp: float = None) -> Optional[Dict]:
        return self.laps.manual_lap(rider_id, timestamp)

    # Finish/reset
    def finish_all(self, category_id: int) -> dict:
        return self.finishes.finish_all(category_id)

    def unfinish_rider(self, rider_id: int) -> bool:
        return self.finishes.unfinish_rider(rider_id)

    def edit_finish_time(self, rider_id: int, new_finish_time_ms: int) -> bool:
        return self.finishes.edit_finish_time(rider_id, new_finish_time_ms)

    def calculate_places(self, category_id: int):
        self.finishes.calculate_places(category_id)

    def reset_category(self, category_id: int) -> dict:
        return self.finishes.reset_category(category_id)

    def get_race_status(self, category_id: int = None) -> Dict[str, int]:
        return self.db.get_status_counts(category_id=category_id)
