import functools
import hmac
import ipaddress
import json
import logging
import os
import secrets
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from flask import render_template, jsonify, request, session
from .database import Database
from .request_helpers import get_json_body

logger = logging.getLogger(__name__)


def _validate_ip(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, str):
        return False, "должен быть строкой"
    try:
        addr = ipaddress.IPv4Address(v)
    except (ipaddress.AddressValueError, ValueError):
        return False, f"невалидный IPv4: {v!r}"
    if addr.is_loopback or addr.is_multicast or addr.is_unspecified:
        return False, f"запрещённый адрес: {v}"
    return True, ""


def _validate_port(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, int):
        return False, "должен быть целым числом"
    if not (1 <= v <= 65535):
        return False, f"порт вне диапазона 1–65535: {v}"
    return True, ""


def _validate_tx_power(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, (int, float)):
        return False, "должен быть числом"
    if not (0.0 <= v <= 33.0):
        return False, f"мощность вне диапазона 0–33 dBm: {v}"
    return True, ""


def _validate_antennas(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, list) or not v:
        return False, "должен быть непустым списком"
    if len(v) > 16:
        return False, "слишком много антенн (макс 16)"
    for a in v:
        if not isinstance(a, int) or not (1 <= a <= 16):
            return False, f"номер антенны должен быть 1–16, получено: {a!r}"
    if len(set(v)) != len(v):
        return False, "дублирующиеся номера антенн"
    return True, ""


def _validate_positive_float(lo: float, hi: float, label: str):
    def _inner(v: Any) -> Tuple[bool, str]:
        if not isinstance(v, (int, float)):
            return False, f"{label}: должен быть числом"
        if not (lo <= float(v) <= hi):
            return False, f"{label}: вне диапазона {lo}–{hi}, получено: {v}"
        return True, ""

    return _inner


def _validate_bool(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, bool):
        return False, "должен быть true/false"
    return True, ""


VALIDATORS = {
    "reader_ip": _validate_ip,
    "reader_port": _validate_port,
    "tx_power": _validate_tx_power,
    "antennas": _validate_antennas,
    "rssi_window_sec": _validate_positive_float(0.1, 30.0, "rssi_window_sec"),
    "min_lap_time_sec": _validate_positive_float(1.0, 3600.0, "min_lap_time_sec"),
    "use_emulator": _validate_bool,
    "emulator_min_lap_sec": _validate_positive_float(
        1.0, 600.0, "emulator_min_lap_sec"
    ),
}


_DEFAULT_ALLOWED_NETS = [
    "169.254.0.0/16",
    "192.168.0.0/16",
    "10.0.0.0/8",
    "172.16.0.0/12",
]


def _build_allowed_networks() -> List[ipaddress.IPv4Network]:
    raw = os.environ.get("RFID_ALLOWED_NETS", "")
    cidrs = (
        [s.strip() for s in raw.split(",") if s.strip()]
        if raw
        else _DEFAULT_ALLOWED_NETS
    )
    nets = []
    for cidr in cidrs:
        try:
            nets.append(ipaddress.IPv4Network(cidr, strict=False))
        except ValueError:
            logger.warning("RFID_ALLOWED_NETS: пропущена невалидная сеть %r", cidr)
    return nets


def _is_ip_allowed(ip_str: str, allowed_nets: List[ipaddress.IPv4Network]) -> bool:
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except (ipaddress.AddressValueError, ValueError):
        return False
    if addr.is_loopback or addr.is_multicast or addr.is_unspecified:
        return False
    return any(addr in net for net in allowed_nets)


def _get_admin_password() -> str:
    password = os.environ.get("RFID_ADMIN_PASSWORD", "").strip()
    if not password:
        password = secrets.token_urlsafe(16)
        logger.warning("══════════════════════════════════════════════════════════")
        logger.warning("RFID_ADMIN_PASSWORD не задан!")
        logger.warning("Сгенерирован временный пароль: %s", password)
        logger.warning("Задайте постоянный: export RFID_ADMIN_PASSWORD=ваш_пароль")
        logger.warning("══════════════════════════════════════════════════════════")
    return password


_admin_password: Optional[str] = None


def _init_admin_password():
    global _admin_password
    if _admin_password is None:
        _admin_password = _get_admin_password()


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


def require_admin(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if _is_admin_session() or _is_admin_bearer():
            return f(*args, **kwargs)
        return jsonify(
            {
                "error": "Требуется авторизация",
                "login_url": "/api/settings/login",
            }
        ), 401

    return wrapper


def _auth_status_payload() -> Dict[str, bool]:
    return {"authenticated": _is_admin_session() or _is_admin_bearer()}


class ConfigState:
    DEFAULTS = {
        "reader_ip": "169.254.1.1",
        "reader_port": 5084,
        "tx_power": 30.0,
        "antennas": [1, 2, 3, 4],
        "rssi_window_sec": 2.0,
        "min_lap_time_sec": 120.0,
        "use_emulator": True,
        "emulator_min_lap_sec": 15.0,
    }

    def __init__(self, filepath: str = "data/settings.json"):
        self._filepath = filepath
        self._data: Dict[str, Any] = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(
                "Повреждён %s (строка %d, кол %d): %s — используются значения по умолчанию",
                self._filepath,
                e.lineno,
                e.colno,
                e.msg,
            )
            return
        except OSError as e:
            logger.error("Не удалось прочитать %s: %s", self._filepath, e)
            return

        if not isinstance(saved, dict):
            logger.error(
                "%s: ожидался JSON-объект, получен %s — игнорируется",
                self._filepath,
                type(saved).__name__,
            )
            return

        for key, value in saved.items():
            validator = VALIDATORS.get(key)
            if validator is None:
                logger.warning(
                    "%s: неизвестный ключ %r — пропущен", self._filepath, key
                )
                continue
            ok, msg = validator(value)
            if ok:
                self._data[key] = value
            else:
                logger.warning(
                    "%s: ключ %r отклонён (%s) — оставлено значение по умолчанию",
                    self._filepath,
                    key,
                    msg,
                )

    def _save(self):
        os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> dict:
        return dict(self._data)

    def update(self, **kw) -> List[str]:
        errors = []
        accepted = {}
        for key, value in kw.items():
            validator = VALIDATORS.get(key)
            if validator is None:
                continue
            ok, msg = validator(value)
            if ok:
                accepted[key] = value
            else:
                errors.append(f"{key}: {msg}")
        if accepted:
            self._data.update(accepted)
            self._save()
        return errors

    def __getitem__(self, key):
        return self._data.get(key, self.DEFAULTS.get(key))


def register_settings(app, db: Database, config_state: ConfigState, reader_mgr=None):

    if not app.secret_key:
        app.secret_key = os.environ.get(
            "FLASK_SECRET_KEY",
            secrets.token_hex(32),
        )

    allowed_nets = _build_allowed_networks()

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
        return jsonify(_auth_status_payload())

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        data = config_state.get_all()
        if reader_mgr:
            data["_reader_status"] = reader_mgr.get_status()
        data["_authenticated"] = _is_admin_session() or _is_admin_bearer()
        return jsonify(data)

    @app.route("/api/settings/reader-status", methods=["GET"])
    def api_reader_status():
        if reader_mgr:
            return jsonify(reader_mgr.get_status())
        return jsonify({"running": False, "mode": "none"})

    @app.route("/api/settings/sys-info", methods=["GET"])
    def api_sys_info():
        def file_size(path):
            try:
                size = os.path.getsize(path)
                if size < 1024:
                    return f"{size} B"
                elif size < 1024 * 1024:
                    return f"{size / 1024:.1f} KB"
                else:
                    return f"{size / 1024 / 1024:.1f} MB"
            except Exception:
                return "—"

        backups_count = 0
        if os.path.isdir("backups"):
            backups_count = len([f for f in os.listdir("backups") if f.endswith(".db")])

        return jsonify(
            {
                "db_size": file_size(db._db_path),
                "log_size": file_size("data/raw_log.csv"),
                "backups_count": backups_count,
                "race_id": db.get_current_race_id(),
                "riders_count": len(db.get_riders()),
            }
        )

    @app.route("/api/settings", methods=["PUT"])
    @require_admin
    def api_settings_put():
        data, err = get_json_body()
        if err:
            return err
        errors = config_state.update(**data)
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400
        return jsonify({"ok": True})

    @app.route("/api/settings/apply", methods=["POST"])
    @require_admin
    def api_settings_apply():
        data, err = get_json_body()
        if err:
            return err
        if data:
            errors = config_state.update(**data)
            if errors:
                return jsonify({"ok": False, "errors": errors}), 400

        if not reader_mgr:
            return jsonify(
                {
                    "ok": True,
                    "message": "Настройки сохранены (менеджер ридера недоступен)",
                }
            )

        try:
            info = reader_mgr.restart()
            mode_label = "эмулятор" if info["new_mode"] == "emulator" else "ридер"
            msg = f"Ридер перезапущен в режиме: {mode_label}"
            if info["switched"]:
                old = "эмулятор" if info["old_mode"] == "emulator" else "ридер"
                msg = f"Переключено: {old} → {mode_label}"
            return jsonify({"ok": True, "message": msg, "info": info})
        except Exception:
            logger.exception("Ошибка перезапуска ридера")
            return jsonify({"ok": False, "error": "Ошибка перезапуска ридера"}), 500

    @app.route("/api/settings/check-reader", methods=["POST"])
    @require_admin
    def api_check_reader():
        ip = config_state["reader_ip"]
        port = config_state["reader_port"]

        if config_state["use_emulator"]:
            return jsonify({"ok": True, "message": "Режим эмулятора — ридер не нужен"})

        if not _is_ip_allowed(ip, allowed_nets):
            logger.warning("check-reader: IP %s не в whitelist — отклонено", ip)
            return jsonify(
                {
                    "ok": False,
                    "error": "Адрес ридера вне разрешённого диапазона",
                }
            ), 400

        import socket

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, int(port)))
        except Exception:
            return jsonify({"ok": False, "error": f"Нет TCP-связи с {ip}:{port}"})

        try:
            s.settimeout(3)
            data = s.recv(1024)
            s.close()
            if data and len(data) >= 10:
                return jsonify(
                    {
                        "ok": True,
                        "message": f"LLRP ридер на {ip}:{port} — ответ получен",
                    }
                )
            elif data:
                return jsonify(
                    {
                        "ok": True,
                        "message": f"Соединение установлено, ответ {len(data)} байт",
                    }
                )
            else:
                return jsonify({"ok": True, "message": "TCP-соединение ОК, данных нет"})
        except Exception:
            try:
                s.close()
            except Exception:
                pass
            return jsonify(
                {"ok": True, "message": "TCP ОК, LLRP-ответ не получен за 3 сек"}
            )

    @app.route("/api/settings/backup", methods=["POST"])
    @require_admin
    def api_backup():
        try:
            db_path = db._db_path
            os.makedirs("backups", exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup_name = f"race_{ts}.db"
            backup_path = os.path.join("backups", backup_name)
            shutil.copy2(db_path, backup_path)
            return jsonify({"ok": True, "filename": backup_name})
        except Exception:
            logger.exception("Ошибка создания бэкапа")
            return jsonify({"ok": False, "error": "Ошибка создания бэкапа"}), 500

    @app.route("/api/settings/reset-race", methods=["POST"])
    @require_admin
    def api_reset_race():
        try:
            race_id = db.new_race(label="manual_reset")
            return jsonify({"ok": True, "race_id": race_id})
        except Exception:
            logger.exception("Ошибка сброса гонки")
            return jsonify({"ok": False, "error": "Ошибка сброса гонки"}), 500
