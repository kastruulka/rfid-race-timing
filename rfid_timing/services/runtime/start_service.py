import logging
import time
from typing import Any, Callable, Dict, Optional

from ...database.database import Database
from ...infra.logger import RawLogger
from ...domain.timing import is_time_limit_mode, is_time_limit_reached

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

    def _normalize_category_ids(
        self,
        category_id: Optional[int] = None,
        category_ids: Optional[list[int]] = None,
    ) -> list[int]:
        ids: list[int] = []
        if category_id is not None:
            ids.append(int(category_id))
        if category_ids:
            ids.extend(int(current_id) for current_id in category_ids)

        normalized: list[int] = []
        seen = set()
        for current_id in ids:
            if current_id in seen:
                continue
            seen.add(current_id)
            normalized.append(current_id)

        if not normalized:
            raise ValueError("Не выбраны категории для масс-старта")
        return normalized

    def _validate_mass_start_category(
        self, category_id: int
    ) -> tuple[Dict[str, Any], list[Dict]]:
        category = self.db.get_category(category_id)
        if not category:
            raise ValueError(f"Категория {category_id} не найдена")
        if self.db.is_category_closed(category_id):
            raise ValueError(f"Категория '{category['name']}' уже завершена")
        category_state = self.db.get_category_state(category_id)
        if category_state and category_state.get("started_at") is not None:
            raise ValueError(f"Категория '{category['name']}' уже запущена")

        riders = self.db.get_riders(category_id=category_id)
        available_to_start = 0
        for rider in riders:
            existing = self.db.get_result_by_rider(rider["id"])
            if existing and not self.is_prestart_result(
                existing, category_id=category_id
            ):
                continue
            available_to_start += 1

        if available_to_start == 0:
            raise ValueError(
                f"Для категории '{category['name']}' нет участников для старта"
            )
        return category, riders

    def _mass_start_category(
        self,
        category_id: int,
        start_time: float,
        category: Optional[Dict[str, Any]] = None,
        riders: Optional[list[Dict]] = None,
    ) -> Dict[str, Any]:
        if category is None or riders is None:
            category, riders = self._validate_mass_start_category(category_id)

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

    def mass_start(
        self,
        category_id: int = None,
        category_ids: Optional[list[int]] = None,
        start_time: float = None,
    ) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time() * 1000

        normalized_ids = self._normalize_category_ids(category_id, category_ids)
        prepared = []
        for current_category_id in normalized_ids:
            category, riders = self._validate_mass_start_category(current_category_id)
            prepared.append((current_category_id, category, riders))

        started_categories = [
            self._mass_start_category(
                current_category_id,
                start_time,
                category=category,
                riders=riders,
            )
            for current_category_id, category, riders in prepared
        ]

        if len(started_categories) == 1:
            return started_categories[0]

        return {
            "start_time": start_time,
            "category_ids": [entry["category_id"] for entry in started_categories],
            "categories": [entry["category"] for entry in started_categories],
            "categories_started": len(started_categories),
            "riders_started": sum(
                entry["riders_started"] for entry in started_categories
            ),
            "details": started_categories,
        }

    def individual_start(
        self, rider_id: int, start_time: float = None
    ) -> Dict[str, Any]:
        if start_time is None:
            start_time = time.time() * 1000

        rider = self.db.get_rider(rider_id)
        if not rider:
            raise ValueError(f"Участник {rider_id} не найден")

        category_id = rider["category_id"]
        category = self.db.get_category(category_id) if category_id else None
        if category_id and self.db.is_category_closed(category_id):
            raise ValueError(
                f"Категория '{category['name'] if category else category_id}' уже завершена"
            )

        if category_id:
            category_state = self.db.get_category_state(category_id)
            started_at = (
                category_state.get("started_at")
                if category_state and category_state.get("started_at") is not None
                else None
            )
            if (
                started_at is not None
                and is_time_limit_mode(category)
                and is_time_limit_reached(category, started_at, int(start_time))
            ):
                raise ValueError(
                    f"Лимит времени для категории '{category['name'] if category else category_id}' уже истек"
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
