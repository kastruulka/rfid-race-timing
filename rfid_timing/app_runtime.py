import logging
import signal
import sys
from dataclasses import dataclass
from typing import Callable

from .config.config import DB_PATH, MAX_EVENTS
from .config.config_state import ConfigState
from .database import Database
from .event_store import EventStore
from .infra.logger import RawLogger
from .infra.reader_manager import ReaderManager
from .race_engine import RaceEngine

logger = logging.getLogger(__name__)


@dataclass
class AppRuntime:
    config_state: ConfigState
    event_store: EventStore
    db: Database
    raw_logger: RawLogger
    engine: RaceEngine
    reader_mgr: ReaderManager


def make_event_handler(event_store: EventStore, engine: RaceEngine) -> Callable:
    def on_new_event(event):
        event_store.add_event(event)
        engine.on_tag_pass(
            epc=event.epc,
            timestamp=event.timestamp,
            rssi=event.rssi if isinstance(event.rssi, (int, float)) else 0,
            antenna=event.antenna if isinstance(event.antenna, int) else 0,
        )

    return on_new_event


def ensure_race_session(db: Database, engine: RaceEngine):
    if db.get_current_race_id() is None:
        db.create_race(label="auto")
        logger.info("Создана новая пустая гоночная сессия")


def build_runtime() -> AppRuntime:
    config_state = ConfigState()
    event_store = EventStore(max_events=MAX_EVENTS)
    db = Database(DB_PATH)
    raw_logger = RawLogger()
    engine = RaceEngine(db=db, raw_logger=raw_logger)

    ensure_race_session(db, engine)

    reader_mgr = ReaderManager(
        config_state=config_state,
        on_event=make_event_handler(event_store, engine),
        db=db,
    )

    return AppRuntime(
        config_state=config_state,
        event_store=event_store,
        db=db,
        raw_logger=raw_logger,
        engine=engine,
        reader_mgr=reader_mgr,
    )


def install_shutdown_handlers(runtime: AppRuntime):
    def shutdown(*_args):
        print("\nОстановка приложения...")
        runtime.reader_mgr.stop()
        runtime.raw_logger.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
