import logging

from rfid_timing.app_runtime import build_runtime, install_shutdown_handlers
from rfid_timing.config.config import WEB_HOST, WEB_PORT
from rfid_timing.web import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    runtime = build_runtime()
    install_shutdown_handlers(runtime)

    runtime.reader_mgr.start()

    app = create_app(
        event_store=runtime.event_store,
        reader_ip=runtime.config_state["reader_ip"],
        antennas=set(runtime.config_state["antennas"]),
        db=runtime.db,
        engine=runtime.engine,
        config_state=runtime.config_state,
        reader_mgr=runtime.reader_mgr,
    )
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)


if __name__ == "__main__":
    main()
