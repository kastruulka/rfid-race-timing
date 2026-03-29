import io
import time
from flask import (
    render_template, jsonify, request, Response, send_file,
)
from .database import Database
from .race_engine import RaceEngine


def fmt_ms(ms):
    if ms is None:
        return "—"
    total_sec = abs(ms) / 1000.0
    m = int(total_sec // 60)
    s = total_sec % 60
    return f"{m:02d}:{s:04.1f}"


def fmt_gap(ms):
    if ms is None or ms == 0:
        return ""
    return "+" + fmt_ms(ms)


def fmt_speed(distance_km, time_ms):
    if not distance_km or not time_ms or time_ms <= 0:
        return "—"
    hours = time_ms / 1000.0 / 3600.0
    return f"{distance_km / hours:.1f}"


def fmt_start_time(start_time_ms):
    if start_time_ms is None:
        return "—"
    ts_sec = start_time_ms / 1000.0
    return time.strftime("%H:%M:%S", time.localtime(ts_sec))


def fmt_start_offset(start_time_ms, first_start_ms):
    if start_time_ms is None or first_start_ms is None:
        return ""
    diff_ms = start_time_ms - first_start_ms
    if diff_ms <= 0:
        return "00:00"
    total_sec = diff_ms / 1000.0
    m = int(total_sec // 60)
    s = int(total_sec) % 60
    return f"+{m:02d}:{s:02d}"


def build_protocol_data(db: Database, engine: RaceEngine,
                        category_id: int):
    category = db.get_category(category_id)
    if not category:
        return None, [], {}

    engine.calculate_places(category_id)

    results = db.get_results_by_category(category_id)
    distance_total = (category.get("distance_km") or 0) * category["laps"]

    rows = []
    leader_time = None

    start_times = set()
    for r in results:
        st = r.get("start_time")
        if st:
            start_times.add(int(st))

    is_individual_start = len(start_times) > 1
    first_start_ms = min(start_times) if start_times else None

    for r in results:
        laps = db.get_laps(r["id"])
        laps_done = sum(1 for l in laps if l["lap_number"] > 0)

        penalty_time_ms = r.get("penalty_time_ms") or 0

        total_time = None
        if r["status"] == "FINISHED":
            if r.get("finish_time") and r.get("start_time"):
                total_time = int(r["finish_time"]) - int(r["start_time"])
            elif laps and r.get("start_time"):
                total_time = int(laps[-1]["timestamp"]) - int(r["start_time"])
        elif laps and r.get("start_time"):
            raw_time = int(laps[-1]["timestamp"]) - int(r["start_time"])
            total_time = raw_time + penalty_time_ms

        if r["status"] == "FINISHED" and leader_time is None:
            leader_time = total_time

        gap = None
        if (r["status"] == "FINISHED" and leader_time is not None
                and total_time is not None and total_time != leader_time):
            gap = total_time - leader_time

        lap_details = []
        for l in laps:
            if l["lap_number"] > 0:
                lap_details.append({
                    "number": l["lap_number"],
                    "time": fmt_ms(int(l["lap_time"]) if l.get("lap_time") else None),
                })

        rider_start_ms = int(r["start_time"]) if r.get("start_time") else None

        rows.append({
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
            "penalty_str": ("+" + fmt_ms(penalty_time_ms)) if penalty_time_ms else "",
            "gap": gap,
            "gap_str": fmt_gap(gap),
            "avg_speed": fmt_speed(distance_total, total_time),
            "lap_details": lap_details,
            "start_time_abs": fmt_start_time(rider_start_ms),
            "start_time_offset": fmt_start_offset(rider_start_ms, first_start_ms),
        })

    extra = {
        "is_individual_start": is_individual_start,
        "first_start_ms": first_start_ms,
    }

    return category, rows, extra


def register_protocol(app, db: Database, engine: RaceEngine = None):

    @app.route("/protocol")
    def protocol_page():
        return render_template("protocol.html")

    @app.route("/api/protocol/preview", methods=["POST"])
    def api_protocol_preview():
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        category, rows, extra = build_protocol_data(db, engine, int(cat_id))
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        meta = data.get("meta", {})
        cols_raw = data.get("columns", {})

        default_start_time = extra.get("is_individual_start", False)

        cols = {k: cols_raw.get(k, k == "start_time" and default_start_time)
                for k in [
            "place", "number", "name", "birth_year", "club",
            "city", "start_time", "time", "gap", "laps", "speed", "status"]}

        if "start_time" in cols_raw:
            cols["start_time"] = cols_raw["start_time"]

        html = render_template(
            "protocol_content.html",
            meta=meta, category=category, rows=rows,
            cols=cols, extra=extra,
        )
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.route("/api/protocol/pdf", methods=["POST"])
    def api_protocol_pdf():
        data = request.get_json(force=True)
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400

        category, rows, extra = build_protocol_data(db, engine, int(cat_id))
        if not category:
            return jsonify({"error": "Категория не найдена"}), 404

        meta = data.get("meta", {})
        cols_raw = data.get("columns", {})

        default_start_time = extra.get("is_individual_start", False)
        cols = {k: cols_raw.get(k, k == "start_time" and default_start_time)
                for k in [
            "place", "number", "name", "birth_year", "club",
            "city", "start_time", "time", "gap", "laps", "speed", "status"]}
        if "start_time" in cols_raw:
            cols["start_time"] = cols_raw["start_time"]

        html = render_template(
            "protocol_pdf.html",
            meta=meta, category=category, rows=rows,
            cols=cols, extra=extra,
        )

        try:
            from weasyprint import HTML as WeasyprintHTML
            pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        except ImportError:
            return jsonify({"error":
                "weasyprint не установлен. "
                "Установите: pip install weasyprint"}), 500
        except Exception as e:
            return jsonify({"error": f"Ошибка PDF: {str(e)}"}), 500

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"protocol_{category['name']}.pdf",
        )