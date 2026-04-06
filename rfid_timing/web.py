import logging
from flask import Flask, render_template, jsonify, request

from .event_store import EventStore
from .database import Database
from .race_engine import RaceEngine
from .race_service import build_race_state
from .start_list import register_start_list
from .protocol import register_protocol
from .config_state import ConfigState
from .settings import register_settings
from .judge import register_judge
from .request_helpers import get_json_body, require_int, make_require_engine, safe_400
from . import actions

logger = logging.getLogger(__name__)

EMPTY_STATE = {
    "feed": [],
    "results": [],
    "categories": [],
    "status": {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0},
    "start_time": None,
    "server_elapsed_ms": None,
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

    app = Flask(__name__)

    require_engine = make_require_engine(engine)

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
        state = build_race_state(db, category_id=cat_id)
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

    @app.route("/api/mass-start", methods=["POST"])
    def api_mass_start():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id, err = require_int(data, "category_id", "Категория не выбрана")
        if err:
            return err
        body, status = actions.action_mass_start(engine, cat_id)
        return jsonify(body), status

    @app.route("/api/individual-start", methods=["POST"])
    def api_individual_start():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_individual_start(engine, rid)
        return jsonify(body), status

    @app.route("/api/manual-lap", methods=["POST"])
    def api_manual_lap():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_manual_lap(engine, rid)
        return jsonify(body), status

    @app.route("/api/dnf", methods=["POST"])
    def api_dnf():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_dnf(engine, rid)
        return jsonify(body), status

    @app.route("/api/dsq", methods=["POST"])
    def api_dsq():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid, err = require_int(data, "rider_id", "Участник не выбран")
        if err:
            return err
        body, status = actions.action_dsq(engine, rid, reason=data.get("reason", ""))
        return jsonify(body), status

    @app.route("/api/action", methods=["POST"])
    def api_action_legacy():
        err = require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err

        action = data.get("action", "")

        _dispatch = {
            "mass_start": lambda: actions.action_mass_start(
                engine, int(data["category_id"])
            ),
            "individual_start": lambda: actions.action_individual_start(
                engine, int(data["rider_id"])
            ),
            "manual_lap": lambda: actions.action_manual_lap(
                engine, int(data["rider_id"])
            ),
            "dnf": lambda: actions.action_dnf(engine, int(data["rider_id"])),
            "dsq": lambda: actions.action_dsq(
                engine, int(data["rider_id"]), reason=data.get("reason", "")
            ),
        }

        handler = _dispatch.get(action)
        if not handler:
            return jsonify({"error": "Неизвестное действие"}), 400

        try:
            body, status = handler()
            return jsonify(body), status
        except Exception as e:
            return safe_400(e, f"action:{action}")

    register_start_list(app, db, engine)
    register_protocol(app, db, engine)
    register_settings(app, db, config_state, reader_mgr=reader_mgr)
    register_judge(app, db, engine)

    return app
