import logging
import time
import threading
import json
from typing import Callable, Optional, Dict, Any

from .database import Database
from .logger import RawLogger
from .penalty_service import PenaltyService
from .timing import calc_required_laps, is_finish_reached, calc_finish_time

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

        self._epc_map: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.reload_epc_map()

    def _is_prestart_result(
        self, result: Optional[Dict], category_id: int = None
    ) -> bool:
        if not result:
            return False
        if category_id is not None and result.get("category_id") != category_id:
            return False
        if result.get("finish_time") is not None:
            return False
        if self.db.count_laps(result["id"]) > 0:
            return False
        state = (
            self.db.get_category_state(result.get("category_id"))
            if result.get("category_id")
            else None
        )
        category_started = state is not None and state.get("started_at") is not None
        return not category_started

    def reload_epc_map(self):
        self._epc_map = self.db.get_epc_map()
        logger.info("EPC map loaded: %d меток привязано", len(self._epc_map))

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

    def mass_start(self, category_id: int, start_time: float = None) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time() * 1000

        category = self.db.get_category(category_id)
        if not category:
            raise ValueError(f"Категория {category_id} не найдена")
        if self.db.is_category_closed(category_id):
            raise ValueError(f"Категория '{category['name']}' уже завершена")
        category_state = self.db.get_category_state(category_id)
        if category_state and category_state.get("started_at") is not None:
            raise ValueError(f"Категория '{category['name']}' уже запущена")

        riders = self.db.get_riders(category_id=category_id)
        started = 0
        for rider in riders:
            existing = self.db.get_result_by_rider(rider["id"])
            if existing and self._is_prestart_result(existing, category_id=category_id):
                self.db.update_result(
                    existing["id"],
                    category_id=category_id,
                    start_time=start_time,
                    finish_time=None,
                    status="RACING",
                    place=None,
                    dnf_reason="",
                )
                started += 1
                continue
            if existing:
                continue
            self.db.create_result(
                rider_id=rider["id"],
                category_id=category_id,
                start_time=start_time,
                status="RACING",
            )
            started += 1

        if started == 0:
            raise ValueError(
                f"Для категории '{category['name']}' нет участников для старта"
            )

        self.db.set_category_started(category_id, start_time)
        self.raw_logger.log_event("MASS_START", details=f"cat={category['name']}")

        info = {
            "category": category["name"],
            "category_id": category_id,
            "start_time": start_time,
            "riders_started": started,
        }
        logger.info(
            "Масс-старт: категория '%s', участников: %d", category["name"], started
        )

        if self.on_status_change:
            self.on_status_change({"event": "MASS_START", **info})
        return info

    def individual_start(
        self, rider_id: int, start_time: float = None
    ) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time() * 1000

        rider = self.db.get_rider(rider_id)
        if not rider:
            raise ValueError(f"Участник {rider_id} не найден")

        category_id = rider["category_id"]
        if category_id and self.db.is_category_closed(category_id):
            category = self.db.get_category(category_id)
            raise ValueError(
                f"Категория '{category['name'] if category else category_id}' уже завершена"
            )

        existing = self.db.get_result_by_rider(rider_id)
        if existing and existing["status"] == "RACING":
            if not self._is_prestart_result(existing, category_id=category_id):
                raise ValueError(f"Участник #{rider['number']} уже в гонке")
            self.db.update_result(
                existing["id"],
                category_id=category_id,
                start_time=start_time,
                finish_time=None,
                status="RACING",
                place=None,
                dnf_reason="",
            )
        elif existing and self._is_prestart_result(existing, category_id=category_id):
            self.db.update_result(
                existing["id"],
                category_id=category_id,
                start_time=start_time,
                finish_time=None,
                status="RACING",
                place=None,
                dnf_reason="",
            )
        else:
            self.db.create_result(
                rider_id=rider_id,
                category_id=category_id,
                start_time=start_time,
                status="RACING",
            )
        if category_id:
            self.db.set_category_started(category_id, start_time)

        self.raw_logger.log_event(
            "INDIVIDUAL_START",
            epc=rider.get("epc", ""),
            details=f"rider={rider['number']}",
        )

        info = {
            "event": "INDIVIDUAL_START",
            "rider_number": rider["number"],
            "rider_name": f"{rider['last_name']} {rider['first_name']}",
            "start_time": start_time,
        }
        logger.info(
            "Раздельный старт: #%d %s %s",
            rider["number"],
            rider["last_name"],
            rider["first_name"],
        )

        if self.on_status_change:
            self.on_status_change(info)
        return info

    def _record_lap(
        self,
        rider: Dict,
        result: Dict,
        timestamp_ms: int,
        source: str = "RFID",
        rssi: float = 0,
        antenna: int = 0,
    ) -> Optional[Dict]:
        """Общая логика записи круга для RFID и ручного ввода."""
        current_laps = self.db.count_laps(result["id"])
        last_lap = self.db.get_last_lap(result["id"])
        category = self.db.get_category(result["category_id"])
        has_warmup_lap = (
            True if category is None else bool(category.get("has_warmup_lap", 1))
        )
        total_required = calc_required_laps(result, category)
        penalty_time_ms = result.get("penalty_time_ms") or 0

        if last_lap:
            lap_time_ms = timestamp_ms - int(last_lap["timestamp"])
        else:
            lap_time_ms = timestamp_ms - int(float(result["start_time"]))

        if last_lap is None and lap_time_ms < MIN_START_TO_FIRST_PASS_MS:
            logger.info(
                "#%d %s — пропуск ложного первого срабатывания через %.1f сек после старта",
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
                "#%d %s — разгонный круг (%.1f сек)",
                rider["number"],
                rider["last_name"],
                lap_time_ms / 1000.0,
            )
        else:
            logger.info(
                "#%d %s — круг %d/%d (%.1f сек)",
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
        }

        if is_finish_reached(lap_number, total_required):
            finish_time_ms = calc_finish_time(timestamp_ms, penalty_time_ms)
            self.db.update_result(
                result["id"], finish_time=finish_time_ms, status="FINISHED"
            )
            lap_data["status"] = "FINISHED"

            penalty_info = (
                f" (штраф: +{penalty_time_ms / 1000.0:.1f} сек)"
                if penalty_time_ms
                else ""
            )
            logger.info(
                "#%d %s — ФИНИШ! Общее время: %.1f сек%s",
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

        if self.on_lap:
            self.on_lap(lap_data)

        return lap_data

    def on_tag_pass(
        self, epc: str, timestamp: float, rssi: float = 0, antenna: int = 0
    ):
        self.raw_logger.log_pass(timestamp, epc, rssi, antenna)
        timestamp_ms = int(timestamp * 1000)

        with self._lock:
            rider = self._epc_map.get(epc)
        if not rider:
            logger.debug("Неизвестная метка: %s", epc)
            return

        result = self.db.get_result_by_rider(rider["id"])
        if not result or result["status"] != "RACING":
            return
        if result.get("category_id") and self.db.is_category_closed(
            result["category_id"]
        ):
            return

        self._record_lap(
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
        return self._record_lap(rider, result, int(timestamp), source="MANUAL")

    def finish_all(self, category_id: int) -> dict:
        results = self.db.get_results_by_category(category_id)
        newly_finished = 0
        newly_dnf = 0

        for r in results:
            if r["status"] != "RACING":
                continue
            if r.get("finish_time"):
                self.db.update_result(r["id"], status="FINISHED")
                newly_finished += 1
            else:
                self.db.update_result(
                    r["id"], status="DNF", dnf_reason="Гонка завершена судьёй"
                )
                self.db.add_penalty(
                    r["id"], "DNF", value=0, reason="Гонка завершена судьёй"
                )
                newly_dnf += 1

        self.calculate_places(category_id)
        self.db.close_category(category_id)

        final_results = self.db.get_results_by_category(category_id)
        finished = sum(1 for r in final_results if r["status"] == "FINISHED")
        dnf_count = sum(1 for r in final_results if r["status"] in ("DNF", "DSQ"))

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

        cat_id = result.get("category_id")
        if cat_id and self.db.is_category_closed(cat_id):
            return False

        last_lap = self.db.get_last_lap(result["id"])
        if last_lap:
            self.db.delete_lap(last_lap["id"])

        self.db.update_result(result["id"], status="RACING", finish_time=None)

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

        cat_id = result.get("category_id")
        if cat_id and self.db.is_category_closed(cat_id):
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
        results = self.db.get_results_by_category(category_id)
        finished = sorted(
            [r for r in results if r["status"] == "FINISHED"],
            key=lambda r: r["finish_time"],
        )
        for i, r in enumerate(finished, start=1):
            self.db.update_result(r["id"], place=i)
        logger.info(
            "Места рассчитаны для категории %d: %d финишировавших",
            category_id,
            len(finished),
        )

    def reset_category(self, category_id: int) -> dict:
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

    def get_race_status(self, category_id: int = None) -> Dict[str, int]:
        return self.db.get_status_counts(category_id=category_id)
