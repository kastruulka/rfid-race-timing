import logging
import time
import threading
import json
from typing import Callable, Optional, Dict, Any

from .database import Database
from .logger import RawLogger

logger = logging.getLogger(__name__)


class RaceEngine:

    def __init__(self, db: Database, raw_logger: RawLogger,
                 on_lap: Callable = None,
                 on_finish: Callable = None,
                 on_status_change: Callable = None):
        self.db = db
        self.raw_logger = raw_logger

        self.on_lap = on_lap
        self.on_finish = on_finish
        self.on_status_change = on_status_change

        self._epc_map: Dict[str, Dict] = {}
        self._lock = threading.Lock()

        self.reload_epc_map()


    def reload_epc_map(self):
        self._epc_map = self.db.get_epc_map()
        logger.info("EPC map loaded: %d меток привязано", len(self._epc_map))


    def mass_start(self, category_id: int,
                   start_time: float = None) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time() * 1000

        category = self.db.get_category(category_id)
        if not category:
            raise ValueError(f"Категория {category_id} не найдена")

        riders = self.db.get_riders(category_id=category_id)
        started = 0

        for rider in riders:
            # проверка нет ли уже активного результата
            existing = self.db.get_result_by_rider(rider["id"])
            if existing and existing["status"] == "RACING":
                continue  # уже в гонке

            self.db.create_result(
                rider_id=rider["id"],
                category_id=category_id,
                start_time=start_time,
                status="RACING",
            )
            started += 1

        self.raw_logger.log_event("MASS_START",
                                  details=f"cat={category['name']}")

        result_info = {
            "category": category["name"],
            "category_id": category_id,
            "start_time": start_time,
            "riders_started": started,
        }

        logger.info("Масс-старт: категория '%s', участников: %d",
                     category["name"], started)

        if self.on_status_change:
            self.on_status_change({
                "event": "MASS_START", **result_info
            })

        return result_info

    def individual_start(self, rider_id: int,
                         start_time: float = None) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time()

        rider = self.db.get_rider(rider_id)
        if not rider:
            raise ValueError(f"Участник {rider_id} не найден")

        existing = self.db.get_result_by_rider(rider_id)
        if existing and existing["status"] == "RACING":
            raise ValueError(f"Участник #{rider['number']} уже в гонке")

        category_id = rider["category_id"]
        self.db.create_result(
            rider_id=rider_id,
            category_id=category_id,
            start_time=start_time,
            status="RACING",
        )

        self.raw_logger.log_event("INDIVIDUAL_START",
                                  epc=rider.get("epc", ""),
                                  details=f"rider={rider['number']}")

        result_info = {
            "event": "INDIVIDUAL_START",
            "rider_number": rider["number"],
            "rider_name": f"{rider['last_name']} {rider['first_name']}",
            "start_time": start_time,
        }

        logger.info("Раздельный старт: #%d %s %s",
                     rider["number"], rider["last_name"], rider["first_name"])

        if self.on_status_change:
            self.on_status_change(result_info)

        return result_info


    def on_tag_pass(self, epc: str, timestamp: float, rssi: float = 0, antenna: int = 0):
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

        current_laps = self.db.count_laps(result["id"])
        last_lap = self.db.get_last_lap(result["id"])
        category = self.db.get_category(result["category_id"])
        required_laps = category["laps"] if category else 1

        if last_lap:
            lap_time_ms = timestamp_ms - int(last_lap["timestamp"])
        else:
            lap_time_ms = timestamp_ms - int(float(result["start_time"]))

        lap_number = 0 if last_lap is None else current_laps + 1

        segment_data = json.dumps({str(lap_number): timestamp_ms})

        # круг в БД
        self.db.record_lap(
            result_id=result["id"],
            lap_number=lap_number,
            timestamp=timestamp_ms,
            lap_time=lap_time_ms,
            segment=segment_data,
            source="RFID",
        )

        total_time_ms = timestamp_ms - int(result["start_time"])
        lap_data = {
            "rider_id": rider["id"],
            "rider_number": rider["number"],
            "rider_name": f"{rider['last_name']} {rider['first_name']}",
            "lap_number": lap_number,
            "lap_time": lap_time_ms,
            "total_time": total_time_ms,
            "timestamp": timestamp_ms,
            "rssi": rssi,
            "antenna": antenna,
            "status": "RACING"
        }

        lap_time_sec = lap_time_ms / 1000.0
        total_time_sec = total_time_ms / 1000.0

        if lap_number == 0:
            logger.info("#%d %s — разгонный круг (%.1f сек)", rider["number"], rider["last_name"], lap_time_sec)
        else:
            logger.info("#%d %s — круг %d/%d (%.1f сек)", rider["number"], rider["last_name"], lap_number, required_laps, lap_time_sec)

        if lap_number > 0 and lap_number >= required_laps:
            self.db.update_result(result["id"], finish_time=timestamp_ms, status="FINISHED")
            lap_data["status"] = "FINISHED"
            logger.info("#%d %s — ФИНИШ! Общее время: %.1f сек", rider["number"], rider["last_name"], total_time_sec)
            self.raw_logger.log_event("FINISH", epc=epc, details=f"rider={rider['number']}")
            if self.on_finish: self.on_finish(lap_data)

        if self.on_lap: self.on_lap(lap_data)


    def manual_lap(self, rider_id: int,
                   timestamp: float = None) -> Optional[Dict]:
        if timestamp is None:
            timestamp = time.time() * 1000

        rider = self.db.get_rider(rider_id)
        if not rider:
            return None

        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "RACING":
            return None

        current_laps = self.db.count_laps(result["id"])
        last_lap = self.db.get_last_lap(result["id"])
        category = self.db.get_category(result["category_id"])
        required_laps = category["laps"] if category else 1

        if last_lap:
            lap_time = timestamp - last_lap["timestamp"]
        else:
            lap_time = timestamp - result["start_time"]

        if last_lap is None:
            lap_number = 0
        else:
            lap_number = current_laps + 1

        self.db.record_lap(result["id"], lap_number, timestamp,
                           lap_time, source="MANUAL")

        self.raw_logger.log_event("MANUAL_LAP",
                                  epc=rider.get("epc", ""),
                                  details=f"rider={rider['number']},lap={lap_number}")

        total_time = timestamp - result["start_time"]
        lap_data = {
            "rider_id": rider["id"],
            "rider_number": rider["number"],
            "rider_name": f"{rider['last_name']} {rider['first_name']}",
            "category": category["name"] if category else "?",
            "lap_number": lap_number,
            "lap_time": lap_time,
            "total_time": total_time,
            "timestamp": timestamp,
            "laps_done": lap_number if lap_number > 0 else 0,
            "laps_required": required_laps,
            "source": "MANUAL",
        }

        # финиш?
        if lap_number > 0 and lap_number >= required_laps:
            self.db.update_result(result["id"],
                                  finish_time=timestamp,
                                  status="FINISHED")
            lap_data["status"] = "FINISHED"
            if self.on_finish:
                self.on_finish(lap_data)
        else:
            lap_data["status"] = "RACING"

        if self.on_lap:
            self.on_lap(lap_data)

        return lap_data

    def set_dnf(self, rider_id: int) -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] not in ("RACING", "DNS"):
            return False

        self.db.update_result(result["id"], status="DNF")

        rider = self.db.get_rider(rider_id)
        self.raw_logger.log_event("DNF",
                                  epc=rider.get("epc", "") if rider else "",
                                  details=f"rider={rider['number']}" if rider else "")

        logger.info("#%d — DNF", rider["number"] if rider else rider_id)

        if self.on_status_change and rider:
            self.on_status_change({
                "event": "DNF",
                "rider_number": rider["number"],
                "rider_name": f"{rider['last_name']} {rider['first_name']}",
            })
        return True

    def set_dsq(self, rider_id: int, reason: str = "") -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return False

        self.db.update_result(result["id"], status="DSQ")

        rider = self.db.get_rider(rider_id)
        self.raw_logger.log_event("DSQ",
                                  epc=rider.get("epc", "") if rider else "",
                                  details=f"rider={rider['number']},reason={reason}")

        logger.info("#%d — DSQ: %s",
                     rider["number"] if rider else rider_id, reason)

        if self.on_status_change and rider:
            self.on_status_change({
                "event": "DSQ",
                "rider_number": rider["number"],
                "rider_name": f"{rider['last_name']} {rider['first_name']}",
                "reason": reason,
            })
        return True


    def calculate_places(self, category_id: int):
        results = self.db.get_results_by_category(category_id)

        finished = [r for r in results if r["status"] == "FINISHED"]
        finished.sort(key=lambda r: r["finish_time"])

        for i, r in enumerate(finished, start=1):
            self.db.update_result(r["id"], place=i)

        logger.info("Места рассчитаны для категории %d: %d финишировавших",
                     category_id, len(finished))


    def get_race_status(self, category_id: int = None) -> Dict[str, int]:
        if category_id:
            results = self.db.get_results_by_category(category_id)
        else:
            # все категории
            results = []
            for cat in self.db.get_categories():
                results.extend(self.db.get_results_by_category(cat["id"]))

        status_counts = {"RACING": 0, "FINISHED": 0, "DNF": 0,
                         "DSQ": 0, "DNS": 0}
        for r in results:
            s = r.get("status", "DNS")
            status_counts[s] = status_counts.get(s, 0) + 1

        return status_counts

    def get_live_standings(self, category_id: int) -> list:
        results = self.db.get_results_by_category(category_id)
        standings = []

        for r in results:
            laps = self.db.get_laps(r["id"])
            laps_done = sum(1 for l in laps if l["lap_number"] > 0)
            last = laps[-1] if laps else None
            total = (r["finish_time"] or (last["timestamp"] if last else 0)) \
                    - (r["start_time"] or 0)

            standings.append({
                "number": r["number"],
                "name": f"{r['last_name']} {r['first_name']}",
                "club": r.get("club", ""),
                "status": r["status"],
                "laps_done": laps_done,
                "total_time": total,
                "finish_time": r.get("finish_time"),
                "last_lap_time": last["lap_time"] if last else None,
            })

        # сортировка: FINISHED по finish_time, RACING по кругам
        def sort_key(s):
            if s["status"] == "FINISHED":
                return (0, s["finish_time"] or 0)
            elif s["status"] == "RACING":
                return (1, -s["laps_done"], s["total_time"])
            else:
                return (2, 0)

        standings.sort(key=sort_key)
        return standings