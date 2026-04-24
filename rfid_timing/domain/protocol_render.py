from flask import render_template


def build_columns(cols_raw: dict, is_individual_start: bool) -> dict:
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


def render_protocol_html(
    meta: dict, sections: list[dict], columns_raw: dict, template_name: str
):
    has_multiple_categories = len(sections) > 1 or any(
        section.get("combined") for section in sections
    )
    has_individual_start = any(
        section.get("extra", {}).get("is_individual_start", False)
        for section in sections
    )
    cols = build_columns(columns_raw, has_individual_start)
    if has_multiple_categories:
        cols["category"] = columns_raw.get("category", True)
    return render_template(template_name, meta=meta, sections=sections, cols=cols)


def build_protocol_pdf_name(sections: list[dict]) -> str:
    if len(sections) == 1 and not sections[0].get("combined"):
        return f"protocol_{sections[0]['category']['name']}.pdf"
    return "protocol_all_categories.pdf"
