import logging
import signal
import sys

from rfid_timing.config import (
    READER_IP,
    READER_PORT,
    FINISH_ANTENNAS,
    MAX_EVENTS,
    WEB_HOST,
    WEB_PORT,
)
from rfid_timing.event_store import EventStore
from rfid_timing.reader import RFIDReader
from rfid_timing.web import create_app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

event_store = EventStore(max_events=MAX_EVENTS)
reader: RFIDReader | None = None


def on_new_event(event):
    event_store.add_event(event)


def shutdown(*_args):
    global reader
    print("Остановка приложения...")
    if reader is not None:
        reader.stop()
    sys.exit(0)


def main():
    global reader

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    reader = RFIDReader(
        ip=READER_IP,
        port=READER_PORT,
        finish_antennas=FINISH_ANTENNAS,
        on_event=on_new_event,
    )
    reader.start()

    app = create_app(event_store, READER_IP, FINISH_ANTENNAS)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)


if __name__ == "__main__":
    main()