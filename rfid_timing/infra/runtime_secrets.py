import json
import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

RUNTIME_SECRETS_PATH = "data/runtime_secrets.json"


def get_or_create_runtime_secret(
    *,
    env_name: str,
    storage_key: str,
    factory: Callable[[], str],
    label: str,
    storage_path: str = RUNTIME_SECRETS_PATH,
) -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value

    secrets_data = _load_runtime_secrets(storage_path)
    stored_value = secrets_data.get(storage_key)
    if isinstance(stored_value, str) and stored_value.strip():
        return stored_value.strip()

    generated = factory()
    secrets_data[storage_key] = generated
    if _save_runtime_secrets(secrets_data, storage_path):
        logger.warning(
            "%s не задан через %s — создан локальный fallback в %s",
            label,
            env_name,
            storage_path,
        )
        return generated

    logger.warning(
        "%s не задан через %s и не удалось сохранить fallback — значение будет временным до перезапуска",
        label,
        env_name,
    )
    return generated


def _load_runtime_secrets(storage_path: str) -> dict[str, str]:
    if not os.path.exists(storage_path):
        return {}
    try:
        with open(storage_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        logger.exception("Не удалось прочитать %s", storage_path)
        return {}


def _save_runtime_secrets(data: dict[str, str], storage_path: str) -> bool:
    try:
        os.makedirs(os.path.dirname(storage_path) or ".", exist_ok=True)
        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        logger.exception("Не удалось сохранить %s", storage_path)
        return False
