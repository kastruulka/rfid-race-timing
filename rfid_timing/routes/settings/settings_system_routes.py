import logging
import os
import shutil
import sqlite3
import time

from flask import jsonify

from ...config.config import DB_PATH
from ...database.database import Database
from ...security.auth import require_admin

logger = logging.getLogger(__name__)


def _format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


def register_settings_system_routes(app, db: Database):
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
        except (sqlite3.Error, OSError) as exc:
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
        except sqlite3.Error as exc:
            logger.exception("Не удалось создать новую гоночную сессию")
            return jsonify({"ok": False, "error": str(exc)}), 500

        return jsonify({"ok": True, "race_id": race_id})
