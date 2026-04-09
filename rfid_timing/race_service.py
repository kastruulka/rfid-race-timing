import time
from typing import Dict, List

from .database import Database
from .timing import calc_total_time_with_penalty, sort_results


def build_race_state(
    db: Database,
    category_id: int = None,
) -> dict:
    now_ms = int(time.time() * 1000)
    categories = db.get_categories()
    race_closed = db.is_race_closed()

    category_states = _build_category_states(db, now_ms)

    start_time_ms = db.get_earliest_start_time()

    all_results = _build_results(db, categories, category_id)

    feed = _build_feed(db, category_id)

    status = db.get_status_counts(category_id=category_id)

    cat_closed = False
    cat_started = False
    if category_id:
        cat_closed = db.is_category_closed(category_id)
        cs = db.get_category_state(category_id)
        cat_started = cs is not None and cs.get("started_at") is not None

    return {
        "feed": feed,
        "results": all_results,
        "status": status,
        "categories": [
            {"id": c["id"], "name": c["name"], "laps": c["laps"]} for c in categories
        ],
        "start_time": start_time_ms,
        "race_closed": race_closed,
        "category_closed": cat_closed,
        "category_started": cat_started,
        "category_states": category_states,
    }


def _build_category_states(db: Database, now_ms: int) -> dict:
    states = {}
    for cs in db.get_all_category_states():
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
    categories: List[Dict],
    category_id: int = None,
) -> list:
    rows = db.get_results_with_lap_summary(category_id=category_id)

    all_results = []
    for r in rows:
        cat_laps = r.get("cat_laps") or 1
        laps_done = r.get("laps_done") or 0
        extra_laps = r.get("extra_laps") or 0
        penalty_time_ms = r.get("penalty_time_ms") or 0

        total_time = calc_total_time_with_penalty(r, r.get("last_lap_ts"))

        all_results.append(
            {
                "rider_id": r["rider_id"],
                "number": r["number"],
                "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                "club": r.get("club", ""),
                "status": r["status"],
                "laps_done": laps_done,
                "laps_required": cat_laps,
                "total_time": total_time,
                "last_lap_time": int(r["last_lap_time"])
                if r.get("last_lap_time")
                else None,
                "finish_time": int(r["finish_time"]) if r.get("finish_time") else None,
                "penalty_time_ms": penalty_time_ms,
                "extra_laps": extra_laps,
                "dnf_reason": r.get("dnf_reason", ""),
                "laps_complete": (
                    r["status"] == "RACING"
                    and r.get("finish_time") is not None
                    and laps_done >= (cat_laps + extra_laps)
                ),
            }
        )

    return sort_results(all_results)


def _build_feed(db: Database, category_id: int = None) -> list:
    feed = []
    for item in db.get_feed_history(limit=50, category_id=category_id):
        ts_sec = item["timestamp"] / 1000.0
        lap_number = item["lap_number"]
        laps_required = (item.get("laps_required") or 1) + (item.get("extra_laps") or 0)

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
                "is_finish_lap": lap_number > 0 and lap_number >= laps_required,
            }
        )
    return feed
