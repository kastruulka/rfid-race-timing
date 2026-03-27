import json
import os
import shutil
import time
from flask import render_template, jsonify, request, send_file
from .database import Database


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
        self._data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> dict:
        return dict(self._data)

    def update(self, **kw):
        allowed = set(self.DEFAULTS.keys())
        for k, v in kw.items():
            if k in allowed:
                self._data[k] = v
        self._save()

    def __getitem__(self, key):
        return self._data.get(key, self.DEFAULTS.get(key))


def register_settings(app, db: Database, config_state: ConfigState):

    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/api/settings", methods=["GET"])
    def api_settings_get():
        return jsonify(config_state.get_all())

    @app.route("/api/settings", methods=["PUT"])
    def api_settings_put():
        data = request.get_json(force=True)
        config_state.update(**data)
        return jsonify({"ok": True})

    @app.route("/api/settings/check-reader", methods=["POST"])
    def api_check_reader():
        ip = config_state["reader_ip"]
        port = config_state["reader_port"]
        if config_state["use_emulator"]:
            return jsonify({"ok": True,
                            "message": "Режим эмулятора — ридер не нужен"})
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            s.connect((ip, int(port)))
            s.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False,
                            "error": f"Нет связи с {ip}:{port} — {e}"})

    @app.route("/api/settings/backup", methods=["POST"])
    def api_backup():
        try:
            db_path = db._db_path
            os.makedirs("backups", exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup_name = f"race_{ts}.db"
            backup_path = os.path.join("backups", backup_name)
            shutil.copy2(db_path, backup_path)
            return jsonify({"ok": True, "filename": backup_name})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/api/settings/reset-race", methods=["POST"])
    def api_reset_race():
        try:
            race_id = db.new_race(label="manual_reset")
            return jsonify({"ok": True, "race_id": race_id})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

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
            backups_count = len([f for f in os.listdir("backups")
                                 if f.endswith(".db")])

        riders = db.get_riders()

        return jsonify({
            "db_size": file_size(db._db_path),
            "log_size": file_size("data/raw_log.csv"),
            "backups_count": backups_count,
            "race_id": db.get_current_race_id(),
            "riders_count": len(riders),
        })