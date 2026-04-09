import functools
import hmac
import os
import secrets
import threading
import time
from typing import Dict, Optional

from dotenv import load_dotenv
from flask import jsonify, request, session

from ..http.request_helpers import get_json_body
from ..infra.runtime_secrets import get_or_create_runtime_secret

_DOTENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", ".env")
)
load_dotenv(_DOTENV_PATH, override=False)

CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_PROTECTED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

LOGIN_RATE_LIMIT_WINDOW_SEC = 300
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = 5
LOGIN_RATE_LIMIT_LOCK_SEC = 300

_admin_password: Optional[str] = None
_admin_api_token: Optional[str] = None
_login_rate_limit_lock = threading.Lock()
_login_attempts: Dict[str, Dict[str, float]] = {}


def _get_env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_admin_password() -> str:
    return get_or_create_runtime_secret(
        env_name="RFID_ADMIN_PASSWORD",
        storage_key="admin_password",
        factory=lambda: secrets.token_urlsafe(16),
        label="Пароль администратора",
    )


def _resolve_admin_api_token() -> str:
    return get_or_create_runtime_secret(
        env_name="RFID_ADMIN_API_TOKEN",
        storage_key="admin_api_token",
        factory=lambda: secrets.token_urlsafe(32),
        label="API-токен администратора",
    )


def _init_admin_password():
    global _admin_password
    if _admin_password is None:
        _admin_password = _resolve_admin_password()


def _init_admin_api_token():
    global _admin_api_token
    if _admin_api_token is None:
        _admin_api_token = _resolve_admin_api_token()


def _check_password(candidate: str) -> bool:
    _init_admin_password()
    return hmac.compare_digest(
        candidate.encode("utf-8"),
        _admin_password.encode("utf-8"),
    )


def _check_api_token(candidate: str) -> bool:
    _init_admin_api_token()
    return hmac.compare_digest(
        candidate.encode("utf-8"),
        _admin_api_token.encode("utf-8"),
    )


def _is_admin_session() -> bool:
    return session.get("is_admin") is True


def _is_admin_bearer() -> bool:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return False
    token = auth[7:].strip()
    if not token:
        return False
    return _check_api_token(token)


def _get_or_create_csrf_token() -> str:
    token = session.get("csrf_token")
    if isinstance(token, str) and token:
        return token
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    return token


def _has_valid_csrf_token() -> bool:
    expected = session.get("csrf_token")
    provided = request.headers.get(CSRF_HEADER_NAME, "").strip()
    if not expected or not provided:
        return False
    return hmac.compare_digest(
        str(expected).encode("utf-8"),
        provided.encode("utf-8"),
    )


def _csrf_error_response():
    return jsonify({"error": "CSRF token missing or invalid"}), 403


def _get_client_key() -> str:
    if _get_env_bool("RFID_TRUST_PROXY_HEADERS", default=False):
        forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
        if forwarded_for:
            return forwarded_for.split(",")[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def _prune_login_attempts(now: float) -> None:
    stale_keys = []
    for key, state in _login_attempts.items():
        locked_until = float(state.get("locked_until", 0))
        last_attempt = float(state.get("last_attempt", 0))
        if locked_until > now:
            continue
        if last_attempt and now - last_attempt <= LOGIN_RATE_LIMIT_WINDOW_SEC:
            continue
        stale_keys.append(key)
    for key in stale_keys:
        _login_attempts.pop(key, None)


def _check_login_rate_limit() -> Optional[tuple]:
    now = time.time()
    client_key = _get_client_key()
    with _login_rate_limit_lock:
        _prune_login_attempts(now)
        state = _login_attempts.get(client_key)
        if not state:
            return None
        locked_until = float(state.get("locked_until", 0))
        if locked_until <= now:
            return None
        retry_after = max(1, int(locked_until - now))

    response = jsonify(
        {
            "error": "Слишком много попыток входа. Попробуйте позже.",
            "retry_after_sec": retry_after,
        }
    )
    response.headers["Retry-After"] = str(retry_after)
    return response, 429


def _record_login_failure() -> None:
    now = time.time()
    client_key = _get_client_key()
    with _login_rate_limit_lock:
        _prune_login_attempts(now)
        state = _login_attempts.get(client_key)
        if (
            not state
            or now - float(state.get("first_attempt", 0)) > LOGIN_RATE_LIMIT_WINDOW_SEC
        ):
            state = {
                "count": 0,
                "first_attempt": now,
                "last_attempt": now,
                "locked_until": 0.0,
            }

        state["count"] = int(state.get("count", 0)) + 1
        state["last_attempt"] = now
        if state["count"] >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            state["locked_until"] = now + LOGIN_RATE_LIMIT_LOCK_SEC
            state["count"] = 0
            state["first_attempt"] = now
        _login_attempts[client_key] = state


def _reset_login_rate_limit() -> None:
    client_key = _get_client_key()
    with _login_rate_limit_lock:
        _login_attempts.pop(client_key, None)


def is_admin_authenticated() -> bool:
    return _is_admin_session() or _is_admin_bearer()


def auth_status_payload() -> Dict[str, object]:
    payload: Dict[str, object] = {"authenticated": is_admin_authenticated()}
    if _is_admin_session():
        payload["csrf_token"] = _get_or_create_csrf_token()
    return payload


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if _is_admin_session():
            if request.method in CSRF_PROTECTED_METHODS and not _has_valid_csrf_token():
                return _csrf_error_response()
            return f(*args, **kwargs)
        if _is_admin_bearer():
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
        rate_limit_response = _check_login_rate_limit()
        if rate_limit_response is not None:
            return rate_limit_response

        data, err = get_json_body()
        if err:
            return err
        password = data.get("password", "")
        if not password or not isinstance(password, str):
            return jsonify({"error": "Введите пароль"}), 400
        if _check_password(password):
            _reset_login_rate_limit()
            session["is_admin"] = True
            session.permanent = True
            return jsonify({"ok": True, "csrf_token": _get_or_create_csrf_token()})

        _record_login_failure()
        return jsonify({"error": "Неверный пароль"}), 403

    @app.route("/api/settings/logout", methods=["POST"])
    @app.route("/api/auth/logout", methods=["POST"])
    def api_settings_logout():
        if _is_admin_session() and not _has_valid_csrf_token():
            return _csrf_error_response()
        session.pop("is_admin", None)
        session.pop("csrf_token", None)
        return jsonify({"ok": True})

    @app.route("/api/settings/auth-status", methods=["GET"])
    @app.route("/api/auth/status", methods=["GET"])
    def api_settings_auth_status():
        return jsonify(auth_status_payload())
