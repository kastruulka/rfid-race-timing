import sqlite3
import threading
import time
import os
import shutil
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path: str = "data/race.db"):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._db_path = db_path
        self._local = threading.local()
        self._create_tables()

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

    def _create_tables(self):
        self._conn().executescript("""
            CREATE TABLE IF NOT EXISTS category (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                laps        INTEGER NOT NULL DEFAULT 1,
                distance_km REAL    DEFAULT 0
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
                label       TEXT    DEFAULT ''
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

            CREATE INDEX IF NOT EXISTS idx_rider_epc      ON rider(epc);
            CREATE INDEX IF NOT EXISTS idx_result_rider    ON result(rider_id);
            CREATE INDEX IF NOT EXISTS idx_lap_result      ON lap(result_id);
            CREATE INDEX IF NOT EXISTS idx_penalty_result  ON penalty(result_id);
            CREATE INDEX IF NOT EXISTS idx_sp_race         ON start_protocol(race_id);
            CREATE INDEX IF NOT EXISTS idx_catstate_race   ON category_state(race_id);
        """)
        self._commit()
        self._migrate()

    def _migrate(self):
        cols = [row[1] for row in
                self._exec("PRAGMA table_info(result)").fetchall()]

        if "race_id" not in cols:
            self._exec(
                "ALTER TABLE result ADD COLUMN race_id INTEGER"
                " REFERENCES race(id)")
            self._commit()

        if "dnf_reason" not in cols:
            self._exec(
                "ALTER TABLE result ADD COLUMN dnf_reason TEXT DEFAULT ''")
            self._commit()

        if "penalty_time_ms" not in cols:
            self._exec(
                "ALTER TABLE result ADD COLUMN penalty_time_ms"
                " INTEGER DEFAULT 0")
            self._commit()

        if "extra_laps" not in cols:
            self._exec(
                "ALTER TABLE result ADD COLUMN extra_laps"
                " INTEGER DEFAULT 0")
            self._commit()

        self._exec("""
            CREATE TABLE IF NOT EXISTS penalty (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                result_id   INTEGER NOT NULL REFERENCES result(id),
                type        TEXT    NOT NULL,
                value       REAL    DEFAULT 0,
                reason      TEXT    DEFAULT '',
                created_at  REAL    NOT NULL
            )
        """)
        self._commit()

        self._exec(
            "CREATE INDEX IF NOT EXISTS idx_result_race"
            " ON result(race_id)")
        self._exec(
            "CREATE INDEX IF NOT EXISTS idx_penalty_result"
            " ON penalty(result_id)")
        self._commit()

        race_cols = [row[1] for row in
                     self._exec("PRAGMA table_info(race)").fetchall()]
        if "closed_at" not in race_cols:
            self._exec(
                "ALTER TABLE race ADD COLUMN closed_at REAL DEFAULT NULL")
            self._commit()

        self._exec("""
            CREATE TABLE IF NOT EXISTS note (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER REFERENCES race(id),
                rider_id    INTEGER REFERENCES rider(id),
                text        TEXT    NOT NULL,
                created_at  REAL    NOT NULL
            )
        """)
        self._exec(
            "CREATE INDEX IF NOT EXISTS idx_note_race"
            " ON note(race_id)")
        self._commit()

        self._exec("""
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
            )
        """)
        self._exec(
            "CREATE INDEX IF NOT EXISTS idx_sp_race"
            " ON start_protocol(race_id)")
        self._commit()

        self._exec("""
            CREATE TABLE IF NOT EXISTS category_state (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id     INTEGER NOT NULL REFERENCES race(id),
                category_id INTEGER NOT NULL REFERENCES category(id),
                started_at  REAL,
                closed_at   REAL,
                UNIQUE(race_id, category_id)
            )
        """)
        self._exec(
            "CREATE INDEX IF NOT EXISTS idx_catstate_race"
            " ON category_state(race_id)")
        self._commit()


    def create_race(self, label: str = "") -> int:
        cur = self._exec(
            "INSERT INTO race (created_at, label) VALUES (?, ?)",
            (time.time(), label),
        )
        self._commit()
        return cur.lastrowid

    def get_current_race_id(self) -> Optional[int]:
        r = self._exec(
            "SELECT id FROM race ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return r["id"] if r else None

    def new_race(self, label: str = "") -> int:
        return self.create_race(label)

    def close_race(self, race_id: int = None):
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return
        self._exec("UPDATE race SET closed_at=? WHERE id=?",
                    (time.time(), race_id))
        self._commit()

    def is_race_closed(self, race_id: int = None) -> bool:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return False
        r = self._exec("SELECT closed_at FROM race WHERE id=?",
                        (race_id,)).fetchone()
        return r is not None and r["closed_at"] is not None


    def set_category_started(self, category_id: int, started_at: float,
                             race_id: int = None):
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return
        existing = self._exec(
            "SELECT id, started_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id)).fetchone()
        if existing:
            if existing["started_at"] is None:
                self._exec(
                    "UPDATE category_state SET started_at=? WHERE id=?",
                    (started_at, existing["id"]))
        else:
            self._exec(
                "INSERT INTO category_state (race_id, category_id, started_at) VALUES (?,?,?)",
                (race_id, category_id, started_at))
        self._commit()

    def close_category(self, category_id: int, race_id: int = None):
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return
        now = time.time()
        existing = self._exec(
            "SELECT id FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id)).fetchone()
        if existing:
            self._exec(
                "UPDATE category_state SET closed_at=? WHERE id=?",
                (now, existing["id"]))
        else:
            self._exec(
                "INSERT INTO category_state (race_id, category_id, closed_at) VALUES (?,?,?)",
                (race_id, category_id, now))
        self._commit()

    def is_category_closed(self, category_id: int, race_id: int = None) -> bool:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return False
        r = self._exec(
            "SELECT closed_at FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id)).fetchone()
        return r is not None and r["closed_at"] is not None

    def get_category_state(self, category_id: int,
                           race_id: int = None) -> Optional[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return None
        r = self._exec(
            "SELECT * FROM category_state WHERE race_id=? AND category_id=?",
            (race_id, category_id)).fetchone()
        return dict(r) if r else None

    def get_all_category_states(self, race_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return []
        rows = self._exec(
            "SELECT * FROM category_state WHERE race_id=?",
            (race_id,)).fetchall()
        return [dict(r) for r in rows]

    def are_all_categories_closed(self, race_id: int = None) -> bool:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return False
        states = self.get_all_category_states(race_id)
        if not states:
            return False
        for s in states:
            if s["started_at"] is not None and s["closed_at"] is None:
                return False
        return True


    def add_category(self, name: str, laps: int = 1, distance_km: float = 0) -> int:
        cur = self._exec("INSERT INTO category (name, laps, distance_km) VALUES (?,?,?)", (name, laps, distance_km))
        self._commit()
        return cur.lastrowid

    def update_category(self, cid: int, **kw) -> bool:
        ok = {"name", "laps", "distance_km"}
        f = {k: v for k, v in kw.items() if k in ok}
        if not f:
            return False
        sql = ("UPDATE category SET "
               + ",".join(f"{k}=?" for k in f)
               + " WHERE id=?")
        self._exec(sql, (*f.values(), cid))
        self._commit()
        return True

    def delete_category(self, cid: int) -> bool:
        r = self._exec(
            "SELECT COUNT(*) as cnt FROM rider WHERE category_id=?",
            (cid,)).fetchone()
        if r and r["cnt"] > 0:
            return False
        self._exec("DELETE FROM category WHERE id=?", (cid,))
        self._commit()
        return True

    def get_categories(self) -> List[Dict]:
        return [dict(r) for r in self._exec("SELECT * FROM category ORDER BY id").fetchall()]

    def get_category(self, cid: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM category WHERE id=?", (cid,)).fetchone()
        return dict(r) if r else None


    def add_rider(self, number: int, last_name: str, first_name: str = "",
                  birth_year: int = None, city: str = "", club: str = "",
                  model: str = "", category_id: int = None,
                  epc: str = None) -> int:
        cur = self._exec(
            """INSERT INTO rider (number, last_name, first_name, birth_year,
               city, club, model, category_id, epc)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (number, last_name, first_name, birth_year,
             city, club, model, category_id, epc))
        self._commit()
        return cur.lastrowid

    def update_rider(self, rid: int, **kw) -> bool:
        ok = {"number", "last_name", "first_name", "birth_year",
              "city", "club", "model", "category_id", "epc"}
        f = {k: v for k, v in kw.items() if k in ok}
        if not f:
            return False
        sql = ("UPDATE rider SET "
               + ",".join(f"{k}=?" for k in f)
               + " WHERE id=?")
        self._exec(sql, (*f.values(), rid))
        self._commit()
        return True

    def delete_rider(self, rid: int) -> bool:
        try:
            results = self._exec(
                "SELECT id FROM result WHERE rider_id=?", (rid,)
            ).fetchall()
            for r in results:
                self._exec("DELETE FROM lap WHERE result_id=?", (r["id"],))
            self._exec("DELETE FROM result WHERE rider_id=?", (rid,))
            self._exec("DELETE FROM rider WHERE id=?", (rid,))
            self._commit()
            return True
        except Exception:
            self._conn().rollback()
            return False

    def get_rider(self, rid: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def get_riders(self, category_id: int = None) -> List[Dict]:
        if category_id:
            rows = self._exec(
                "SELECT * FROM rider WHERE category_id=? ORDER BY number",
                (category_id,)).fetchall()
        else:
            rows = self._exec(
                "SELECT * FROM rider ORDER BY number").fetchall()
        return [dict(r) for r in rows]

    def get_riders_with_category(self, category_id: int = None) -> List[Dict]:
        if category_id:
            rows = self._exec("""
                SELECT r.*, c.name as category_name
                FROM rider r
                LEFT JOIN category c ON r.category_id = c.id
                WHERE r.category_id = ?
                ORDER BY r.number
            """, (category_id,)).fetchall()
        else:
            rows = self._exec("""
                SELECT r.*, c.name as category_name
                FROM rider r
                LEFT JOIN category c ON r.category_id = c.id
                ORDER BY r.number
            """).fetchall()
        return [dict(r) for r in rows]

    def get_rider_by_epc(self, epc: str) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE epc=?", (epc,)).fetchone()
        return dict(r) if r else None

    def get_rider_by_number(self, number: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM rider WHERE number=?",
                        (number,)).fetchone()
        return dict(r) if r else None

    def get_epc_map(self) -> Dict[str, Dict]:
        rows = self._exec(
            "SELECT * FROM rider WHERE epc IS NOT NULL AND epc != ''"
        ).fetchall()
        return {r["epc"]: dict(r) for r in rows}


    def create_result(self, rider_id: int, category_id: int,
                      start_time: float = None, status: str = "DNS",
                      race_id: int = None) -> int:
        if race_id is None:
            race_id = self.get_current_race_id()
        cur = self._exec(
            """INSERT INTO result
               (rider_id, category_id, race_id, start_time, status)
               VALUES (?,?,?,?,?)""",
            (rider_id, category_id, race_id, start_time, status))
        self._commit()
        return cur.lastrowid

    def get_result_by_rider(self, rider_id: int,
                            race_id: int = None) -> Optional[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return None
        r = self._exec(
            """SELECT * FROM result
               WHERE rider_id=? AND race_id=?
               ORDER BY id DESC LIMIT 1""",
            (rider_id, race_id)).fetchone()
        return dict(r) if r else None

    def get_results_by_category(self, category_id: int,
                                race_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
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
            (category_id, race_id)).fetchall()
        return [dict(r) for r in rows]

    def update_result(self, result_id: int, **kw):
        ok = {"start_time", "finish_time", "status", "place",
              "dnf_reason", "penalty_time_ms", "extra_laps"}
        f = {k: v for k, v in kw.items() if k in ok}
        if not f:
            return
        sql = ("UPDATE result SET "
               + ",".join(f"{k}=?" for k in f)
               + " WHERE id=?")
        self._exec(sql, (*f.values(), result_id))
        self._commit()


    def add_penalty(self, result_id: int, penalty_type: str,
                    value: float = 0, reason: str = "") -> int:
        cur = self._exec(
            """INSERT INTO penalty (result_id, type, value, reason, created_at)
               VALUES (?,?,?,?,?)""",
            (result_id, penalty_type, value, reason, time.time()))
        self._commit()
        return cur.lastrowid

    def get_penalties(self, result_id: int) -> List[Dict]:
        rows = self._exec(
            "SELECT * FROM penalty WHERE result_id=? ORDER BY created_at",
            (result_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_penalties_by_race(self, race_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return []
        rows = self._exec("""
            SELECT p.*, r.rider_id, rd.number as rider_number,
                   rd.last_name, rd.first_name
            FROM penalty p
            JOIN result r ON p.result_id = r.id
            JOIN rider rd ON r.rider_id = rd.id
            WHERE r.race_id = ?
            ORDER BY p.created_at DESC
        """, (race_id,)).fetchall()
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
        self.update_result(result_id,
                           penalty_time_ms=total_time_ms,
                           extra_laps=total_extra_laps)


    def record_lap(self, result_id: int, lap_number: int,
                   timestamp: float, lap_time: float = None,
                   segment: str = '{}', source: str = "RFID") -> int:
        cur = self._exec(
            """INSERT INTO lap
               (result_id, lap_number, timestamp, lap_time, segment, source)
               VALUES (?,?,?,?,?,?)""",
            (result_id, lap_number, timestamp, lap_time, segment, source))
        self._commit()
        return cur.lastrowid

    def get_laps(self, result_id: int) -> List[Dict]:
        rows = self._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number",
            (result_id,)).fetchall()
        return [dict(r) for r in rows]

    def count_laps(self, result_id: int) -> int:
        r = self._exec(
            "SELECT COUNT(*) as cnt FROM lap WHERE result_id=? AND lap_number>0",
            (result_id,)).fetchone()
        return r["cnt"] if r else 0

    def get_last_lap(self, result_id: int) -> Optional[Dict]:
        r = self._exec(
            "SELECT * FROM lap WHERE result_id=? ORDER BY lap_number DESC LIMIT 1",
            (result_id,)).fetchone()
        return dict(r) if r else None

    def update_lap(self, lap_id: int, **kw) -> bool:
        ok = {"timestamp", "lap_time", "source"}
        f = {k: v for k, v in kw.items() if k in ok}
        if not f:
            return False
        sql = ("UPDATE lap SET "
               + ",".join(f"{k}=?" for k in f)
               + " WHERE id=?")
        self._exec(sql, (*f.values(), lap_id))
        self._commit()
        return True

    def delete_lap(self, lap_id: int) -> bool:
        self._exec("DELETE FROM lap WHERE id=?", (lap_id,))
        self._commit()
        return True

    def get_lap_by_id(self, lap_id: int) -> Optional[Dict]:
        r = self._exec("SELECT * FROM lap WHERE id=?",
                        (lap_id,)).fetchone()
        return dict(r) if r else None

    def get_flat_results(self) -> List[Dict]:
        rows = self._exec("""
            SELECT r.rider_id as user_id, r.category_id, rd.number,
                   rd.club, rd.city, rd.model, r.start_time
            FROM result r JOIN rider rd ON r.rider_id = rd.id
        """).fetchall()
        return [dict(r) for r in rows]

    def get_flat_laps(self) -> List[Dict]:
        rows = self._exec("""
            SELECT r.rider_id as user_id, r.category_id,
                   l.lap_number as lap, l.timestamp as time, l.segment
            FROM lap l JOIN result r ON l.result_id = r.id
        """).fetchall()
        return [dict(r) for r in rows]


    def get_feed_history(self, limit: int = 50,
                         race_id: int = None,
                         category_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return []

        if category_id:
            rows = self._exec("""
                SELECT
                    l.id as lap_id,
                    l.lap_number,
                    l.lap_time,
                    l.timestamp,
                    rd.number as rider_number,
                    rd.last_name,
                    rd.first_name,
                    c.laps as laps_required,
                    r.status
                FROM lap l
                JOIN result r ON l.result_id = r.id
                JOIN rider rd ON r.rider_id = rd.id
                LEFT JOIN category c ON r.category_id = c.id
                WHERE r.race_id = ? AND r.category_id = ?
                ORDER BY l.timestamp DESC
                LIMIT ?
            """, (race_id, category_id, limit)).fetchall()
        else:
            rows = self._exec("""
                SELECT
                    l.id as lap_id,
                    l.lap_number,
                    l.lap_time,
                    l.timestamp,
                    rd.number as rider_number,
                    rd.last_name,
                    rd.first_name,
                    c.laps as laps_required,
                    r.status
                FROM lap l
                JOIN result r ON l.result_id = r.id
                JOIN rider rd ON r.rider_id = rd.id
                LEFT JOIN category c ON r.category_id = c.id
                WHERE r.race_id = ?
                ORDER BY l.timestamp DESC
                LIMIT ?
            """, (race_id, limit)).fetchall()

        return [dict(r) for r in rows]


    def add_note(self, text: str, rider_id: int = None,
                 race_id: int = None) -> int:
        if race_id is None:
            race_id = self.get_current_race_id()
        cur = self._exec(
            """INSERT INTO note (race_id, rider_id, text, created_at)
               VALUES (?,?,?,?)""",
            (race_id, rider_id, text, time.time()))
        self._commit()
        return cur.lastrowid

    def get_notes(self, race_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return []
        rows = self._exec("""
            SELECT n.*, rd.number as rider_number,
                   rd.last_name, rd.first_name
            FROM note n
            LEFT JOIN rider rd ON n.rider_id = rd.id
            WHERE n.race_id = ?
            ORDER BY n.created_at DESC
        """, (race_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_note(self, note_id: int) -> bool:
        self._exec("DELETE FROM note WHERE id=?", (note_id,))
        self._commit()
        return True


    def save_start_protocol(self, category_id: int,
                            entries: List[Dict],
                            race_id: int = None) -> int:
        if race_id is None:
            race_id = self.get_current_race_id()
        self._exec(
            "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
            (race_id, category_id))
        count = 0
        for e in entries:
            self._exec(
                """INSERT INTO start_protocol
                   (race_id, category_id, rider_id, position,
                    interval_sec, status)
                   VALUES (?,?,?,?,?,?)""",
                (race_id, category_id, e["rider_id"],
                 e["position"], e.get("interval_sec", 30), "WAITING"))
            count += 1
        self._commit()
        return count

    def get_start_protocol(self, category_id: int,
                           race_id: int = None) -> List[Dict]:
        if race_id is None:
            race_id = self.get_current_race_id()
        if race_id is None:
            return []
        rows = self._exec("""
            SELECT sp.*, rd.number as rider_number,
                   rd.last_name, rd.first_name,
                   rd.club, rd.city
            FROM start_protocol sp
            JOIN rider rd ON sp.rider_id = rd.id
            WHERE sp.race_id=? AND sp.category_id=?
            ORDER BY sp.position
        """, (race_id, category_id)).fetchall()
        return [dict(r) for r in rows]

    def update_start_protocol_entry(self, entry_id: int, **kw):
        ok = {"planned_time", "actual_time", "status"}
        f = {k: v for k, v in kw.items() if k in ok}
        if not f:
            return
        sql = ("UPDATE start_protocol SET "
               + ",".join(f"{k}=?" for k in f)
               + " WHERE id=?")
        self._exec(sql, (*f.values(), entry_id))
        self._commit()

    def clear_start_protocol(self, category_id: int,
                             race_id: int = None):
        if race_id is None:
            race_id = self.get_current_race_id()
        self._exec(
            "DELETE FROM start_protocol WHERE race_id=? AND category_id=?",
            (race_id, category_id))
        self._commit()