import logging
import os
import shutil
import socket
import sqlite3
import time

from flask import jsonify, render_template

from .config import DB_PATH
from .config_state import ConfigState
from .database import Database
from .request_helpers import get_json_body
from .security.auth import is_admin_authenticated, require_admin
from .security.network import build_allowed_networks, is_ip_allowed

logger = logging.getLogger(__name__)


def _format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def register_settings_routes(
    app,
    db: Database,
    config_state: ConfigState,
    reader_mgr=None,
):
    allowed_nets = build_allowed_networks()

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        data = config_state.get_all()
        data["_authenticated"] = is_admin_authenticated()
        if reader_mgr:
            try:
                data["_reader_status"] = reader_mgr.get_status()
            except Exception:
                logger.exception("Не удалось получить статус ридера")
        return jsonify(data)

    @app.route("/api/settings/reader-status", methods=["GET"])
    def api_settings_reader_status():
        if not reader_mgr:
            return jsonify({"running": False, "mode": "none"})
        return jsonify(reader_mgr.get_status())

    @app.route("/api/settings/sys-info", methods=["GET"])
    def api_settings_sys_info():
        def file_size(path: str) -> int:
            return os.path.getsize(path) if os.path.exists(path) else 0

        backups_dir = os.path.join("data", "backups")
        db_size = file_size(DB_PATH)
        log_size = file_size(os.path.join("data", "raw_log.csv"))
        backups_count = (
            len([name for name in os.listdir(backups_dir) if name.endswith(".db")])
            if os.path.isdir(backups_dir)
            else 0
        )
        riders_count = len(db.get_riders()) if db else 0
        race_id = db.get_current_race_id() if db else None

        return jsonify(
            {
                "db_size": _format_bytes(db_size),
                "log_size": _format_bytes(log_size),
                "backups_count": backups_count,
                "race_id": race_id,
                "riders_count": riders_count,
            }
        )

    @app.route("/api/settings", methods=["PUT"])
    @require_admin
    def api_settings_put():
        data, err = get_json_body()
        if err:
            return err

        try:
            updated = config_state.update(**data)
            return jsonify({"ok": True, "settings": updated})
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

    @app.route("/api/settings/apply", methods=["POST"])
    @require_admin
    def api_settings_apply():
        data, err = get_json_body()
        if err:
            return err

        try:
            settings = config_state.update(**data)
        except ValueError as exc:
            return jsonify({"ok": False, "errors": [str(exc)]}), 400

        if reader_mgr:
            try:
                status = reader_mgr.restart()
            except Exception as exc:
                logger.exception("Не удалось применить настройки ридера")
                return (
                    jsonify(
                        {
                            "ok": False,
                            "error": f"Не удалось перезапустить ридер: {exc}",
                        }
                    ),
                    500,
                )
        else:
            status = {"switched": False}

        return jsonify(
            {
                "ok": True,
                "settings": settings,
                "reader_status": status,
                "message": "Настройки применены",
            }
        )

    @app.route("/api/settings/check-reader", methods=["POST"])
    @require_admin
    def api_settings_check_reader():
        reader_ip = config_state["reader_ip"]
        reader_port = config_state["reader_port"]

        if config_state["use_emulator"]:
            return jsonify({"ok": True, "message": "Включен режим эмулятора"})

        if not is_ip_allowed(reader_ip, allowed_nets):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "IP ридера вне разрешенных локальных подсетей",
                    }
                ),
                400,
            )

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        try:
            sock.connect((reader_ip, reader_port))
            return jsonify(
                {
                    "ok": True,
                    "message": f"Ридер доступен по {reader_ip}:{reader_port}",
                }
            )
        except OSError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        finally:
            sock.close()

    @app.route("/api/settings/backup", methods=["POST"])
    @require_admin
    def api_settings_backup():
        backups_dir = os.path.join("data", "backups")
        os.makedirs(backups_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"race_{timestamp}.db"
        dst_path = os.path.join(backups_dir, filename)

        try:
            if db and hasattr(db, "_conn"):
                src_conn = db._conn()
                with sqlite3.connect(dst_path) as backup_conn:
                    src_conn.backup(backup_conn)
            else:
                shutil.copy2(DB_PATH, dst_path)
        except Exception as exc:
            logger.exception("Не удалось создать бэкап БД")
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "filename": filename})

    @app.route("/api/settings/reset-race", methods=["POST"])
    @require_admin
    def api_settings_reset_race():
        if not db:
            return jsonify({"ok": False, "error": "База данных недоступна"}), 500

        try:
            race_id = db.create_race(label="reset")
        except Exception as exc:
            logger.exception("Не удалось создать новую гоночную сессию")
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "race_id": race_id})
