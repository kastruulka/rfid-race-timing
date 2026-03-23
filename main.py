import logging
import signal
import sys
import time

from rfid_timing.config import (
    READER_IP, READER_PORT, FINISH_ANTENNAS, MAX_EVENTS,
    WEB_HOST, WEB_PORT, RSSI_WINDOW_SEC, MIN_LAP_TIME_SEC,
    USE_EMULATOR, EMULATOR_MIN_LAP_TIME_SEC, EMULATOR_TAGS,
    TARGET_LAPS, DB_PATH,
)
from rfid_timing.event_store import EventStore
from rfid_timing.reader import RFIDReader
from rfid_timing.emulator import EmulatorReader
from rfid_timing.web import create_app
from rfid_timing.database import Database
from rfid_timing.logger import RawLogger
from rfid_timing.race_engine import RaceEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

event_store = EventStore(max_events=MAX_EVENTS)
reader = None
db = Database(DB_PATH)
raw_logger = RawLogger()
engine = RaceEngine(db=db, raw_logger=raw_logger)


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
    #engine.mass_start(category_id=cat_id)


def on_new_event(event):
    event_store.add_event(event)
    engine.on_tag_pass(
        epc=event.epc,
        timestamp=time.time(),
        rssi=event.rssi if isinstance(event.rssi, (int, float)) else 0,
        antenna=event.antenna if isinstance(event.antenna, int) else 0,
    )


def shutdown(*_args):
    global reader
    print("\nОстановка приложения...")
    if reader is not None:
        reader.stop()
    raw_logger.close()
    sys.exit(0)


def main():
    global reader

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    setup_dummy_data()

    if USE_EMULATOR:
        logging.info("Запуск в режиме ЭМУЛЯТОРА")
        reader = EmulatorReader(
            on_event=on_new_event,
            db=db,
            rssi_window_sec=RSSI_WINDOW_SEC,
            min_lap_time_sec=EMULATOR_MIN_LAP_TIME_SEC,
        )
    else:
        logging.info("Запуск с ридером Impinj")
        reader = RFIDReader(
            ip=READER_IP, port=READER_PORT,
            finish_antennas=FINISH_ANTENNAS,
            on_event=on_new_event,
            rssi_window_sec=RSSI_WINDOW_SEC,
            min_lap_time_sec=MIN_LAP_TIME_SEC,
        )

    reader.start()

    app = create_app(
        event_store=event_store,
        reader_ip=READER_IP if not USE_EMULATOR else "ЭМУЛЯТОР",
        antennas=FINISH_ANTENNAS,
        db=db,
        engine=engine,
    )
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)


if __name__ == "__main__":
    main()