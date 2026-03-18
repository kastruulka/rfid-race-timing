import logging
import signal
import sys
import time

from rfid_timing.config import (
    READER_IP, READER_PORT, FINISH_ANTENNAS, MAX_EVENTS,
    WEB_HOST, WEB_PORT, RSSI_WINDOW_SEC, MIN_LAP_TIME_SEC,
    USE_EMULATOR, EMULATOR_MIN_LAP_TIME_SEC, EMULATOR_TAGS, TARGET_LAPS, 
    DB_PATH
)
from rfid_timing.event_store import EventStore
from rfid_timing.reader import RFIDReader
from rfid_timing.emulator import EmulatorReader
from rfid_timing.web import create_app
from rfid_timing.database import Database
from rfid_timing.logger import RawLogger
from rfid_timing.race_engine import RaceEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

event_store = EventStore(max_events=MAX_EVENTS)
reader = None
db = Database(DB_PATH)
raw_logger = RawLogger()

engine = RaceEngine(db=db, raw_logger=raw_logger)

def setup_dummy_data():
    cats = db.get_categories()
    if not cats:
        cat_id = db.add_category(name="Name", laps=TARGET_LAPS, distance_km=5.0)
    else:
        cat_id = cats[0]['id']

    riders_data = [
        (13, "Иванов", "Уралхим Ski Factory", "Москва", None, EMULATOR_TAGS[0]),
        (14, "Петров", "Динамо", "Санкт-Петербург", None, EMULATOR_TAGS[1]),
        (15, "Сидоров", "ЦСКА", "Казань", None, EMULATOR_TAGS[2]),
    ]

    for num, lname, club, city, model, epc in riders_data:
        if not db.get_rider_by_epc(epc):
            db.add_rider(number=num, last_name=lname, club=club, city=city, model=model, category_id=cat_id, epc=epc)

    engine.reload_epc_map()

    engine.mass_start(category_id=cat_id)

def on_new_event(event):
    event_store.add_event(event)

    ts_sec = time.time() 
    engine.on_tag_pass(epc=event.epc, timestamp=ts_sec, rssi=event.rssi, antenna=event.antenna)

def shutdown(*_args):
    global reader
    print("\nОстановка приложения...")
    if reader is not None:
        reader.stop()
    sys.exit(0)

def main():
    global reader
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    setup_dummy_data()

    if USE_EMULATOR:
        reader = EmulatorReader(
            epc_list=EMULATOR_TAGS, on_event=on_new_event,
            rssi_window_sec=RSSI_WINDOW_SEC, min_lap_time_sec=EMULATOR_MIN_LAP_TIME_SEC,
        )
    else:
        reader = RFIDReader(
            ip=READER_IP, port=READER_PORT, finish_antennas=FINISH_ANTENNAS,
            on_event=on_new_event, rssi_window_sec=RSSI_WINDOW_SEC, min_lap_time_sec=MIN_LAP_TIME_SEC,
        )
        
    reader.start()

    app = create_app(event_store, READER_IP if not USE_EMULATOR else "ЭМУЛЯТОР", FINISH_ANTENNAS)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False)

if __name__ == "__main__":
    main()