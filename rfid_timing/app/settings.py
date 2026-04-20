import logging
import os
import secrets

from dotenv import load_dotenv

from ..config.config_state import ConfigState
from ..database.database import Database
from ..infra.runtime_secrets import get_or_create_runtime_secret
from ..security.auth import register_auth_routes
from ..routes.settings.settings_routes import register_settings_routes

logger = logging.getLogger(__name__)

_DOTENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(_DOTENV_PATH, override=False)


def _get_flask_secret_key() -> str:
    return get_or_create_runtime_secret(
        env_name="FLASK_SECRET_KEY",
        storage_key="flask_secret_key",
        factory=lambda: secrets.token_hex(32),
        label="FLASK secret key",
    )


def _get_env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def register_settings(
    app,
    db: Database,
    config_state: ConfigState,
    reader_mgr=None,
):
    if not app.secret_key:
        app.secret_key = _get_flask_secret_key()

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault(
        "SESSION_COOKIE_SAMESITE",
        os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    )
    app.config.setdefault(
        "SESSION_COOKIE_SECURE",
        _get_env_bool("SESSION_COOKIE_SECURE", default=False),
    )

    register_auth_routes(app)
    register_settings_routes(app, db, config_state, reader_mgr=reader_mgr)
