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
    fmt_start_offset_precise,
    fmt_start_time,
    fmt_start_time_precise,
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


def _calculate_places_from_sorted(results: list[dict]) -> dict[int, int]:
    places = {}
    place = 1
    for result in results:
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
    start_times = {
        int(result["start_time"]) for result in results if result.get("start_time")
    }
    is_individual_start = len(start_times) > 1
    first_start_ms = min(start_times) if start_times else None

    rows = []
    leader_time = None
    time_limit_ms = get_time_limit_ms(category) if finish_mode == "time" else None

    for result in sort_results(enriched_results):
        laps = db.get_laps(result["id"])
        laps_done = result["laps_done"]
        penalty_time_ms = result.get("penalty_time_ms") or 0
        total_time = result["total_time"]

        if result["status"] in {"RACING", "FINISHED"} and leader_time is None:
            leader_time = total_time

        gap = None
        if (
            result["status"] in {"RACING", "FINISHED"}
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

        rider_start_ms = int(result["start_time"]) if result.get("start_time") else None
        if finish_mode == "time":
            distance_total = _estimate_time_mode_distance_km(
                category, result, laps, total_time
            )
        else:
            effective_laps = category["laps"] + (result.get("extra_laps") or 0)
            distance_total = (category.get("distance_km") or 0) * effective_laps

        finished_by_penalty_limit = (
            finish_mode == "time"
            and result["status"] == "FINISHED"
            and penalty_time_ms > 0
            and total_time is not None
            and time_limit_ms is not None
            and total_time >= time_limit_ms
        )

        rows.append(
            {
                "id": result["id"],
                "place": preview_places.get(result["id"], ""),
                "number": result["number"],
                "last_name": result["last_name"],
                "first_name": result.get("first_name", ""),
                "name": f"{result['last_name']} {result.get('first_name', '')}".strip(),
                "birth_year": result.get("birth_year") or "",
                "club": result.get("club", ""),
                "city": result.get("city", ""),
                "category_id": category["id"],
                "category_name": category["name"],
                "status": result["status"],
                "laps_done": laps_done,
                "laps_required": category["laps"] if finish_mode == "laps" else None,
                "finish_mode": finish_mode,
                "time_limit_sec": category.get("time_limit_sec"),
                "total_time": total_time,
                "total_time_str": fmt_ms(total_time),
                "finish_time": result.get("finish_time"),
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
                "start_time_abs_precise": fmt_start_time_precise(rider_start_ms),
                "start_time_offset": fmt_start_offset(rider_start_ms, first_start_ms),
                "start_time_offset_precise": fmt_start_offset_precise(
                    rider_start_ms, first_start_ms
                ),
                "start_time_ms": rider_start_ms,
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
        "category",
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


def _parse_category_ids(raw_ids) -> list[int]:
    if raw_ids is None:
        return []

    if isinstance(raw_ids, str):
        raw_values = [part.strip() for part in raw_ids.split(",")]
    elif isinstance(raw_ids, (list, tuple)):
        raw_values = raw_ids
    else:
        raw_values = [raw_ids]

    category_ids = []
    seen = set()
    for raw_value in raw_values:
        if raw_value in (None, ""):
            continue
        try:
            category_id = int(raw_value)
        except (TypeError, ValueError):
            continue
        if category_id <= 0 or category_id in seen:
            continue
        seen.add(category_id)
        category_ids.append(category_id)
    return category_ids


def _resolve_protocol_category_ids(
    db: Database, data: dict
) -> tuple[list[int], str | None]:
    scope = str(data.get("scope") or "single").strip().lower()
    all_categories = db.get_categories()

    if scope == "all":
        category_ids = [int(category["id"]) for category in all_categories]
        if not category_ids:
            return [], "Категории не найдены"
        return category_ids, None

    if scope == "selected":
        category_ids = _parse_category_ids(data.get("category_ids"))
        if not category_ids:
            return [], "Выберите хотя бы одну категорию"
        available_ids = {int(category["id"]) for category in all_categories}
        filtered_ids = [
            category_id for category_id in category_ids if category_id in available_ids
        ]
        if not filtered_ids:
            return [], "Выбранные категории не найдены"
        return filtered_ids, None

    cat_id, err = require_int(data, "category_id", "Категория не выбрана")
    if err:
        return [], "Категория не выбрана"
    return [cat_id], None


def _build_protocol_sections(db: Database, category_ids: list[int]) -> list[dict]:
    sections = []
    for category_id in category_ids:
        category, rows, extra = build_protocol_data(db, category_id)
        if not category:
            continue
        sections.append({"category": category, "rows": rows, "extra": extra})
    return sections


def _combined_effective_total_ms(
    row: dict, earliest_start_ms: int | None
) -> int | None:
    total_time = row.get("total_time")
    if total_time is not None:
        return int(total_time)

    finish_time = row.get("finish_time")
    start_time_ms = row.get("start_time_ms")
    if finish_time is not None and start_time_ms is not None:
        return int(finish_time) - int(start_time_ms)

    return None


def _combined_progress_sort_key(row: dict) -> tuple:
    status = row.get("status", "DNS")
    number = row.get("number") or 0
    progress_ms = row.get("combined_effective_total_ms")

    if row.get("finish_mode") == "time" and status in {"RACING", "FINISHED"}:
        return (0, -(row.get("laps_done", 0) or 0), progress_ms or 10**18, number)

    if status == "FINISHED":
        return (0, progress_ms or 10**18, number)

    if status == "RACING":
        return (
            1,
            -(row.get("laps_done", 0) or 0),
            progress_ms or 10**18,
            number,
        )

    status_order = {"DNF": 2, "DSQ": 3, "DNS": 4}
    return (status_order.get(status, 5), 0, number)


def _sort_combined_protocol_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=_combined_progress_sort_key)


def _combined_progress_gap_ms(row: dict, leader_row: dict | None) -> int | None:
    if leader_row is None:
        return None
    if row.get("status") not in {"RACING", "FINISHED"}:
        return None

    row_progress = row.get("combined_effective_total_ms")
    leader_progress = leader_row.get("combined_effective_total_ms")

    if (
        row_progress is None
        or leader_progress is None
        or row_progress == leader_progress
    ):
        return None

    return int(row_progress) - int(leader_progress)


def _build_combined_protocol_section(sections: list[dict], title: str) -> dict:
    merged_rows = []
    category_names = []
    start_times = set()

    for section in sections:
        category = section["category"]
        extra = section.get("extra", {})
        category_names.append(category["name"])
        if extra.get("first_start_ms") is not None:
            start_times.add(int(extra["first_start_ms"]))

        for row in section["rows"]:
            merged_rows.append(dict(row))

    earliest_start_ms = min(start_times) if start_times else None
    for row in merged_rows:
        row["combined_effective_total_ms"] = _combined_effective_total_ms(
            row, earliest_start_ms
        )
        row["start_time_display"] = row.get("start_time_abs_precise") or row.get(
            "start_time_abs"
        )
        row["start_time_offset_display"] = row.get(
            "start_time_offset_precise"
        ) or row.get("start_time_offset")

    ranked_rows = _sort_combined_protocol_rows(merged_rows)
    preview_places = _calculate_places_from_sorted(ranked_rows)

    leader_time = None
    for row in ranked_rows:
        if row["status"] in {"RACING", "FINISHED"}:
            leader_time = row
            break

    for row in ranked_rows:
        row["place"] = preview_places.get(row["id"], "")
        gap = _combined_progress_gap_ms(row, leader_time)
        row["gap"] = gap
        row["gap_str"] = fmt_gap(gap)

    return {
        "combined": True,
        "title": title,
        "category_names": category_names,
        "rows": ranked_rows,
        "extra": {
            "is_individual_start": len(start_times) > 1,
            "combined": True,
        },
    }


def _render_protocol_html(
    meta: dict, sections: list[dict], columns_raw: dict, template_name: str
):
    has_multiple_categories = len(sections) > 1 or any(
        section.get("combined") for section in sections
    )
    has_individual_start = any(
        section.get("extra", {}).get("is_individual_start", False)
        for section in sections
    )
    cols = _build_columns(columns_raw, has_individual_start)
    if has_multiple_categories:
        cols["category"] = columns_raw.get("category", True)
    return render_template(template_name, meta=meta, sections=sections, cols=cols)


def _build_protocol_pdf_name(sections: list[dict]) -> str:
    if len(sections) == 1 and not sections[0].get("combined"):
        return f"protocol_{sections[0]['category']['name']}.pdf"
    return "protocol_all_categories.pdf"


def register_protocol(app, db: Database, engine=None):
    @app.route("/protocol")
    def protocol_page():
        return render_template("protocol.html")

    @app.route("/api/protocol/preview", methods=["POST"])
    def api_protocol_preview():
        data, err = get_json_body()
        if err:
            return err

        category_ids, error_message = _resolve_protocol_category_ids(db, data)
        if error_message:
            return jsonify({"error": error_message}), 400

        sections = _build_protocol_sections(db, category_ids)
        if not sections:
            return jsonify({"error": "Категории не найдены"}), 404
        if len(category_ids) > 1:
            title = (
                "Общий зачет по выбранным категориям"
                if str(data.get("scope") or "").lower() == "selected"
                else "Общий зачет по всем категориям"
            )
            sections = [_build_combined_protocol_section(sections, title)]

        html = _render_protocol_html(
            meta=data.get("meta", {}),
            sections=sections,
            columns_raw=data.get("columns", {}),
            template_name="protocol_content.html",
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/protocol/pdf", methods=["POST"])
    def api_protocol_pdf():
        data, err = get_json_body()
        if err:
            return err

        category_ids, error_message = _resolve_protocol_category_ids(db, data)
        if error_message:
            return jsonify({"error": error_message}), 400

        sections = _build_protocol_sections(db, category_ids)
        if not sections:
            return jsonify({"error": "Категории не найдены"}), 404
        if len(category_ids) > 1:
            title = (
                "Общий зачет по выбранным категориям"
                if str(data.get("scope") or "").lower() == "selected"
                else "Общий зачет по всем категориям"
            )
            sections = [_build_combined_protocol_section(sections, title)]

        html = _render_protocol_html(
            meta=data.get("meta", {}),
            sections=sections,
            columns_raw=data.get("columns", {}),
            template_name="protocol_pdf.html",
        )

        try:
            from weasyprint import HTML as WeasyprintHTML

            pdf = WeasyprintHTML(string=html).write_pdf()
            return send_file(
                io.BytesIO(pdf),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=_build_protocol_pdf_name(sections),
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
        category_ids, error_message = _resolve_protocol_category_ids(db, data)
        if error_message:
            return jsonify({"error": error_message}), 400

        try:
            payload = build_sync_export_payload(db, category_ids=category_ids)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 404

        if len(category_ids) == 1:
            category = db.get_category(category_ids[0])
            export_name = (
                category["name"] if category else f"category-{category_ids[0]}"
            )
        else:
            export_name = "all-categories"
        json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return send_file(
            io.BytesIO(json_bytes),
            mimetype="application/json",
            as_attachment=True,
            download_name=f"sync-export-{export_name}.json",
        )
