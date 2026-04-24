import sqlite3
import threading
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict

from ..repositories.notes import NotesRepository
from ..repositories.penalties import PenaltiesRepository
from ..repositories.results import ResultsRepository
from ..repositories.start_protocol import StartProtocolRepository
from ..repositories.laps import LapsRepository
from ..repositories.categories import CategoriesRepository
from ..repositories.riders import RidersRepository
from ..repositories.race import RaceRepository
from ..repositories.category_state import CategoryStateRepository
from ..repositories.feed import FeedRepository
from ..services.runtime.category_reset_service import CategoryResetService

logger = logging.getLogger(__name__)

_MOJIBAKE_TEXT_FIELDS = {
    ("result", "dnf_reason"),
    ("penalty", "reason"),
}

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
    def __init__(self, db_path: str = "data/race.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._local = threading.local()
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
        self.category_reset_service = CategoryResetService(self)

    def get_sync_participant_starts(self) -> List[Dict]:
        return list(getattr(self, "_last_sync_participant_starts", []))

    def get_sync_pass_events(self) -> List[Dict]:
        return list(getattr(self, "_last_sync_pass_events", []))

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
        self._conn().executescript("""
            CREATE TABLE IF NOT EXISTS category (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                laps        INTEGER NOT NULL DEFAULT 1,
                distance_km REAL    DEFAULT 0,
                has_warmup_lap INTEGER NOT NULL DEFAULT 1,
                finish_mode TEXT NOT NULL DEFAULT 'laps',
                time_limit_sec INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS rider (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                number      INTEGER NOT NULL UNIQUE,
                last_name   TEXT    NOT NULL,
                first_name  TEXT    NOT NULL DEFAULT '',
                birth_year  INTEGER,
                city        TEXT    DEFAULT '',
                club        TEXT    DEFAULT '',
                model       TEXT    DEFAULT '',
                category_id INTEGER REFERENCES category(id),
                epc         TEXT    UNIQUE
            );

            CREATE TABLE IF NOT EXISTS race (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  REAL    NOT NULL,
                label       TEXT    DEFAULT '',
                closed_at   REAL    DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS result (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rider_id        INTEGER NOT NULL REFERENCES rider(id),
                category_id     INTEGER REFERENCES category(id),
                race_id         INTEGER REFERENCES race(id),
                start_time      REAL,
                finish_time     REAL,
                status          TEXT    NOT NULL DEFAULT 'DNS',
                place           INTEGER,
                dnf_reason      TEXT    DEFAULT '',
                penalty_time_ms INTEGER DEFAULT 0,
                extra_laps      INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS lap (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id   INTEGER NOT NULL REFERENCES result(id),
                lap_number  INTEGER NOT NULL,
                timestamp   REAL    NOT NULL,
                lap_time    REAL,
                segment     TEXT    DEFAULT '{}',
                source      TEXT    NOT NULL DEFAULT 'RFID'
            );

            CREATE TABLE IF NOT EXISTS penalty (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id   INTEGER NOT NULL REFERENCES result(id),
                type        TEXT    NOT NULL,
                value       REAL    DEFAULT 0,
                reason      TEXT    DEFAULT '',
                created_at  REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS start_protocol (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER REFERENCES race(id),
                category_id INTEGER REFERENCES category(id),
                rider_id    INTEGER NOT NULL REFERENCES rider(id),
                position    INTEGER NOT NULL,
                interval_sec REAL   NOT NULL DEFAULT 30,
                planned_time REAL,
                actual_time  REAL,
                status      TEXT    NOT NULL DEFAULT 'WAITING'
            );

            CREATE TABLE IF NOT EXISTS category_state (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER NOT NULL REFERENCES race(id),
                category_id INTEGER NOT NULL REFERENCES category(id),
                started_at  REAL,
                closed_at   REAL,
                UNIQUE(race_id, category_id)
            );

            CREATE TABLE IF NOT EXISTS note (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER REFERENCES race(id),
                rider_id    INTEGER REFERENCES rider(id),
                text        TEXT    NOT NULL,
                created_at  REAL    NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rider_epc      ON rider(epc);
            CREATE INDEX IF NOT EXISTS idx_result_rider    ON result(rider_id);
            CREATE INDEX IF NOT EXISTS idx_result_race     ON result(race_id);
            CREATE INDEX IF NOT EXISTS idx_lap_result      ON lap(result_id);
            CREATE INDEX IF NOT EXISTS idx_penalty_result  ON penalty(result_id);
            CREATE INDEX IF NOT EXISTS idx_sp_race         ON start_protocol(race_id);
            CREATE INDEX IF NOT EXISTS idx_catstate_race   ON category_state(race_id);
            CREATE INDEX IF NOT EXISTS idx_note_race       ON note(race_id);
        """)
        self._commit()
        self._migrate_legacy()

    def _migrate_legacy(self):
        cols = [row[1] for row in self._exec("PRAGMA table_info(result)").fetchall()]
        migrations = {
            "race_id": "ALTER TABLE result ADD COLUMN race_id INTEGER REFERENCES race(id)",
            "dnf_reason": "ALTER TABLE result ADD COLUMN dnf_reason TEXT DEFAULT ''",
            "penalty_time_ms": "ALTER TABLE result ADD COLUMN penalty_time_ms INTEGER DEFAULT 0",
            "extra_laps": "ALTER TABLE result ADD COLUMN extra_laps INTEGER DEFAULT 0",
        }
        for col, sql in migrations.items():
            if col not in cols:
                self._exec(sql)
                self._commit()

        race_cols = [row[1] for row in self._exec("PRAGMA table_info(race)").fetchall()]
        if "closed_at" not in race_cols:
            self._exec("ALTER TABLE race ADD COLUMN closed_at REAL DEFAULT NULL")
            self._commit()

        category_cols = [
            row[1] for row in self._exec("PRAGMA table_info(category)").fetchall()
        ]
        if "has_warmup_lap" not in category_cols:
            self._exec(
                "ALTER TABLE category ADD COLUMN has_warmup_lap INTEGER NOT NULL DEFAULT 1"
            )
            self._commit()
        if "finish_mode" not in category_cols:
            self._exec(
                "ALTER TABLE category ADD COLUMN finish_mode TEXT NOT NULL DEFAULT 'laps'"
            )
            self._commit()
        if "time_limit_sec" not in category_cols:
            self._exec(
                "ALTER TABLE category ADD COLUMN time_limit_sec INTEGER DEFAULT NULL"
            )
            self._commit()

        self._deduplicate_results_by_race_rider()
        self._round_timestamp_columns()
        self._repair_mojibake_text_fields()
        self._exec(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_result_race_rider "
            "ON result(race_id, rider_id)"
        )
        self._commit()

    @staticmethod
    def _repair_mojibake_text(value: str) -> str:
        if not value:
            return value
        if "Р" not in value and "С" not in value:
            return value
        try:
            repaired = value.encode("cp1251").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
        if repaired == value:
            return value
        mojibake_markers_before = value.count("Р") + value.count("С")
        mojibake_markers_after = repaired.count("Р") + repaired.count("С")
        return repaired if mojibake_markers_after < mojibake_markers_before else value

    def _repair_mojibake_text_fields(self):
        for table, field in _MOJIBAKE_TEXT_FIELDS:
            rows = self._exec(
                f"""
                SELECT id, {field}
                FROM {table}
                WHERE {field} IS NOT NULL
                  AND {field} != ''
                """
            ).fetchall()
            for row in rows:
                repaired = self._repair_mojibake_text(row[field])
                if repaired != row[field]:
                    self._exec(
                        f"UPDATE {table} SET {field}=? WHERE id=?",
                        (repaired, row["id"]),
                    )

    def _round_timestamp_columns(self):
        timestamp_columns = {
            "race": ("created_at", "closed_at"),
            "result": ("start_time", "finish_time"),
            "lap": ("timestamp",),
            "penalty": ("created_at",),
            "start_protocol": ("planned_time", "actual_time"),
            "category_state": ("started_at", "closed_at"),
            "note": ("created_at",),
        }
        for table, columns in timestamp_columns.items():
            for column in columns:
                self._exec(
                    f"""
                    UPDATE {table}
                    SET {column} = CAST(ROUND({column}) AS INTEGER)
                    WHERE {column} IS NOT NULL
                      AND {column} != CAST({column} AS INTEGER)
                    """
                )

    def _deduplicate_results_by_race_rider(self):
        duplicate_groups = self._exec(
            """
            SELECT race_id, rider_id, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
            FROM result
            WHERE race_id IS NOT NULL
            GROUP BY race_id, rider_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        if not duplicate_groups:
            return

        logger.warning(
            "Найдены дубли result по (race_id, rider_id): %d групп. Выполняю схлопывание.",
            len(duplicate_groups),
        )

        with self._transaction():
            for group in duplicate_groups:
                ids = [int(part) for part in str(group["ids"]).split(",") if part]
                if len(ids) < 2:
                    continue

                keep_id = max(ids)
                drop_ids = [result_id for result_id in ids if result_id != keep_id]

                keep_row = self._exec(
                    "SELECT * FROM result WHERE id=?",
                    (keep_id,),
                ).fetchone()
                keep_data = dict(keep_row) if keep_row else {}

                for drop_id in drop_ids:
                    drop_row = self._exec(
                        "SELECT * FROM result WHERE id=?",
                        (drop_id,),
                    ).fetchone()
                    if not drop_row:
                        continue
                    drop_data = dict(drop_row)

                    merged_fields = {}
                    for field in (
                        "category_id",
                        "start_time",
                        "finish_time",
                        "place",
                        "dnf_reason",
                    ):
                        if keep_data.get(field) in (None, "") and drop_data.get(
                            field
                        ) not in (
                            None,
                            "",
                        ):
                            merged_fields[field] = drop_data[field]

                    if (keep_data.get("penalty_time_ms") or 0) == 0 and (
                        drop_data.get("penalty_time_ms") or 0
                    ) != 0:
                        merged_fields["penalty_time_ms"] = drop_data["penalty_time_ms"]

                    if (keep_data.get("extra_laps") or 0) == 0 and (
                        drop_data.get("extra_laps") or 0
                    ) != 0:
                        merged_fields["extra_laps"] = drop_data["extra_laps"]

                    if keep_data.get("status") in ("DNS", "", None) and drop_data.get(
                        "status"
                    ) not in ("", None):
                        merged_fields["status"] = drop_data["status"]

                    if merged_fields:
                        set_clause = ", ".join(f"{field}=?" for field in merged_fields)
                        self._exec(
                            f"UPDATE result SET {set_clause} WHERE id=?",
                            (*merged_fields.values(), keep_id),
                        )
                        keep_data.update(merged_fields)

                    self._exec(
                        "UPDATE lap SET result_id=? WHERE result_id=?",
                        (keep_id, drop_id),
                    )
                    self._exec(
                        "UPDATE penalty SET result_id=? WHERE result_id=?",
                        (keep_id, drop_id),
                    )
                    self._exec("DELETE FROM result WHERE id=?", (drop_id,))

    def create_race(self, label: str = "") -> int:
        return self.race_repo.create_race(label=label)

    def get_current_race_id(self) -> Optional[int]:
        return self.race_repo.get_current_race_id()

    def close_race(self, race_id: int = None):
        self.race_repo.close_race(race_id=race_id)

    def close_open_races(self) -> int:
        return self.race_repo.close_open_races()

    def is_race_closed(self, race_id: int = None) -> bool:
        return self.race_repo.is_race_closed(race_id=race_id)

    def get_race_closed_at(self, race_id: int = None) -> Optional[float]:
        return self.race_repo.get_race_closed_at(race_id=race_id)

    def get_earliest_start_time(
        self, race_id: int = None, category_id: int = None
    ) -> Optional[int]:
        return self.race_repo.get_earliest_start_time(
            race_id=race_id,
            category_id=category_id,
        )

    def get_status_counts(
        self, race_id: int = None, category_id: int = None
    ) -> Dict[str, int]:
        return self.results_repo.get_status_counts(
            race_id=race_id,
            category_id=category_id,
        )

    def get_results_with_lap_summary(
        self, category_id: int = None, race_id: int = None
    ) -> List[Dict]:
        return self.results_repo.get_results_with_lap_summary(
            category_id=category_id,
            race_id=race_id,
        )

    def _resolve_race(self, race_id: int = None) -> Optional[int]:
        return race_id or self.get_current_race_id()

    def set_category_started(
        self, category_id: int, started_at: float, race_id: int = None
    ):
        self.category_state_repo.set_category_started(
            category_id=category_id,
            started_at=started_at,
            race_id=race_id,
        )

    def close_category(self, category_id: int, race_id: int = None):
        self.category_state_repo.close_category(
            category_id=category_id, race_id=race_id
        )

    def is_category_closed(self, category_id: int, race_id: int = None) -> bool:
        return self.category_state_repo.is_category_closed(
            category_id=category_id,
            race_id=race_id,
        )

    def get_category_state(
        self, category_id: int, race_id: int = None
    ) -> Optional[Dict]:
        return self.category_state_repo.get_category_state(
            category_id=category_id,
            race_id=race_id,
        )

    def get_all_category_states(self, race_id: int = None) -> List[Dict]:
        return self.category_state_repo.get_all_category_states(race_id=race_id)

    def are_all_categories_closed(self, race_id: int = None) -> bool:
        return self.category_state_repo.are_all_categories_closed(race_id=race_id)

    def reset_category(self, category_id: int, race_id: int = None) -> dict:
        return self.category_reset_service.reset_category(
            category_id=category_id,
            race_id=race_id,
        )

    def add_category(
        self,
        name: str,
        laps: int = 1,
        distance_km: float = 0,
        has_warmup_lap: bool = True,
        finish_mode: str = "laps",
        time_limit_sec: int = None,
    ) -> int:
        return self.categories_repo.add_category(
            name=name,
            laps=laps,
            distance_km=distance_km,
            has_warmup_lap=has_warmup_lap,
            finish_mode=finish_mode,
            time_limit_sec=time_limit_sec,
        )

    def update_category(self, cid: int, **kw) -> bool:
        return self.categories_repo.update_category(cid, **kw)

    def delete_category(self, cid: int) -> bool:
        return self.categories_repo.delete_category(cid)

    def get_categories(self) -> List[Dict]:
        return self.categories_repo.get_categories()

    def get_category(self, cid: int) -> Optional[Dict]:
        return self.categories_repo.get_category(cid)

    def add_rider(
        self,
        number: int,
        last_name: str,
        first_name: str = "",
        birth_year: int = None,
        city: str = "",
        club: str = "",
        model: str = "",
        category_id: int = None,
        epc: str = None,
    ) -> int:
        return self.riders_repo.add_rider(
            number=number,
            last_name=last_name,
            first_name=first_name,
            birth_year=birth_year,
            city=city,
            club=club,
            model=model,
            category_id=category_id,
            epc=epc,
        )

    def update_rider(self, rid: int, **kw) -> bool:
        return self.riders_repo.update_rider(rid, **kw)

    def delete_rider(self, rid: int) -> bool:
        return self.riders_repo.delete_rider(rid)

    def get_rider(self, rid: int) -> Optional[Dict]:
        return self.riders_repo.get_rider(rid)

    def get_riders(self, category_id: int = None) -> List[Dict]:
        return self.riders_repo.get_riders(category_id=category_id)

    def get_riders_with_category(self, category_id: int = None) -> List[Dict]:
        return self.riders_repo.get_riders_with_category(category_id=category_id)

    def get_rider_by_epc(self, epc: str) -> Optional[Dict]:
        return self.riders_repo.get_rider_by_epc(epc)

    def get_rider_by_number(self, number: int) -> Optional[Dict]:
        return self.riders_repo.get_rider_by_number(number)

    def get_epc_map(self) -> Dict[str, Dict]:
        return self.riders_repo.get_epc_map()

    def create_result(
        self,
        rider_id: int,
        category_id: int,
        start_time: float = None,
        status: str = "DNS",
        race_id: int = None,
    ) -> int:
        return self.results_repo.create_result(
            rider_id=rider_id,
            category_id=category_id,
            start_time=start_time,
            status=status,
            race_id=race_id,
        )

    def get_result_by_rider(self, rider_id: int, race_id: int = None) -> Optional[Dict]:
        return self.results_repo.get_result_by_rider(rider_id=rider_id, race_id=race_id)

    def has_active_unfinished_race(self, rider_id: int, race_id: int = None) -> bool:
        return self.results_repo.has_active_unfinished_race(
            rider_id=rider_id,
            race_id=race_id,
        )

    def get_result_by_id(self, result_id: int) -> Optional[Dict]:
        return self.results_repo.get_result_by_id(result_id)

    def get_results_by_category(
        self, category_id: int, race_id: int = None
    ) -> List[Dict]:
        return self.results_repo.get_results_by_category(
            category_id=category_id,
            race_id=race_id,
        )

    def update_result(self, result_id: int, **kw):
        self.results_repo.update_result(result_id, **kw)

    def get_category_for_result(self, result_id: int) -> Optional[int]:
        return self.results_repo.get_category_for_result(result_id)

    def add_penalty(
        self, result_id: int, penalty_type: str, value: float = 0, reason: str = ""
    ) -> int:
        return self.penalties_repo.add_penalty(
            result_id=result_id, penalty_type=penalty_type, value=value, reason=reason
        )

    def get_penalties(self, result_id: int) -> List[Dict]:
        return self.penalties_repo.get_penalties(result_id)

    def get_penalty_by_id(self, penalty_id: int) -> Optional[Dict]:
        return self.penalties_repo.get_penalty_by_id(penalty_id)

    def get_penalties_by_race(self, race_id: int = None) -> List[Dict]:
        return self.penalties_repo.get_penalties_by_race(race_id=race_id)

    def delete_penalty(self, penalty_id: int) -> bool:
        return self.penalties_repo.delete_penalty(penalty_id)

    def recalc_penalties(self, result_id: int):
        return self.penalties_repo.recalc_penalties(result_id)

    def record_lap(
        self,
        result_id: int,
        lap_number: int,
        timestamp: float,
        lap_time: float = None,
        segment: str = "{}",
        source: str = "RFID",
    ) -> int:
        return self.laps_repo.record_lap(
            result_id=result_id,
            lap_number=lap_number,
            timestamp=timestamp,
            lap_time=lap_time,
            segment=segment,
            source=source,
        )

    def get_laps(self, result_id: int) -> List[Dict]:
        return self.laps_repo.get_laps(result_id)

    def count_laps(self, result_id: int) -> int:
        return self.laps_repo.count_laps(result_id)

    def get_last_lap(self, result_id: int) -> Optional[Dict]:
        return self.laps_repo.get_last_lap(result_id)

    def update_lap(self, lap_id: int, **kw) -> bool:
        return self.laps_repo.update_lap(lap_id, **kw)

    def delete_lap(self, lap_id: int) -> bool:
        return self.laps_repo.delete_lap(lap_id)

    def get_lap_by_id(self, lap_id: int) -> Optional[Dict]:
        return self.laps_repo.get_lap_by_id(lap_id)

    def recalc_lap_timestamps(self, result_id: int):
        self.laps_repo.recalc_lap_timestamps(result_id)

    def renumber_laps(self, result_id: int):
        self.laps_repo.renumber_laps(result_id)

    def get_feed_history(
        self, limit: int = 50, race_id: int = None, category_id: int = None
    ) -> List[Dict]:
        return self.feed_repo.get_feed_history(
            limit=limit,
            race_id=race_id,
            category_id=category_id,
        )

    def add_note(self, text: str, rider_id: int = None, race_id: int = None) -> int:
        return self.notes_repo.add_note(text=text, rider_id=rider_id, race_id=race_id)

    def get_notes(self, race_id: int = None) -> List[Dict]:
        return self.notes_repo.get_notes(race_id=race_id)

    def delete_note(self, note_id: int) -> bool:
        return self.notes_repo.delete_note(note_id)

    def delete_notes_by_category(self, category_id: int, race_id: int = None) -> int:
        return self.notes_repo.delete_notes_by_category(
            category_id=category_id,
            race_id=race_id,
        )

    def save_start_protocol(
        self, category_id: int, entries: List[Dict], race_id: int = None
    ) -> int:
        return self.start_protocol_repo.save_start_protocol(
            category_id=category_id,
            entries=entries,
            race_id=race_id,
        )

    def get_start_protocol(self, category_id: int, race_id: int = None) -> List[Dict]:
        return self.start_protocol_repo.get_start_protocol(
            category_id=category_id,
            race_id=race_id,
        )

    def update_start_protocol_entry(self, entry_id: int, **kw):
        self.start_protocol_repo.update_start_protocol_entry(entry_id, **kw)

    def claim_due_start_protocol_entries(
        self, now_ms: float, limit: int = 20
    ) -> List[Dict]:
        return self.start_protocol_repo.claim_due_start_protocol_entries(
            now_ms=now_ms,
            limit=limit,
        )

    def clear_start_protocol(self, category_id: int, race_id: int = None):
        self.start_protocol_repo.clear_start_protocol(
            category_id=category_id,
            race_id=race_id,
        )
