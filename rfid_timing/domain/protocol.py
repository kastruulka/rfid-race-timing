import io
import json
import logging

from flask import jsonify, render_template, send_file

from ..database.database import Database
from ..http.request_helpers import get_json_body, require_int
from ..integrations.sync_payload import build_sync_export_payload
from ..utils.formatters import (
    fmt_gap,
    fmt_ms,
    fmt_speed,
    fmt_start_offset,
    fmt_start_time,
)
from .timing import (
    calc_total_time_with_penalty,
    get_finish_mode,
    get_time_limit_ms,
    sort_results,
)

logger = logging.getLogger(__name__)


def _calculate_preview_places(results: list[dict]) -> dict[int, int]:
    ranked = sort_results(results[:])
    places = {}
    place = 1
    for result in ranked:
        if result.get("status") in {"DNF", "DSQ", "DNS"}:
            continue
        places[result["id"]] = place
        place += 1
    return places


def _estimate_time_mode_distance_km(
    category: dict,
    result: dict,
    laps: list[dict],
    total_time_ms: int | None,
) -> float:
    lap_distance_km = float(category.get("distance_km") or 0)
    if lap_distance_km <= 0 or total_time_ms is None:
        return 0.0

    counted_laps = [lap for lap in laps if lap.get("lap_number", 0) > 0]
    laps_done = len(counted_laps)
    distance_km = lap_distance_km * laps_done

    start_time_ms = result.get("start_time")
    if not start_time_ms:
        return distance_km

    penalty_time_ms = int(result.get("penalty_time_ms") or 0)
    elapsed_without_penalty_ms = max(0, int(total_time_ms) - penalty_time_ms)

    if not counted_laps:
        return distance_km

    last_counted_lap = counted_laps[-1]
    elapsed_at_last_lap_ms = int(last_counted_lap["timestamp"]) - int(
        float(start_time_ms)
    )
    partial_elapsed_ms = elapsed_without_penalty_ms - elapsed_at_last_lap_ms
    if partial_elapsed_ms <= 0:
        return distance_km

    reference_lap_time_ms = int(last_counted_lap.get("lap_time") or 0)
    if reference_lap_time_ms <= 0:
        positive_lap_times = [
            int(lap["lap_time"])
            for lap in counted_laps
            if int(lap.get("lap_time") or 0) > 0
        ]
        if not positive_lap_times:
            return distance_km
        reference_lap_time_ms = int(sum(positive_lap_times) / len(positive_lap_times))

    partial_lap_fraction = min(partial_elapsed_ms / reference_lap_time_ms, 0.999)
    return distance_km + lap_distance_km * partial_lap_fraction


def build_protocol_data(db: Database, category_id: int):
    category = db.get_category(category_id)
    if not category:
        return None, [], {}

    results = db.get_results_by_category(category_id)
    finish_mode = get_finish_mode(category)

    enriched_results = []
    for result in results:
        laps = db.get_laps(result["id"])
        laps_done = sum(1 for lap in laps if lap["lap_number"] > 0)
        last_lap_ts = laps[-1]["timestamp"] if laps else None
        enriched = dict(result)
        enriched["laps_done"] = laps_done
        enriched["total_time"] = calc_total_time_with_penalty(result, last_lap_ts)
        enriched["finish_mode"] = finish_mode
        enriched_results.append(enriched)

    preview_places = _calculate_preview_places(enriched_results)
    start_times = {int(r["start_time"]) for r in results if r.get("start_time")}
    is_individual_start = len(start_times) > 1
    first_start_ms = min(start_times) if start_times else None

    rows = []
    leader_time = None
    time_limit_ms = get_time_limit_ms(category) if finish_mode == "time" else None

    for r in sort_results(enriched_results):
        laps = db.get_laps(r["id"])
        laps_done = r["laps_done"]
        penalty_time_ms = r.get("penalty_time_ms") or 0
        total_time = r["total_time"]

        if r["status"] in {"RACING", "FINISHED"} and leader_time is None:
            leader_time = total_time

        gap = None
        if (
            r["status"] in {"RACING", "FINISHED"}
            and leader_time is not None
            and total_time is not None
            and total_time != leader_time
        ):
            gap = total_time - leader_time

        warmup_lap = next(
            (
                {
                    "number": lap["lap_number"],
                    "time": fmt_ms(
                        int(lap["lap_time"]) if lap.get("lap_time") else None
                    ),
                }
                for lap in laps
                if lap["lap_number"] == 0
            ),
            None,
        )

        lap_details = [
            {
                "number": lap["lap_number"],
                "time": fmt_ms(int(lap["lap_time"]) if lap.get("lap_time") else None),
            }
            for lap in laps
            if lap["lap_number"] > 0
        ]

        rider_start_ms = int(r["start_time"]) if r.get("start_time") else None
        if finish_mode == "time":
            distance_total = _estimate_time_mode_distance_km(
                category, r, laps, total_time
            )
        else:
            effective_laps = category["laps"] + (r.get("extra_laps") or 0)
            distance_total = (category.get("distance_km") or 0) * effective_laps

        finished_by_penalty_limit = (
            finish_mode == "time"
            and r["status"] == "FINISHED"
            and penalty_time_ms > 0
            and total_time is not None
            and time_limit_ms is not None
            and total_time >= time_limit_ms
        )

        rows.append(
            {
                "place": preview_places.get(r["id"], ""),
                "number": r["number"],
                "last_name": r["last_name"],
                "first_name": r.get("first_name", ""),
                "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                "birth_year": r.get("birth_year") or "",
                "club": r.get("club", ""),
                "city": r.get("city", ""),
                "status": r["status"],
                "laps_done": laps_done,
                "laps_required": category["laps"] if finish_mode == "laps" else None,
                "finish_mode": finish_mode,
                "time_limit_sec": category.get("time_limit_sec"),
                "total_time": total_time,
                "total_time_str": fmt_ms(total_time),
                "penalty_time_ms": penalty_time_ms,
                "penalty_str": ("+" + fmt_ms(penalty_time_ms))
                if penalty_time_ms
                else "",
                "gap": gap,
                "gap_str": fmt_gap(gap),
                "avg_speed": fmt_speed(distance_total, total_time),
                "warmup_lap": warmup_lap,
                "warmup_lap_time": warmup_lap["time"] if warmup_lap else "",
                "lap_details": lap_details,
                "laps_display": (
                    " / ".join(item["time"] for item in lap_details)
                    if lap_details
                    else "--"
                ),
                "laps_subnote": (
                    (
                        (f"{laps_done} кр. · " if laps_done else "")
                        + "финиш по лимиту с учетом штрафа"
                    )
                    if finished_by_penalty_limit
                    else (
                        f"{laps_done} кр."
                        if finish_mode == "time" and laps_done
                        else ""
                    )
                ),
                "start_time_abs": fmt_start_time(rider_start_ms),
                "start_time_offset": fmt_start_offset(rider_start_ms, first_start_ms),
            }
        )

    extra = {
        "is_individual_start": is_individual_start,
        "first_start_ms": first_start_ms,
    }
    return category, rows, extra


def _build_columns(cols_raw: dict, is_individual_start: bool) -> dict:
    col_keys = [
        "place",
        "number",
        "name",
        "birth_year",
        "club",
        "city",
        "start_time",
        "time",
        "gap",
        "warmup_lap",
        "laps",
        "speed",
        "status",
    ]
    cols = {
        key: cols_raw.get(key, key == "start_time" and is_individual_start)
        for key in col_keys
    }
    if "start_time" in cols_raw:
        cols["start_time"] = cols_raw["start_time"]
    return cols


def register_protocol(app, db: Database, engine=None):
    @app.route("/protocol")
    def protocol_page():
        return render_template("protocol.html")

    @app.route("/api/protocol/preview", methods=["POST"])
    def api_protocol_preview():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err

        category, rows, extra = build_protocol_data(db, cat_id)
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        cols = _build_columns(
            data.get("columns", {}), extra.get("is_individual_start", False)
        )
        html = render_template(
            "protocol_content.html",
            meta=data.get("meta", {}),
            category=category,
            rows=rows,
            cols=cols,
            extra=extra,
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/protocol/pdf", methods=["POST"])
    def api_protocol_pdf():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err

        category, rows, extra = build_protocol_data(db, cat_id)
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        cols = _build_columns(
            data.get("columns", {}), extra.get("is_individual_start", False)
        )
        html = render_template(
            "protocol_pdf.html",
            meta=data.get("meta", {}),
            category=category,
            rows=rows,
            cols=cols,
            extra=extra,
        )

        try:
            from weasyprint import HTML as WeasyprintHTML

            pdf = WeasyprintHTML(string=html).write_pdf()
            return send_file(
                io.BytesIO(pdf),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=f"protocol_{category['name']}.pdf",
            )
        except ImportError:
            return jsonify({"error": "WeasyPrint не установлен"}), 500
        except Exception as exc:
            logger.exception("protocol_pdf failed")
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/protocol/sync-export", methods=["POST"])
    def api_protocol_sync_export():
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err

        try:
            payload = build_sync_export_payload(db, category_id=cat_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

        category = db.get_category(cat_id)
        category_name = category["name"] if category else f"category-{cat_id}"
        json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return send_file(
            io.BytesIO(json_bytes),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"sync-export-{category_name}.json",
        )
