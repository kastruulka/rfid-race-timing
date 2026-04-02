from typing import Optional, Dict, List


def calc_total_time(
    result: Dict,
    last_lap_ts: Optional[int] = None,
) -> Optional[int]:
    start = result.get("start_time")
    if not start:
        return None

    start_ms = int(start)

    if result.get("finish_time") and result.get("status") == "FINISHED":
        return int(result["finish_time"]) - start_ms

    if result.get("finish_time"):
        return int(result["finish_time"]) - start_ms

    if last_lap_ts is not None:
        return int(last_lap_ts) - start_ms

    return None


def calc_total_time_with_penalty(
    result: Dict,
    last_lap_ts: Optional[int] = None,
) -> Optional[int]:
    raw = calc_total_time(result, last_lap_ts)
    if raw is None:
        return None

    if result.get("status") == "FINISHED":
        return raw

    penalty_ms = result.get("penalty_time_ms") or 0
    return raw + penalty_ms


def calc_required_laps(result: Dict, category: Optional[Dict] = None) -> int:
    base = category["laps"] if category else 1
    extra = result.get("extra_laps") or 0
    return base + extra


def is_finish_reached(lap_number: int, total_required: int) -> bool:
    return lap_number > 0 and lap_number >= total_required


def calc_finish_time(timestamp_ms: int, penalty_time_ms: int) -> int:
    return timestamp_ms + penalty_time_ms


_STATUS_ORDER = {"FINISHED": 0, "RACING": 1, "DNF": 2, "DSQ": 3, "DNS": 4}


def result_sort_key(r: Dict) -> tuple:
    status = r.get("status", "DNS")
    order = _STATUS_ORDER.get(status, 5)

    if status == "RACING":
        laps = r.get("laps_done", 0)
        total = r.get("total_time") or r.get("total") or 0
        return (order, -laps, total)

    if status == "FINISHED":
        ft = r.get("finish_time") or r.get("total_time") or 0
        return (order, ft)

    return (order, 0)


def sort_results(results: List[Dict]) -> List[Dict]:
    results.sort(key=result_sort_key)
    return results
