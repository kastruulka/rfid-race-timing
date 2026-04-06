import functools
import hmac
import os
import secrets
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import jsonify, request, session

from ..request_helpers import get_json_body
from ..runtime_secrets import get_or_create_runtime_secret

_DOTENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)
load_dotenv(_DOTENV_PATH, override=False)

_admin_password: Optional[str] = None


def _resolve_admin_password() -> str:
    return get_or_create_runtime_secret(
        env_name="RFID_ADMIN_PASSWORD",
        storage_key="admin_password",
        factory=lambda: secrets.token_urlsafe(16),
        label="Пароль администратора",
    )


def _init_admin_password():
    global _admin_password
    if _admin_password is None:
        _admin_password = _resolve_admin_password()


def _check_password(candidate: str) -> bool:
    _init_admin_password()
    return hmac.compare_digest(candidate, _admin_password)


def _is_admin_session() -> bool:
    return session.get("is_admin") is True


def _is_admin_bearer() -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return _check_password(auth[7:])


def is_admin_authenticated() -> bool:
    return _is_admin_session() or _is_admin_bearer()


def auth_status_payload() -> Dict[str, bool]:
    return {"authenticated": is_admin_authenticated()}


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if is_admin_authenticated():
            return f(*args, **kwargs)
        return jsonify(
            {
                "error": "Требуется авторизация",
                "login_url": "/api/settings/login",
            }
        ), 401

    return wrapper


def register_auth_routes(app) -> None:
    @app.route("/api/settings/login", methods=["POST"])
    @app.route("/api/auth/login", methods=["POST"])
    def api_settings_login():
        data, err = get_json_body()
        if err:
            return err
        password = data.get("password", "")
        if not password or not isinstance(password, str):
            return jsonify({"error": "Введите пароль"}), 400
        if _check_password(password):
            session["is_admin"] = True
            session.permanent = True
            return jsonify({"ok": True})
        return jsonify({"error": "Неверный пароль"}), 403

    @app.route("/api/settings/logout", methods=["POST"])
    @app.route("/api/auth/logout", methods=["POST"])
    def api_settings_logout():
        session.pop("is_admin", None)
        return jsonify({"ok": True})

    @app.route("/api/settings/auth-status", methods=["GET"])
    @app.route("/api/auth/status", methods=["GET"])
    def api_settings_auth_status():
        return jsonify(auth_status_payload())
