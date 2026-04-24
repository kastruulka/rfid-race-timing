import time

from ..database.database import Database
from .timing import (
    calc_total_time_with_penalty,
    derive_result_state,
    get_finish_mode,
    sort_results,
)


def build_race_state(
    db: Database,
    engine=None,
    category_id: int = None,
) -> dict:
    now_ms = int(time.time() * 1000)
    categories = db.categories_repo.get_categories()
    race_closed = db.race_repo.is_race_closed()

    category_states = _build_category_states(db, now_ms)

    start_time_ms = db.race_repo.get_earliest_start_time()

    all_results = _build_results(db, now_ms, category_id)

    feed = _build_feed(db, category_id)

    status = db.results_repo.get_status_counts(category_id=category_id)

    cat_closed = False
    cat_started = False
    if category_id:
        cat_closed = db.category_state_repo.is_category_closed(category_id)
        cs = db.category_state_repo.get_category_state(category_id)
        cat_started = cs is not None and cs.get("started_at") is not None

    return {
        "feed": feed,
        "results": all_results,
        "status": status,
        "categories": [
            {
                "id": c["id"],
                "name": c["name"],
                "laps": c["laps"],
                "finish_mode": get_finish_mode(c),
                "time_limit_sec": c.get("time_limit_sec"),
            }
            for c in categories
        ],
        "start_time": start_time_ms,
        "race_closed": race_closed,
        "category_closed": cat_closed,
        "category_started": cat_started,
        "category_states": category_states,
    }


def _build_category_states(db: Database, now_ms: int) -> dict:
    states = {}
    for cs in db.category_state_repo.get_all_category_states():
        cid = cs["category_id"]
        started = cs.get("started_at")
        closed = cs.get("closed_at")

        elapsed = None
        if started is not None:
            elapsed = (int(closed * 1000) if closed else now_ms) - int(started)

        states[str(cid)] = {
            "started_at": started,
            "closed_at": closed,
            "closed": closed is not None,
            "elapsed_ms": elapsed,
        }
    return states


def _build_results(
    db: Database,
    now_ms: int,
    category_id: int = None,
) -> list:
    rows = db.results_repo.get_results_with_lap_summary(category_id=category_id)
    category_states = {
        state["category_id"]: state
        for state in db.category_state_repo.get_all_category_states()
    }

    all_results = []
    for r in rows:
        cat_laps = r.get("cat_laps") or 1
        category_meta = {
            "laps": cat_laps,
            "finish_mode": r.get("cat_finish_mode"),
            "time_limit_sec": r.get("cat_time_limit_sec"),
        }
        finish_mode = get_finish_mode(category_meta)
        laps_done = r.get("laps_done") or 0
        extra_laps = r.get("extra_laps") or 0
        penalty_time_ms = r.get("penalty_time_ms") or 0

        total_time = calc_total_time_with_penalty(r, r.get("last_lap_ts"))
        category_state = category_states.get(r.get("category_id"))
        category_started_at = (
            int(category_state["started_at"])
            if category_state and category_state.get("started_at") is not None
            else None
        )
        derived = derive_result_state(
            r,
            category_meta,
            laps_done=laps_done,
            last_lap_ts=r.get("last_lap_ts"),
            category_started_at_ms=category_started_at,
            now_ms=now_ms,
        )
        status = derived["status"]
        finish_time = derived["finish_time"]
        if (
            status == "FINISHED"
            and finish_time is not None
            and r.get("start_time")
            and (r["status"] != status or r.get("finish_time") != finish_time)
        ):
            total_time = finish_time - int(r.get("start_time") or 0)

        all_results.append(
            {
                "rider_id": r["rider_id"],
                "number": r["number"],
                "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                "club": r.get("club", ""),
                "status": status,
                "laps_done": laps_done,
                "laps_required": cat_laps if finish_mode == "laps" else None,
                "total_time": total_time,
                "last_lap_time": int(r["last_lap_time"])
                if r.get("last_lap_time")
                else None,
                "finish_time": finish_time,
                "penalty_time_ms": penalty_time_ms,
                "extra_laps": extra_laps,
                "dnf_reason": r.get("dnf_reason", ""),
                "finish_mode": finish_mode,
                "time_limit_sec": r.get("cat_time_limit_sec"),
                "laps_complete": (
                    finish_mode == "laps"
                    and status == "RACING"
                    and finish_time is not None
                    and laps_done >= (cat_laps + extra_laps)
                ),
            }
        )

    ranked_results = sort_results(all_results)
    place = 1
    for item in ranked_results:
        if item["status"] in {"DNF", "DSQ", "DNS"}:
            item["rank"] = None
            continue
        item["rank"] = place
        place += 1

    return ranked_results


def _build_feed(db: Database, category_id: int = None) -> list:
    feed = []
    for item in db.feed_repo.get_feed_history(limit=50, category_id=category_id):
        ts_sec = item["timestamp"] / 1000.0
        lap_number = item["lap_number"]
        finish_mode = get_finish_mode(item)
        laps_required = None
        if finish_mode == "laps":
            laps_required = (item.get("laps_required") or 1) + (
                item.get("extra_laps") or 0
            )

        feed.append(
            {
                "lap_id": item["lap_id"],
                "rider_number": item["rider_number"],
                "rider_name": f"{item['last_name']} {item.get('first_name', '')}".strip(),
                "lap_number": lap_number,
                "lap_time": int(item["lap_time"]) if item.get("lap_time") else None,
                "laps_required": laps_required,
                "extra_laps": item.get("extra_laps") or 0,
                "time_str": time.strftime("%H:%M:%S", time.localtime(ts_sec)),
                "is_finish_lap": (
                    finish_mode == "laps"
                    and lap_number > 0
                    and laps_required is not None
                    and lap_number >= laps_required
                ),
                "finish_mode": finish_mode,
                "time_limit_sec": item.get("time_limit_sec"),
            }
        )
    return feed
