import logging

from flask import jsonify, render_template

from ..config.config_state import ConfigState
from ..database import Database
from ..security.auth import is_admin_authenticated
from .settings_reader_routes import register_settings_reader_routes
from .settings_system_routes import register_settings_system_routes

logger = logging.getLogger(__name__)


def register_settings_routes(
    app,
    db: Database,
    config_state: ConfigState,
    reader_mgr=None,
):
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
                logger.exception("settings reader status failed")
                data["_reader_status"] = {"running": False, "mode": "error"}
        return jsonify(data)

    register_settings_reader_routes(app, config_state, reader_mgr=reader_mgr)
    register_settings_system_routes(app, db)
