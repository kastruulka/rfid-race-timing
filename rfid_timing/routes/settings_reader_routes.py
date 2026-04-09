import logging
import socket

from flask import jsonify

from ..config.config_state import ConfigState
from ..http.request_helpers import get_json_body
from ..security.auth import require_admin
from ..security.network import build_allowed_networks, is_ip_allowed

logger = logging.getLogger(__name__)


def register_settings_reader_routes(app, config_state: ConfigState, reader_mgr=None):
    allowed_nets = build_allowed_networks()

    @app.route("/api/settings/reader-status", methods=["GET"])
    def api_settings_reader_status():
        if not reader_mgr:
            return jsonify({"running": False, "mode": "none"})
        return jsonify(reader_mgr.get_status())

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
