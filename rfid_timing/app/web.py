import logging
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from ..config.config_state import ConfigState
from ..database.database import Database
from ..integrations.event_store import EventStore
from .judge import register_judge
from ..domain.protocol import register_protocol
from .race_engine import RaceEngine
from ..domain.race_service import build_race_state
from .settings import register_settings
from .start_list import register_start_list

logger = logging.getLogger(__name__)
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"

EMPTY_STATE = {
    "feed": [],
    "results": [],
    "categories": [],
    "status": {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0},
    "start_time": None,
    "race_closed": False,
    "category_states": {},
}


def create_app(
    event_store: EventStore,
    reader_ip: str,
    antennas: set[int],
    db: Database = None,
    engine: RaceEngine = None,
    config_state: ConfigState = None,
    reader_mgr=None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(TEMPLATES_DIR),
        static_folder=str(STATIC_DIR),
    )

    @app.route("/")
    def index():
        if config_state:
            display_ip = (
                "ЭМУЛЯТОР"
                if config_state["use_emulator"]
                else config_state["reader_ip"]
            )
            display_ant = ", ".join(str(a) for a in sorted(config_state["antennas"]))
        else:
            display_ip = reader_ip
            display_ant = ", ".join(str(a) for a in sorted(antennas))
        return render_template("web.html", reader_ip=display_ip, antennas=display_ant)

    @app.route("/api/state")
    def api_state():
        if not db or not engine:
            return jsonify(EMPTY_STATE)

        cat_id = request.args.get("category_id", type=int)
        state = build_race_state(db, engine=engine, category_id=cat_id)
        return jsonify(state)

    @app.route("/api/events")
    def api_events():
        return jsonify(
            [
                {
                    "timestamp": e.timestamp_str,
                    "epc": e.epc,
                    "epc_short": e.epc_short,
                    "rssi": e.rssi,
                    "antenna": e.antenna,
                }
                for e in event_store.get_events()
            ]
        )

    register_start_list(app, db, engine)
    register_protocol(app, db, engine)
    register_settings(app, db, config_state, reader_mgr=reader_mgr)
    register_judge(app, db, engine)

    return app
