import io
import logging
from flask import render_template, jsonify, send_file
from .database import Database
from .race_engine import RaceEngine
from .request_helpers import get_json_body, require_int
from .timing import calc_total_time_with_penalty
from .formatters import fmt_ms, fmt_gap, fmt_speed, fmt_start_time, fmt_start_offset

logger = logging.getLogger(__name__)


def build_protocol_data(db: Database, engine: RaceEngine, category_id: int):
    category = db.get_category(category_id)
    if not category:
        return None, [], {}

    engine.calculate_places(category_id)

    results = db.get_results_by_category(category_id)
    distance_total = (category.get("distance_km") or 0) * category["laps"]

    start_times = {int(r["start_time"]) for r in results if r.get("start_time")}
    is_individual_start = len(start_times) > 1
    first_start_ms = min(start_times) if start_times else None

    rows = []
    leader_time = None

    for r in results:
        laps = db.get_laps(r["id"])
        laps_done = sum(1 for lap in laps if lap["lap_number"] > 0)
        penalty_time_ms = r.get("penalty_time_ms") or 0

        last_lap_ts = laps[-1]["timestamp"] if laps else None
        total_time = calc_total_time_with_penalty(r, last_lap_ts)

        if r["status"] == "FINISHED" and leader_time is None:
            leader_time = total_time

        gap = None
        if (
            r["status"] == "FINISHED"
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

        rows.append(
            {
                "place": r.get("place") or "",
                "number": r["number"],
                "last_name": r["last_name"],
                "first_name": r.get("first_name", ""),
                "name": f"{r['last_name']} {r.get('first_name', '')}".strip(),
                "birth_year": r.get("birth_year") or "",
                "club": r.get("club", ""),
                "city": r.get("city", ""),
                "status": r["status"],
                "laps_done": laps_done,
                "laps_required": category["laps"],
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
        k: cols_raw.get(k, k == "start_time" and is_individual_start) for k in col_keys
    }
    if "start_time" in cols_raw:
        cols["start_time"] = cols_raw["start_time"]
    return cols


def register_protocol(app, db: Database, engine: RaceEngine = None):

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

        category, rows, extra = build_protocol_data(db, engine, cat_id)
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

        category, rows, extra = build_protocol_data(db, engine, cat_id)
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

            pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        except ImportError:
            return jsonify({"error": "weasyprint не установлен"}), 500
        except Exception:
            logger.exception("Ошибка генерации PDF")
            return jsonify({"error": "Ошибка генерации PDF"}), 500

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"protocol_{category['name']}.pdf",
        )
