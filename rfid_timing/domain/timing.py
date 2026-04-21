from typing import Optional, Dict, List


def get_finish_mode(category: Optional[Dict] = None) -> str:
    mode = (category or {}).get("finish_mode") or "laps"
    return "time" if mode == "time" else "laps"


def is_time_limit_mode(category: Optional[Dict] = None) -> bool:
    return get_finish_mode(category) == "time" and (category or {}).get(
        "time_limit_sec"
    ) not in (None, 0, "0")


def get_time_limit_ms(category: Optional[Dict] = None) -> Optional[int]:
    if not is_time_limit_mode(category):
        return None
    return max(0, int(float((category or {}).get("time_limit_sec") or 0) * 1000))


def is_time_limit_reached(
    category: Optional[Dict],
    started_at_ms: Optional[int],
    timestamp_ms: int,
) -> bool:
    limit_ms = get_time_limit_ms(category)
    if limit_ms is None or started_at_ms is None:
        return False
    return int(timestamp_ms) > int(started_at_ms) + limit_ms


def is_rider_time_limit_reached(
    category: Optional[Dict],
    rider_started_at_ms: Optional[int],
    timestamp_ms: int,
    penalty_time_ms: int = 0,
) -> bool:
    limit_ms = get_time_limit_ms(category)
    if limit_ms is None or rider_started_at_ms is None:
        return False
    total_elapsed_ms = (
        int(timestamp_ms) - int(rider_started_at_ms) + int(penalty_time_ms or 0)
    )
    return total_elapsed_ms >= limit_ms


def lap_times_fit_time_limit(
    category: Optional[Dict],
    lap_times_ms: List[Optional[int]],
) -> bool:
    limit_ms = get_time_limit_ms(category)
    if limit_ms is None:
        return True

    elapsed_ms = 0
    for lap_time_ms in lap_times_ms:
        elapsed_ms += int(lap_time_ms or 0)
        if elapsed_ms > limit_ms:
            return False
    return True


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
    if is_time_limit_mode(category):
        return 0
    if category:
        base = category.get("laps", result.get("cat_laps", 1))
    else:
        base = result.get("cat_laps", 1)
    extra = result.get("extra_laps") or 0
    return int(base) + int(extra)


def is_finish_reached(lap_number: int, total_required: int) -> bool:
    return total_required > 0 and lap_number > 0 and lap_number >= total_required


def calc_finish_time(timestamp_ms: int, penalty_time_ms: int) -> int:
    return timestamp_ms + penalty_time_ms


def build_racing_result_update() -> Dict:
    return {
        "status": "RACING",
        "finish_time": None,
        "place": None,
        "dnf_reason": "",
    }


def build_finished_result_update(finish_time_ms: int) -> Dict:
    return {
        "status": "FINISHED",
        "finish_time": int(finish_time_ms),
        "dnf_reason": "",
    }


def build_dnf_result_update(reason: str) -> Dict:
    return {
        "status": "DNF",
        "finish_time": None,
        "place": None,
        "dnf_reason": reason,
    }


def build_dsq_result_update(reason: str = "") -> Dict:
    return {
        "status": "DSQ",
        "finish_time": None,
        "place": None,
        "dnf_reason": reason or "",
    }


def calc_time_limit_deadline_ms(
    category: Optional[Dict],
    category_started_at_ms: Optional[int],
) -> Optional[int]:
    limit_ms = get_time_limit_ms(category)
    if limit_ms is None or category_started_at_ms is None:
        return None
    return int(category_started_at_ms) + int(limit_ms)


def derive_result_state(
    result: Dict,
    category: Optional[Dict] = None,
    *,
    laps_done: Optional[int] = None,
    last_lap_ts: Optional[int] = None,
    category_started_at_ms: Optional[int] = None,
    now_ms: Optional[int] = None,
) -> Dict:
    status = result.get("status") or "DNS"
    finish_time = (
        int(result["finish_time"]) if result.get("finish_time") is not None else None
    )

    if status in {"DNF", "DSQ", "DNS"}:
        return {"status": status, "finish_time": finish_time}

    penalty_time_ms = int(result.get("penalty_time_ms") or 0)
    start_time = result.get("start_time")
    start_time_ms = int(float(start_time)) if start_time is not None else None

    if is_time_limit_mode(category):
        deadline_ms = calc_time_limit_deadline_ms(category, category_started_at_ms)
        if (
            deadline_ms is not None
            and now_ms is not None
            and int(now_ms) >= int(deadline_ms)
        ):
            return {
                "status": "FINISHED",
                "finish_time": calc_finish_time(int(deadline_ms), penalty_time_ms),
            }

        if last_lap_ts is not None and start_time_ms is not None:
            if is_rider_time_limit_reached(
                category,
                start_time_ms,
                int(last_lap_ts),
                penalty_time_ms,
            ):
                return {
                    "status": "FINISHED",
                    "finish_time": calc_finish_time(int(last_lap_ts), penalty_time_ms),
                }
            return {"status": "RACING", "finish_time": None}

        if (
            status == "FINISHED"
            and finish_time is not None
            and start_time_ms is not None
            and (finish_time - start_time_ms) >= int(get_time_limit_ms(category) or 0)
        ):
            return {"status": "FINISHED", "finish_time": finish_time}

        return {"status": "RACING", "finish_time": None}

    if laps_done is None:
        laps_done = result.get("laps_done", 0)

    required_laps = calc_required_laps(result, category)
    if (
        required_laps > 0
        and int(laps_done or 0) >= required_laps
        and last_lap_ts is not None
    ):
        return {
            "status": "FINISHED",
            "finish_time": calc_finish_time(int(last_lap_ts), penalty_time_ms),
        }

    if (
        status == "FINISHED"
        and finish_time is not None
        and (
            required_laps <= 0
            or last_lap_ts is None
            or int(laps_done or 0) >= required_laps
        )
    ):
        return {"status": "FINISHED", "finish_time": finish_time}

    return {"status": "RACING", "finish_time": None}


_STATUS_ORDER = {"FINISHED": 0, "RACING": 1, "DNF": 2, "DSQ": 3, "DNS": 4}


def result_sort_key(r: Dict) -> tuple:
    status = r.get("status", "DNS")
    order = _STATUS_ORDER.get(status, 5)
    finish_mode = r.get("finish_mode") or "laps"
    total = r.get("total_time") or r.get("total") or 0
    laps = r.get("laps_done", 0)

    if finish_mode == "time" and status in {"RACING", "FINISHED"}:
        return (0, -laps, total, r.get("number") or 0)

    if status == "RACING":
        return (order, -laps, total)

    if status == "FINISHED":
        ft = r.get("finish_time") or total
        return (order, ft)

    return (order, 0)


def sort_results(results: List[Dict]) -> List[Dict]:
    results.sort(key=result_sort_key)
    return results
