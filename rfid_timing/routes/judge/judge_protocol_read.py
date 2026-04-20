from flask import jsonify

from ...database.database import Database
from ...services.start_protocol.start_protocol_service import format_protocol_entry, get_protocol_entries
from .judge_protocol_shared import parse_query_category_ids


def register_judge_protocol_read_routes(app, db: Database):
    @app.route("/api/judge/start-protocol", methods=["GET"])
    def api_start_protocol_get():
        category_ids = parse_query_category_ids()
        if not category_ids:
            return jsonify([])
        return jsonify(get_protocol_entries(db, category_ids))

    @app.route("/api/judge/start-protocol/status", methods=["GET"])
    def api_start_protocol_status():
        category_ids = parse_query_category_ids()
        if not category_ids:
            return jsonify({"running": False})

        entries = get_protocol_entries(db, category_ids)
        if not entries:
            return jsonify({"running": False})

        has_planned = any(
            entry["status"] in {"PLANNED", "STARTING"} for entry in entries
        )
        has_started = any(entry["status"] == "STARTED" for entry in entries)
        if not has_planned and not has_started:
            return jsonify({"running": False})

        return jsonify(
            {
                "running": has_planned,
                "planned": [format_protocol_entry(entry) for entry in entries],
            }
        )
