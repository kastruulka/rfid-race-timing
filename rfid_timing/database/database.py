import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from .bootstrap import init_schema
from .sync_state import SyncTraceState
from ..repositories.categories import CategoriesRepository
from ..repositories.category_state import CategoryStateRepository
from ..repositories.feed import FeedRepository
from ..repositories.laps import LapsRepository
from ..repositories.notes import NotesRepository
from ..repositories.penalties import PenaltiesRepository
from ..repositories.race import RaceRepository
from ..repositories.results import ResultsRepository
from ..repositories.riders import RidersRepository
from ..repositories.start_protocol import StartProtocolRepository
from ..repositories.sync_read import SyncReadRepository
from ..repositories.sync_write import SyncWriteRepository
from ..services.runtime.category_reset_service import CategoryResetService

_SAFE_TABLES = frozenset(
    {
        "category",
        "rider",
        "result",
        "lap",
        "penalty",
        "start_protocol",
        "category_state",
        "race",
        "note",
    }
)

_TABLE_FIELDS = {
    "category": {
        "name",
        "laps",
        "distance_km",
        "has_warmup_lap",
        "finish_mode",
        "time_limit_sec",
    },
    "rider": {
        "number",
        "last_name",
        "first_name",
        "birth_year",
        "city",
        "club",
        "model",
        "category_id",
        "epc",
    },
    "result": {
        "start_time",
        "finish_time",
        "status",
        "place",
        "dnf_reason",
        "penalty_time_ms",
        "extra_laps",
    },
    "lap": {"timestamp", "lap_time", "source", "lap_number"},
    "start_protocol": {"planned_time", "actual_time", "status"},
}

_TIMESTAMP_FIELDS = {
    "created_at",
    "closed_at",
    "started_at",
    "start_time",
    "finish_time",
    "timestamp",
    "planned_time",
    "actual_time",
}


class Database:
    """Infra container for DB connection, schema bootstrap, and repository wiring."""

    def __init__(self, db_path: str = "data/race.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._local = threading.local()
        self.sync_state = SyncTraceState()
        self._init_schema()
        self._init_repositories()

    def _init_repositories(self):
        self.race_repo = RaceRepository(self)
        self.category_state_repo = CategoryStateRepository(self)
        self.categories_repo = CategoriesRepository(self)
        self.riders_repo = RidersRepository(self)
        self.notes_repo = NotesRepository(self)
        self.penalties_repo = PenaltiesRepository(self)
        self.results_repo = ResultsRepository(self)
        self.start_protocol_repo = StartProtocolRepository(self)
        self.laps_repo = LapsRepository(self)
        self.feed_repo = FeedRepository(self)
        self.sync_read_repo = SyncReadRepository(self)
        self.sync_write_repo = SyncWriteRepository(self)
        self.category_reset_service = CategoryResetService(self)

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn().execute(sql, params)

    def _commit(self):
        self._conn().commit()

    @contextmanager
    def _transaction(self):
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def _update_fields(self, table: str, row_id: int, allowed: set, **kw) -> bool:
        if table not in _SAFE_TABLES:
            raise ValueError(f"Table {table!r} is not in the safe update whitelist")
        table_allowed = _TABLE_FIELDS.get(table, allowed)
        safe_allowed = allowed & table_allowed
        fields = {
            k: self._normalize_db_value(k, v)
            for k, v in kw.items()
            if k in safe_allowed
        }
        if not fields:
            return False
        set_clause = ",".join(f"{k}=?" for k in fields)
        sql = f"UPDATE {table} SET {set_clause} WHERE id=?"
        self._exec(sql, (*fields.values(), row_id))
        self._commit()
        return True

    def _normalize_db_value(self, field: str, value):
        if value is None:
            return None
        if field in _TIMESTAMP_FIELDS:
            return int(round(float(value)))
        return value

    def _init_schema(self):
        init_schema(self)

    def _resolve_race(self, race_id: int = None) -> Optional[int]:
        return race_id or self.race_repo.get_current_race_id()
