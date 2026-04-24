import io
import json
import logging

from flask import jsonify, render_template, send_file

from ..database.database import Database
from ..http.request_helpers import get_json_body, require_int
from ..integrations.sync_payload import build_sync_export_payload
from .protocol_build import build_combined_protocol_section, build_protocol_sections
from .protocol_render import build_protocol_pdf_name, render_protocol_html

logger = logging.getLogger(__name__)


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
    all_categories = db.categories_repo.get_categories()

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


def _with_combined_section_if_needed(
    data: dict, category_ids: list[int], sections: list[dict]
):
    if len(category_ids) <= 1:
        return sections

    title = (
        "Общий зачет по выбранным категориям"
        if str(data.get("scope") or "").lower() == "selected"
        else "Общий зачет по всем категориям"
    )
    return [build_combined_protocol_section(sections, title)]


def register_protocol(app, db: Database, engine=None):
    del engine

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

        sections = build_protocol_sections(db, category_ids)
        if not sections:
            return jsonify({"error": "Категории не найдены"}), 404
        sections = _with_combined_section_if_needed(data, category_ids, sections)

        html = render_protocol_html(
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

        sections = build_protocol_sections(db, category_ids)
        if not sections:
            return jsonify({"error": "Категории не найдены"}), 404
        sections = _with_combined_section_if_needed(data, category_ids, sections)

        html = render_protocol_html(
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
                download_name=build_protocol_pdf_name(sections),
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
            category = db.categories_repo.get_category(category_ids[0])
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
