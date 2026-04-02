import sqlite3
import threading
import time
import os
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

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
    "category": {"name", "laps", "distance_km", "has_warmup_lap"},
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


class Database:
    def __init__(self, db_path: str = "data/race.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._local = threading.local()
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path)
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
            raise ValueError(f"Таблица {table!r} не в whitelist")
        table_allowed = _TABLE_FIELDS.get(table, allowed)
        safe_allowed = allowed & table_allowed
        fields = {k: v for k, v in kw.items() if k in safe_allowed}
        if not fields:
            return False
        set_clause = ",".join(f"{k}=?" for k in fields)
        sql = f"UPDATE {table} SET {set_clause} WHERE id=?"
        self._exec(sql, (*fields.values(), row_id))
        self._commit()
        return True

    def _init_schema(self):
        self._conn().executescript("""
            CREATE TABLE IF NOT EXISTS category (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                laps        INTEGER NOT NULL DEFAULT 1,
                distance_km REAL    DEFAULT 0,
                has_warmup_lap INTEGER NOT NULL DEFAULT 1
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

    def create_race(self, label: str = "") -> int:
        cur = self._exec(
            "INSERT INTO race (created_at, label) VALUES (?, ?)",
            (time.time(), label),
        )
        self._commit()
        return cur.lastrowid

    new_race = create_race

    def get_current_race_id(self) -> Optional[int]:
        r = self._exec("SELECT id FROM race ORDER BY id DESC LIMIT 1").fetchone()
        return r["id"] if r else None

    def close_race(self, race_id: int = None):
        race_id = race_id or self.get_current_race_id()
        if race_id is None:
            return
        self._exec("UPDATE race SET closed_at=? WHERE id=?", (time.time(), race_id))
        self._commit()

    def is_race_closed(self, race_id: int = None) -> bool:
        race_id = race_id or self.get_current_race_id()
        if race_id is None:
            return False
        r = self._exec("SELECT closed_at FROM race WHERE id=?", (race_id,)).fetchone()
        return r is not None and r["closed_at"] is not None

    def get_race_closed_at(self, race_id: int = None) -> Optional[float]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return None
        r = self._exec("SELECT closed_at FROM race WHERE id=?", (race_id,)).fetchone()
        return r["closed_at"] if r else None

    def get_earliest_start_time(
        self, race_id: int = None, category_id: int = None
    ) -> Optional[int]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return None
        if category_id:
            r = self._exec(
                "SELECT MIN(start_time) as mn FROM result WHERE race_id=? AND category_id=? AND start_time IS NOT NULL",
                (race_id, category_id),
            ).fetchone()
        else:
            r = self._exec(
                "SELECT MIN(start_time) as mn FROM result WHERE race_id=? AND start_time IS NOT NULL",
                (race_id,),
            ).fetchone()
        return int(r["mn"]) if r and r["mn"] is not None else None

    def get_status_counts(
        self, race_id: int = None, category_id: int = None
    ) -> Dict[str, int]:
        race_id = self._resolve_race(race_id)
        counts = {"RACING": 0, "FINISHED": 0, "DNF": 0, "DSQ": 0, "DNS": 0}
        if race_id is None:
            return counts
        if category_id:
            rows = self._exec(
                "SELECT status, COUNT(*) as cnt FROM result WHERE race_id=? AND category_id=? GROUP BY status",
                (race_id, category_id),
            ).fetchall()
        else:
            rows = self._exec(
                "SELECT status, COUNT(*) as cnt FROM result WHERE race_id=? GROUP BY status",
                (race_id,),
            ).fetchall()
        for r in rows:
            counts[r["status"]] = r["cnt"]
        return counts

    def get_results_with_lap_summary(
        self, category_id: int = None, race_id: int = None
    ) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []

        base = """
            SELECT
                r.id as result_id,
                r.rider_id, r.category_id, r.start_time, r.finish_time,
                r.status, r.place, r.dnf_reason, r.penalty_time_ms, r.extra_laps,
                rd.number, rd.last_name, rd.first_name, rd.club, rd.city, rd.birth_year,
                c.laps as cat_laps, c.name as cat_name,
                COALESCE(ls.laps_done, 0) as laps_done,
                ls.last_lap_time, ls.last_lap_ts
            FROM result r
            JOIN rider rd ON rd.id = r.rider_id
            LEFT JOIN category c ON c.id = r.category_id
            LEFT JOIN (
                SELECT
                    result_id,
                    SUM(CASE WHEN lap_number > 0 THEN 1 ELSE 0 END) as laps_done,
                    MAX(CASE WHEN lap_number = (
                        SELECT MAX(lap_number) FROM lap l2 WHERE l2.result_id = lap.result_id
                    ) THEN lap_time END) as last_lap_time,
                    MAX(timestamp) as last_lap_ts
                FROM lap
                GROUP BY result_id
            ) ls ON ls.result_id = r.id
            WHERE r.race_id = ?
        """
        if category_id:
            rows = self._exec(
                base + " AND r.category_id = ?", (race_id, category_id)
            ).fetchall()
        else:
            rows = self._exec(base, (race_id,)).fetchall()
        return [dict(row) for row in rows]

    def _resolve_race(self, race_id: int = None) -> Optional[int]:
        return race_id or self.get_current_race_id()

    def set_category_started(
        self, category_id: int, started_at: float, race_id: int = None
    ):
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return
        existing = self._exec(
            "SELECT id, started_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        if existing:
            if existing["started_at"] is None:
                self._exec(
                    "UPDATE category_state SET started_at=? WHERE id=?",
                    (started_at, existing["id"]),
                )
        else:
            self._exec(
                "INSERT INTO category_state (race_id, category_id, started_at) VALUES (?,?,?)",
                (race_id, category_id, started_at),
            )
        self._commit()

    def close_category(self, category_id: int, race_id: int = None):
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return
        now = time.time()
        existing = self._exec(
            "SELECT id FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        if existing:
            self._exec(
                "UPDATE category_state SET closed_at=? WHERE id=?",
                (now, existing["id"]),
            )
        else:
            self._exec(
                "INSERT INTO category_state (race_id, category_id, closed_at) VALUES (?,?,?)",
                (race_id, category_id, now),
            )
        self._commit()

    def is_category_closed(self, category_id: int, race_id: int = None) -> bool:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return False
        r = self._exec(
            "SELECT closed_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        return r is not None and r["closed_at"] is not None

    def get_category_state(
        self, category_id: int, race_id: int = None
    ) -> Optional[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return None
        r = self._exec(
            "SELECT * FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        ).fetchone()
        return dict(r) if r else None

    def get_all_category_states(self, race_id: int = None) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._exec(
            "SELECT * FROM category_state WHERE race_id=?", (race_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def are_all_categories_closed(self, race_id: int = None) -> bool:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return False
        states = self.get_all_category_states(race_id)
        if not states:
            return False
        return all(
            s["started_at"] is None or s["closed_at"] is not None for s in states
        )

    def reset_category(self, category_id: int, race_id: int = None) -> dict:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return {"error": "no race"}

        with self._transaction():
            results = self._exec(
                "SELECT id FROM result WHERE category_id=? AND race_id=?",
                (category_id, race_id),
            ).fetchall()
            result_ids = [r["id"] for r in results]

            deleted_laps = 0
            for rid in result_ids:
                c = self._exec(
                    "SELECT COUNT(*) as cnt FROM lap WHERE result_id=?", (rid,)
                ).fetchone()
                deleted_laps += c["cnt"] if c else 0
                self._exec("DELETE FROM lap WHERE result_id=?", (rid,))
                self._exec("DELETE FROM penalty WHERE result_id=?", (rid,))

            if result_ids:
                placeholders = ",".join("?" * len(result_ids))
                self._exec(
                    f"DELETE FROM result WHERE id IN ({placeholders})",
                    tuple(result_ids),
                )

            self._exec(
                "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            )
            self._exec(
                "DELETE FROM category_state WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            )

            race_row = self._exec(
                "SELECT closed_at FROM race WHERE id=?", (race_id,)
            ).fetchone()
            if race_row and race_row["closed_at"] is not None:
                self._exec("UPDATE race SET closed_at=NULL WHERE id=?", (race_id,))

        return {
            "deleted_results": len(result_ids),
            "deleted_laps": deleted_laps,
        }

    def add_category(
        self,
        name: str,
        laps: int = 1,
        distance_km: float = 0,
        has_warmup_lap: bool = True,
    ) -> int:
        cur = self._exec(
            "INSERT INTO category (name, laps, distance_km, has_warmup_lap) VALUES (?,?,?,?)",
            (name, laps, distance_km, 1 if has_warmup_lap else 0),
        )
        self._commit()
        return cur.lastrowid

    def update_category(self, cid: int, **kw) -> bool:
        return self._update_fields(
            "category", cid, {"name", "laps", "distance_km", "has_warmup_lap"}, **kw
        )

    def delete_category(self, cid: int) -> bool:
        r = self._exec(
            "SELECT COUNT(*) as cnt FROM rider WHERE category_id=?", (cid,)
        ).fetchone()
        if r and r["cnt"] > 0:
            return False
        self._exec("DELETE FROM category WHERE id=?", (cid,))
        self._commit()
        return True

    def get_categories(self) -> List[Dict]:
        return [
            dict(r) for r in self._exec("SELECT * FROM category ORDER BY id").fetchall()
        ]

    def get_category(self, cid: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM category WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None

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
        cur = self._exec(
            """INSERT INTO rider (number, last_name, first_name, birth_year,
               city, club, model, category_id, epc)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                number,
                last_name,
                first_name,
                birth_year,
                city,
                club,
                model,
                category_id,
                epc,
            ),
        )
        self._commit()
        return cur.lastrowid

    def update_rider(self, rid: int, **kw) -> bool:
        return self._update_fields(
            "rider",
            rid,
            {
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
            **kw,
        )

    def delete_rider(self, rid: int) -> bool:
        try:
            with self._transaction():
                results = self._exec(
                    "SELECT id FROM result WHERE rider_id=?", (rid,)
                ).fetchall()
                for r in results:
                    self._exec("DELETE FROM lap WHERE result_id=?", (r["id"],))
                    self._exec("DELETE FROM penalty WHERE result_id=?", (r["id"],))
                self._exec("DELETE FROM result WHERE rider_id=?", (rid,))
                self._exec("DELETE FROM start_protocol WHERE rider_id=?", (rid,))
                self._exec("DELETE FROM rider WHERE id=?", (rid,))
            return True
        except Exception:
            logger.exception("Ошибка удаления участника #%d", rid)
            return False

    def get_rider(self, rid: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def get_riders(self, category_id: int = None) -> List[Dict]:
        if category_id:
            rows = self._exec(
                "SELECT * FROM rider WHERE category_id=? ORDER BY number",
                (category_id,),
            ).fetchall()
        else:
            rows = self._exec("SELECT * FROM rider ORDER BY number").fetchall()
        return [dict(r) for r in rows]

    def get_riders_with_category(self, category_id: int = None) -> List[Dict]:
        base = """
            SELECT r.*, c.name as category_name
            FROM rider r
            LEFT JOIN category c ON r.category_id = c.id
        """
        if category_id:
            rows = self._exec(
                base + " WHERE r.category_id = ? ORDER BY r.number", (category_id,)
            ).fetchall()
        else:
            rows = self._exec(base + " ORDER BY r.number").fetchall()
        return [dict(r) for r in rows]

    def get_rider_by_epc(self, epc: str) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE epc=?", (epc,)).fetchone()
        return dict(r) if r else None

    def get_rider_by_number(self, number: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE number=?", (number,)).fetchone()
        return dict(r) if r else None

    def get_epc_map(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT * FROM rider WHERE epc IS NOT NULL AND epc != ''"
        ).fetchall()
        return {r["epc"]: dict(r) for r in rows}

    def create_result(
        self,
        rider_id: int,
        category_id: int,
        start_time: float = None,
        status: str = "DNS",
        race_id: int = None,
    ) -> int:
        race_id = self._resolve_race(race_id)
        cur = self._exec(
            """INSERT INTO result
               (rider_id, category_id, race_id, start_time, status)
               VALUES (?,?,?,?,?)""",
            (rider_id, category_id, race_id, start_time, status),
        )
        self._commit()
        return cur.lastrowid

    def get_result_by_rider(self, rider_id: int, race_id: int = None) -> Optional[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return None
        r = self._exec(
            """SELECT * FROM result
               WHERE rider_id=? AND race_id=?
               ORDER BY id DESC LIMIT 1""",
            (rider_id, race_id),
        ).fetchone()
        return dict(r) if r else None

    def get_result_by_id(self, result_id: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM result WHERE id=?", (result_id,)).fetchone()
        return dict(r) if r else None

    def get_results_by_category(
        self, category_id: int, race_id: int = None
    ) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._exec(
            """SELECT r.*, rd.number, rd.last_name, rd.first_name,
                      rd.club, rd.city, rd.birth_year
               FROM result r
               JOIN rider rd ON rd.id = r.rider_id
               WHERE r.category_id = ? AND r.race_id = ?
               ORDER BY
                 CASE r.status
                   WHEN 'FINISHED' THEN 0
                   WHEN 'RACING'   THEN 1
                   WHEN 'DNS'      THEN 2
                   WHEN 'DNF'      THEN 3
                   WHEN 'DSQ'      THEN 4
                 END,
                 r.finish_time ASC NULLS LAST""",
            (category_id, race_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_result(self, result_id: int, **kw):
        self._update_fields(
            "result",
            result_id,
            {
                "start_time",
                "finish_time",
                "status",
                "place",
                "dnf_reason",
                "penalty_time_ms",
                "extra_laps",
            },
            **kw,
        )

    def get_category_for_result(self, result_id: int) -> Optional[int]:
        r = self._exec(
            "SELECT category_id FROM result WHERE id=?", (result_id,)
        ).fetchone()
        return r["category_id"] if r else None

    def add_penalty(
        self, result_id: int, penalty_type: str, value: float = 0, reason: str = ""
    ) -> int:
        cur = self._exec(
            """INSERT INTO penalty (result_id, type, value, reason, created_at)
               VALUES (?,?,?,?,?)""",
            (result_id, penalty_type, value, reason, time.time()),
        )
        self._commit()
        return cur.lastrowid

    def get_penalties(self, result_id: int) -> List[Dict]:
        rows = self._exec(
            "SELECT * FROM penalty WHERE result_id=? ORDER BY created_at", (result_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_penalty_by_id(self, penalty_id: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM penalty WHERE id=?", (penalty_id,)).fetchone()
        return dict(r) if r else None

    def get_penalties_by_race(self, race_id: int = None) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._exec(
            """
            SELECT p.*, r.rider_id, r.category_id,
                   rd.number as rider_number,
                   rd.last_name, rd.first_name,
                   c.name as category_name
            FROM penalty p
            JOIN result r ON p.result_id = r.id
            JOIN rider rd ON r.rider_id = rd.id
            LEFT JOIN category c ON r.category_id = c.id
            WHERE r.race_id = ?
            ORDER BY p.created_at DESC
        """,
            (race_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_penalty(self, penalty_id: int) -> bool:
        self._exec("DELETE FROM penalty WHERE id=?", (penalty_id,))
        self._commit()
        return True

    def recalc_penalties(self, result_id: int):
        penalties = self.get_penalties(result_id)
        total_time_ms = 0
        total_extra_laps = 0
        for p in penalties:
            if p["type"] == "TIME_PENALTY":
                total_time_ms += int(p["value"] * 1000)
            elif p["type"] == "EXTRA_LAP":
                total_extra_laps += int(p["value"])
        self.update_result(
            result_id, penalty_time_ms=total_time_ms, extra_laps=total_extra_laps
        )

    def record_lap(
        self,
        result_id: int,
        lap_number: int,
        timestamp: float,
        lap_time: float = None,
        segment: str = "{}",
        source: str = "RFID",
    ) -> int:
        cur = self._exec(
            """INSERT INTO lap
               (result_id, lap_number, timestamp, lap_time, segment, source)
               VALUES (?,?,?,?,?,?)""",
            (result_id, lap_number, timestamp, lap_time, segment, source),
        )
        self._commit()
        return cur.lastrowid

    def get_laps(self, result_id: int) -> List[Dict]:
        rows = self._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number", (result_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count_laps(self, result_id: int) -> int:
        r = self._exec(
            "SELECT COUNT(*) as cnt FROM lap WHERE result_id=? AND lap_number>0",
            (result_id,),
        ).fetchone()
        return r["cnt"] if r else 0

    def get_last_lap(self, result_id: int) -> Optional[Dict]:
        r = self._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number DESC LIMIT 1",
            (result_id,),
        ).fetchone()
        return dict(r) if r else None

    def update_lap(self, lap_id: int, **kw) -> bool:
        return self._update_fields(
            "lap", lap_id, {"timestamp", "lap_time", "source"}, **kw
        )

    def delete_lap(self, lap_id: int) -> bool:
        self._exec("DELETE FROM lap WHERE id=?", (lap_id,))
        self._commit()
        return True

    def get_lap_by_id(self, lap_id: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM lap WHERE id=?", (lap_id,)).fetchone()
        return dict(r) if r else None

    def recalc_lap_timestamps(self, result_id: int):
        result = self.get_result_by_id(result_id)
        if not result:
            return
        laps = self.get_laps(result_id)
        current_ts = int(float(result["start_time"]))
        for lap in laps:
            current_ts += int(lap.get("lap_time") or 0)
            self._exec("UPDATE lap SET timestamp=? WHERE id=?", (current_ts, lap["id"]))
        self._commit()
        if result["status"] == "FINISHED" and laps:
            penalty_ms = result.get("penalty_time_ms") or 0
            self.update_result(result_id, finish_time=current_ts + penalty_ms)

    def renumber_laps(self, result_id: int):
        laps = self.get_laps(result_id)
        for i, lap in enumerate(laps):
            new_num = 0 if i == 0 else i
            if lap["lap_number"] != new_num:
                self._exec(
                    "UPDATE lap SET lap_number=? WHERE id=?", (new_num, lap["id"])
                )
        self._commit()
        self.recalc_lap_timestamps(result_id)

    def get_feed_history(
        self, limit: int = 50, race_id: int = None, category_id: int = None
    ) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []

        base = """
            SELECT
                l.id as lap_id, l.lap_number, l.lap_time, l.timestamp,
                rd.number as rider_number, rd.last_name, rd.first_name,
                c.laps as laps_required, r.extra_laps, r.status
            FROM lap l
            JOIN result r ON l.result_id = r.id
            JOIN rider rd ON r.rider_id = rd.id
            LEFT JOIN category c ON r.category_id = c.id
            WHERE r.race_id = ?
        """
        if category_id:
            rows = self._exec(
                base + " AND r.category_id = ? ORDER BY l.timestamp DESC LIMIT ?",
                (race_id, category_id, limit),
            ).fetchall()
        else:
            rows = self._exec(
                base + " ORDER BY l.timestamp DESC LIMIT ?",
                (race_id, limit),
            ).fetchall()

        return [dict(r) for r in rows]

    def add_note(self, text: str, rider_id: int = None, race_id: int = None) -> int:
        race_id = self._resolve_race(race_id)
        cur = self._exec(
            """INSERT INTO note (race_id, rider_id, text, created_at)
               VALUES (?,?,?,?)""",
            (race_id, rider_id, text, time.time()),
        )
        self._commit()
        return cur.lastrowid

    def get_notes(self, race_id: int = None) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._exec(
            """
            SELECT n.*, rd.number as rider_number,
                   rd.last_name, rd.first_name
            FROM note n
            LEFT JOIN rider rd ON n.rider_id = rd.id
            WHERE n.race_id = ?
            ORDER BY n.created_at DESC
        """,
            (race_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, note_id: int) -> bool:
        self._exec("DELETE FROM note WHERE id=?", (note_id,))
        self._commit()
        return True

    def save_start_protocol(
        self, category_id: int, entries: List[Dict], race_id: int = None
    ) -> int:
        race_id = self._resolve_race(race_id)
        with self._transaction():
            self._exec(
                "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
                (race_id, category_id),
            )
            for e in entries:
                self._exec(
                    """INSERT INTO start_protocol
                       (race_id, category_id, rider_id, position, interval_sec, status)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        race_id,
                        category_id,
                        e["rider_id"],
                        e["position"],
                        e.get("interval_sec", 30),
                        "WAITING",
                    ),
                )
        return len(entries)

    def get_start_protocol(self, category_id: int, race_id: int = None) -> List[Dict]:
        race_id = self._resolve_race(race_id)
        if race_id is None:
            return []
        rows = self._exec(
            """
            SELECT sp.*, rd.number as rider_number,
                   rd.last_name, rd.first_name,
                   rd.club, rd.city
            FROM start_protocol sp
            JOIN rider rd ON sp.rider_id = rd.id
            WHERE sp.race_id=? AND sp.category_id=?
            ORDER BY sp.position
        """,
            (race_id, category_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_start_protocol_entry(self, entry_id: int, **kw):
        self._update_fields(
            "start_protocol", entry_id, {"planned_time", "actual_time", "status"}, **kw
        )

    def clear_start_protocol(self, category_id: int, race_id: int = None):
        race_id = self._resolve_race(race_id)
        self._exec(
            "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
            (race_id, category_id),
        )
        self._commit()
