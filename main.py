import logging
import signal
import sys
import time

from rfid_timing.settings import ConfigState
from rfid_timing.event_store import EventStore
from rfid_timing.reader_manager import ReaderManager
from rfid_timing.web import create_app
from rfid_timing.database import Database
from rfid_timing.logger import RawLogger
from rfid_timing.race_engine import RaceEngine
from rfid_timing.config import (
    MAX_EVENTS, WEB_HOST, WEB_PORT, EMULATOR_TAGS, TARGET_LAPS, DB_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

config_state = ConfigState()
event_store = EventStore(max_events=MAX_EVENTS)
db = Database(DB_PATH)
raw_logger = RawLogger()
engine = RaceEngine(db=db, raw_logger=raw_logger)
reader_mgr = None


def setup_dummy_data():
    race_id = db.new_race(label="auto")
    logging.info("Новая гоночная сессия: race_id=%d", race_id)

    cats = db.get_categories()
    if not cats:
        cat_id = db.add_category(name="М18-29", laps=TARGET_LAPS,
                                 distance_km=5.0)
    else:
        cat_id = cats[0]["id"]

    riders_data = [
        (13, "Иванов",    "Алексей", "Уралхим Ski Factory", "Москва"),
        (14, "Петров",    "Дмитрий", "Динамо", "Санкт-Петербург"),
        (15, "Сидоров",   "Максим",  "ЦСКА", "Казань"),
    ]

    for i, (num, lname, fname, club, city) in enumerate(riders_data):
        epc = EMULATOR_TAGS[i] if i < len(EMULATOR_TAGS) else f"EMU_{num}"
        if not db.get_rider_by_epc(epc):
            db.add_rider(
                number=num, last_name=lname, first_name=fname,
                club=club, city=city, category_id=cat_id, epc=epc,
            )

    engine.reload_epc_map()


def on_new_event(event):
    event_store.add_event(event)
    engine.on_tag_pass(
        epc=event.epc,
        timestamp=time.time(),
        rssi=event.rssi if isinstance(event.rssi, (int, float)) else 0,
        antenna=event.antenna if isinstance(event.antenna, int) else 0,
    )


def shutdown(*_args):
    global reader_mgr
    print("\nОстановка приложения...")
    if reader_mgr is not None:
        reader_mgr.stop()
    raw_logger.close()
    sys.exit(0)


def main():
    global reader_mgr

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    setup_dummy_data()

    reader_mgr = ReaderManager(
        config_state=config_state,
        on_event=on_new_event,
        db=db,
    )
    reader_mgr.start()

    app = create_app(
        event_store=event_store,
        reader_ip=config_state["reader_ip"],
        antennas=set(config_state["antennas"]),
        db=db,
        engine=engine,
        config_state=config_state,
        reader_mgr=reader_mgr,
    )
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)


if __name__ == "__main__":
    main()