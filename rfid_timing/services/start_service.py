import logging
import time
from typing import Any, Callable, Dict, Optional

from ..database import Database
from ..infra.logger import RawLogger

logger = logging.getLogger(__name__)


class StartService:
    def __init__(
        self,
        db: Database,
        raw_logger: RawLogger,
        on_status_change: Optional[Callable] = None,
    ):
        self.db = db
        self.raw_logger = raw_logger
        self.on_status_change = on_status_change

    def is_prestart_result(
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
            if existing and self.is_prestart_result(existing, category_id=category_id):
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
            if not self.is_prestart_result(existing, category_id=category_id):
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
        elif existing and self.is_prestart_result(existing, category_id=category_id):
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
