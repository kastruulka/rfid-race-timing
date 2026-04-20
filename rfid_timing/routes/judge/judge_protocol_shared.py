from flask import request


def parse_category_ids(data: dict) -> list[int]:
    category_ids = data.get("category_ids")
    if category_ids is not None:
        if not isinstance(category_ids, list):
            raise ValueError("category_ids must be a list")
        raw_ids = category_ids
    elif data.get("category_id") is not None:
        raw_ids = [data.get("category_id")]
    else:
        raise ValueError("Категория не выбрана")

    normalized_ids: list[int] = []
    seen = set()
    for value in raw_ids:
        current_id = int(value)
        if current_id in seen:
            continue
        seen.add(current_id)
        normalized_ids.append(current_id)

    if not normalized_ids:
        raise ValueError("Категория не выбрана")
    return normalized_ids


def parse_query_category_ids() -> list[int]:
    raw = request.args.get("category_ids", "").strip()
    if raw:
        return parse_category_ids(
            {"category_ids": [part.strip() for part in raw.split(",") if part.strip()]}
        )

    category_id = request.args.get("category_id", type=int)
    if category_id is None:
        return []
    return [int(category_id)]
