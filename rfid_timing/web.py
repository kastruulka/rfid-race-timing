import logging
from flask import Flask, render_template, jsonify, request

from .event_store import EventStore
from .database import Database
from .race_engine import RaceEngine
from .race_service import build_race_state
from .start_list import register_start_list
from .protocol import register_protocol
from .settings import register_settings, ConfigState
from .judge import register_judge
from .request_helpers import get_json_body, safe_400

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

    def _require_engine():
        if not engine:
            return jsonify({"error": "Engine not available"}), 500
        return None

    @app.route("/api/mass-start", methods=["POST"])
    def api_mass_start():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        cat_id = data.get("category_id")
        if not cat_id:
            return jsonify({"error": "Категория не выбрана"}), 400
        try:
            info = engine.mass_start(int(cat_id))
            return jsonify({"ok": True, "info": info})
        except ValueError as e:
            logger.warning("mass_start: %s", e)
            return jsonify({"error": "Невозможно запустить категорию"}), 400
        except Exception as e:
            return safe_400(e, "mass_start")

    @app.route("/api/individual-start", methods=["POST"])
    def api_individual_start():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        try:
            info = engine.individual_start(int(rid))
            return jsonify({"ok": True, "info": info})
        except ValueError as e:
            logger.warning("individual_start: %s", e)
            return jsonify({"error": "Невозможно стартовать участника"}), 400
        except Exception as e:
            return safe_400(e, "individual_start")

    @app.route("/api/manual-lap", methods=["POST"])
    def api_manual_lap():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        result = engine.manual_lap(int(rid))
        if not result:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": True, "result": result})

    @app.route("/api/dnf", methods=["POST"])
    def api_dnf():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dnf(int(rid))
        if not ok:
            return jsonify({"error": "Невозможно — участник не в гонке"}), 400
        return jsonify({"ok": ok})

    @app.route("/api/dsq", methods=["POST"])
    def api_dsq():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err
        rid = data.get("rider_id")
        if not rid:
            return jsonify({"error": "Участник не выбран"}), 400
        ok = engine.set_dsq(int(rid), data.get("reason", ""))
        if not ok:
            return jsonify({"error": "Невозможно"}), 400
        return jsonify({"ok": ok})

    @app.route("/api/action", methods=["POST"])
    def api_action_legacy():
        err = _require_engine()
        if err:
            return err
        data, err = get_json_body()
        if err:
            return err

        _dispatch = {
            "mass_start": lambda: engine.mass_start(data["category_id"]),
            "individual_start": lambda: engine.individual_start(data["rider_id"]),
            "manual_lap": lambda: engine.manual_lap(data["rider_id"]),
            "dnf": lambda: engine.set_dnf(data["rider_id"]),
            "dsq": lambda: engine.set_dsq(data["rider_id"], data.get("reason", "")),
        }

        action = data.get("action", "")
        handler = _dispatch.get(action)
        if not handler:
            return jsonify({"error": "Неизвестное действие"}), 400

        try:
            result = handler()
            return jsonify({"ok": True, "result": result})
        except Exception as e:
            return safe_400(e, f"action:{action}")

    register_start_list(app, db, engine)
    register_protocol(app, db, engine)
    register_settings(app, db, config_state, reader_mgr=reader_mgr)
    register_judge(app, db, engine)

    return app
