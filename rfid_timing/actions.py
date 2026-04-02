import logging
from typing import Optional, Tuple, Dict, Any

from .race_engine import RaceEngine

logger = logging.getLogger(__name__)

ResponseTuple = Tuple[Dict[str, Any], int]


def action_mass_start(engine: RaceEngine, category_id: int) -> ResponseTuple:
    try:
        info = engine.mass_start(category_id)
        return {"ok": True, "info": info}, 200
    except ValueError as e:
        logger.warning("mass_start: %s", e)
        return {"error": "Невозможно запустить категорию"}, 400
    except Exception as e:
        logger.warning("mass_start: %s", e)
        return {"error": "Неверный запрос"}, 400


def action_individual_start(
    engine: RaceEngine,
    rider_id: int,
    start_time: Optional[float] = None,
) -> ResponseTuple:
    try:
        info = engine.individual_start(rider_id, start_time=start_time)
        return {"ok": True, "info": info}, 200
    except ValueError as e:
        logger.warning("individual_start: %s", e)
        return {"error": "Невозможно стартовать участника"}, 400
    except Exception as e:
        logger.warning("individual_start: %s", e)
        return {"error": "Неверный запрос"}, 400


def action_manual_lap(engine: RaceEngine, rider_id: int) -> ResponseTuple:
    result = engine.manual_lap(rider_id)
    if not result:
        return {"error": "Невозможно — участник не в гонке"}, 400
    return {"ok": True, "result": result}, 200


def action_dnf(
    engine: RaceEngine,
    rider_id: int,
    reason_code: str = "",
    reason_text: str = "",
) -> ResponseTuple:
    ok = engine.set_dnf(rider_id, reason_code=reason_code, reason_text=reason_text)
    if not ok:
        return {"error": "Невозможно — участник не в гонке"}, 400
    return {"ok": True}, 200


def action_dsq(engine: RaceEngine, rider_id: int, reason: str = "") -> ResponseTuple:
    ok = engine.set_dsq(rider_id, reason=reason)
    if not ok:
        return {"error": "Невозможно"}, 400
    return {"ok": True}, 200
