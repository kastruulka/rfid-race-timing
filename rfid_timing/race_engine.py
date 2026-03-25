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
            existing = self.db.get_result_by_rider(rider["id"])
            if existing:
                continue

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
            self.on_status_change({"event": "MASS_START", **result_info})

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


    def on_tag_pass(self, epc: str, timestamp: float,
                    rssi: float = 0, antenna: int = 0):
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

        extra_laps = result.get("extra_laps") or 0
        total_required = required_laps + extra_laps

        if last_lap:
            lap_time_ms = timestamp_ms - int(last_lap["timestamp"])
        else:
            lap_time_ms = timestamp_ms - int(float(result["start_time"]))

        lap_number = 0 if last_lap is None else current_laps + 1

        segment_data = json.dumps({str(lap_number): timestamp_ms})

        self.db.record_lap(
            result_id=result["id"],
            lap_number=lap_number,
            timestamp=timestamp_ms,
            lap_time=lap_time_ms,
            segment=segment_data,
            source="RFID",
        )

        penalty_time_ms = result.get("penalty_time_ms") or 0
        total_time_ms = timestamp_ms - int(result["start_time"]) + penalty_time_ms

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
            "status": "RACING",
            "penalty_time_ms": penalty_time_ms,
            "extra_laps": extra_laps,
        }

        lap_time_sec = lap_time_ms / 1000.0

        if lap_number == 0:
            logger.info("#%d %s — разгонный круг (%.1f сек)",
                        rider["number"], rider["last_name"], lap_time_sec)
        else:
            logger.info("#%d %s — круг %d/%d (%.1f сек)",
                        rider["number"], rider["last_name"],
                        lap_number, total_required, lap_time_sec)

        if lap_number > 0 and lap_number >= total_required:
            finish_time_ms = timestamp_ms + penalty_time_ms
            self.db.update_result(result["id"],
                                  finish_time=finish_time_ms,
                                  status="FINISHED")
            lap_data["status"] = "FINISHED"
            total_sec = total_time_ms / 1000.0
            logger.info("#%d %s — ФИНИШ! Общее время: %.1f сек"
                        + (" (штраф: +%.1f сек)" % (penalty_time_ms/1000.0)
                           if penalty_time_ms else ""),
                        rider["number"], rider["last_name"], total_sec)
            self.raw_logger.log_event("FINISH", epc=epc,
                                      details=f"rider={rider['number']}")
            if self.on_finish:
                self.on_finish(lap_data)

        if self.on_lap:
            self.on_lap(lap_data)


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
        extra_laps = result.get("extra_laps") or 0
        total_required = required_laps + extra_laps

        if last_lap:
            lap_time = timestamp - last_lap["timestamp"]
        else:
            lap_time = timestamp - result["start_time"]

        lap_number = 0 if last_lap is None else current_laps + 1

        self.db.record_lap(result["id"], lap_number, timestamp,
                           lap_time, source="MANUAL")

        self.raw_logger.log_event("MANUAL_LAP",
                                  epc=rider.get("epc", ""),
                                  details=f"rider={rider['number']},lap={lap_number}")

        penalty_time_ms = result.get("penalty_time_ms") or 0
        total_time = timestamp - result["start_time"] + penalty_time_ms

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
            "laps_required": total_required,
            "source": "MANUAL",
        }

        if lap_number > 0 and lap_number >= total_required:
            finish_time = timestamp + penalty_time_ms
            self.db.update_result(result["id"],
                                  finish_time=finish_time,
                                  status="FINISHED")
            lap_data["status"] = "FINISHED"
            if self.on_finish:
                self.on_finish(lap_data)
        else:
            lap_data["status"] = "RACING"

        if self.on_lap:
            self.on_lap(lap_data)

        return lap_data

    def finish_all(self, category_id: int) -> dict:
        results = self.db.get_results_by_category(category_id)
        finished = 0
        dnf_count = 0
 
        for r in results:
            if r["status"] != "RACING":
                continue
            if r.get("finish_time"):
                self.db.update_result(r["id"], status="FINISHED")
                finished += 1
            else:
                self.db.update_result(r["id"], status="DNF",
                                      dnf_reason="Гонка завершена судьёй")
                self.db.add_penalty(r["id"], "DNF", value=0,
                                    reason="Гонка завершена судьёй")
                dnf_count += 1
 
        self.calculate_places(category_id)
 
        self.db.close_race()
 
        logger.info("Гонка завершена: категория %d, финиш: %d, DNF: %d",
                    category_id, finished, dnf_count)
 
        return {"finished": finished, "dnf_count": dnf_count}
 
    def unfinish_rider(self, rider_id: int) -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "FINISHED":
            return False
 
        if self.db.is_race_closed():
            return False
 
        last_lap = self.db.get_last_lap(result["id"])
        if last_lap:
            self.db.delete_lap(last_lap["id"])

        self.db.update_result(result["id"], status="RACING",
                              finish_time=None)
 
        rider = self.db.get_rider(rider_id)
        logger.info("#%d %s — финиш отменён, возврат в RACING",
                    rider["number"] if rider else rider_id,
                    rider["last_name"] if rider else "")
 
        self.raw_logger.log_event(
            "UNFINISH", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']}" if rider else "")
 
        return True

    def edit_finish_time(self, rider_id: int,
                         new_finish_time_ms: int) -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] != "FINISHED":
            return False
        if self.db.is_race_closed():
            return False
 
        old_time = result.get("finish_time")
        self.db.update_result(result["id"],
                              finish_time=new_finish_time_ms)
 
        rider = self.db.get_rider(rider_id)
        logger.info("#%d %s — время финиша изменено: %s → %s",
                    rider["number"] if rider else rider_id,
                    rider["last_name"] if rider else "",
                    old_time, new_finish_time_ms)
 
        self.raw_logger.log_event(
            "EDIT_FINISH", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},old={old_time},new={new_finish_time_ms}")
 
        return True
    
    DNF_REASONS = {
        "voluntary": "Добровольный сход",
        "mechanical": "Механическая поломка",
        "injury": "Травма",
        "other": "Другое",
    }

    def set_dnf(self, rider_id: int, reason_code: str = "",
                reason_text: str = "") -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result or result["status"] not in ("RACING", "DNS", "FINISHED"):
            return False

        reason = self.DNF_REASONS.get(reason_code, reason_text or reason_code)

        self.db.update_result(result["id"], status="DNF", dnf_reason=reason)

        self.db.add_penalty(result["id"], "DNF", value=0, reason=reason)

        rider = self.db.get_rider(rider_id)
        self.raw_logger.log_event(
            "DNF", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},reason={reason}" if rider else "")

        logger.info("#%d — DNF: %s",
                    rider["number"] if rider else rider_id, reason)

        if self.on_status_change and rider:
            self.on_status_change({
                "event": "DNF",
                "rider_number": rider["number"],
                "rider_name": f"{rider['last_name']} {rider['first_name']}",
                "reason": reason,
            })
        return True


    def set_dsq(self, rider_id: int, reason: str = "") -> bool:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return False

        self.db.update_result(result["id"], status="DSQ")

        self.db.add_penalty(result["id"], "DSQ", reason=reason)

        rider = self.db.get_rider(rider_id)
        self.raw_logger.log_event(
            "DSQ", epc=rider.get("epc", "") if rider else "",
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


    def add_time_penalty(self, rider_id: int, seconds: float,
                         reason: str = "") -> Optional[Dict]:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return None

        pid = self.db.add_penalty(result["id"], "TIME_PENALTY",
                                  value=seconds, reason=reason)
        self.db.recalc_penalties(result["id"])

        rider = self.db.get_rider(rider_id)
        logger.info("#%d — штраф +%.0f сек: %s",
                    rider["number"] if rider else rider_id, seconds, reason)

        self.raw_logger.log_event(
            "TIME_PENALTY", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},sec={seconds},reason={reason}")

        return {"id": pid, "type": "TIME_PENALTY",
                "value": seconds, "reason": reason}

    def add_extra_lap(self, rider_id: int, laps: int = 1,
                      reason: str = "") -> Optional[Dict]:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return None

        pid = self.db.add_penalty(result["id"], "EXTRA_LAP",
                                  value=laps, reason=reason)
        self.db.recalc_penalties(result["id"])

        rider = self.db.get_rider(rider_id)
        logger.info("#%d — штрафной круг (+%d): %s",
                    rider["number"] if rider else rider_id, laps, reason)

        self.raw_logger.log_event(
            "EXTRA_LAP", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},laps={laps},reason={reason}")

        return {"id": pid, "type": "EXTRA_LAP",
                "value": laps, "reason": reason}

    def add_warning(self, rider_id: int,
                    reason: str = "") -> Optional[Dict]:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return None

        pid = self.db.add_penalty(result["id"], "WARNING",
                                  value=0, reason=reason)

        rider = self.db.get_rider(rider_id)
        logger.info("#%d — предупреждение: %s",
                    rider["number"] if rider else rider_id, reason)

        self.raw_logger.log_event(
            "WARNING", epc=rider.get("epc", "") if rider else "",
            details=f"rider={rider['number']},reason={reason}")

        return {"id": pid, "type": "WARNING",
                "value": 0, "reason": reason}

    def remove_penalty(self, penalty_id: int) -> bool:
        row = self.db._exec(
            "SELECT result_id, type FROM penalty WHERE id=?",
            (penalty_id,)).fetchone()
        if not row:
            return False
 
        result_id = row["result_id"]
        penalty_type = row["type"]
 
        self.db.delete_penalty(penalty_id)
        self.db.recalc_penalties(result_id)

        if penalty_type in ("DNF", "DSQ"):
            result = self.db._exec(
                "SELECT status FROM result WHERE id=?",
                (result_id,)).fetchone()
            if result and result["status"] == penalty_type:
                self.db.update_result(result_id, status="RACING",
                                      dnf_reason="")
 
        logger.info("Штраф #%d (%s) удалён, пересчёт result #%d",
                    penalty_id, penalty_type, result_id)
        return True

    def get_rider_penalties(self, rider_id: int) -> list:
        result = self.db.get_result_by_rider(rider_id)
        if not result:
            return []
        return self.db.get_penalties(result["id"])


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
            results = []
            for cat in self.db.get_categories():
                results.extend(
                    self.db.get_results_by_category(cat["id"]))

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

            penalty_time_ms = r.get("penalty_time_ms") or 0
            extra_laps = r.get("extra_laps") or 0

            total = ((r["finish_time"] or
                      (last["timestamp"] if last else 0))
                     - (r["start_time"] or 0))

            standings.append({
                "number": r["number"],
                "name": f"{r['last_name']} {r['first_name']}",
                "club": r.get("club", ""),
                "status": r["status"],
                "laps_done": laps_done,
                "total_time": total,
                "finish_time": r.get("finish_time"),
                "last_lap_time": last["lap_time"] if last else None,
                "penalty_time_ms": penalty_time_ms,
                "extra_laps": extra_laps,
                "dnf_reason": r.get("dnf_reason", ""),
            })

        def sort_key(s):
            if s["status"] == "FINISHED":
                return (0, s["finish_time"] or 0)
            elif s["status"] == "RACING":
                return (1, -s["laps_done"], s["total_time"])
            else:
                return (2, 0)

        standings.sort(key=sort_key)
        return standings