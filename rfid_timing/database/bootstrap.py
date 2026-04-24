import logging

logger = logging.getLogger(__name__)

_MOJIBAKE_TEXT_FIELDS = {
    ("result", "dnf_reason"),
    ("penalty", "reason"),
}


def init_schema(db) -> None:
    db._conn().executescript("""
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
    db._commit()
    migrate_legacy(db)


def migrate_legacy(db) -> None:
    cols = [row[1] for row in db._exec("PRAGMA table_info(result)").fetchall()]
    migrations = {
        "race_id": "ALTER TABLE result ADD COLUMN race_id INTEGER REFERENCES race(id)",
        "dnf_reason": "ALTER TABLE result ADD COLUMN dnf_reason TEXT DEFAULT ''",
        "penalty_time_ms": "ALTER TABLE result ADD COLUMN penalty_time_ms INTEGER DEFAULT 0",
        "extra_laps": "ALTER TABLE result ADD COLUMN extra_laps INTEGER DEFAULT 0",
    }
    for col, sql in migrations.items():
        if col not in cols:
            db._exec(sql)
            db._commit()

    race_cols = [row[1] for row in db._exec("PRAGMA table_info(race)").fetchall()]
    if "closed_at" not in race_cols:
        db._exec("ALTER TABLE race ADD COLUMN closed_at REAL DEFAULT NULL")
        db._commit()

    category_cols = [
        row[1] for row in db._exec("PRAGMA table_info(category)").fetchall()
    ]
    if "has_warmup_lap" not in category_cols:
        db._exec(
            "ALTER TABLE category ADD COLUMN has_warmup_lap INTEGER NOT NULL DEFAULT 1"
        )
        db._commit()
    if "finish_mode" not in category_cols:
        db._exec(
            "ALTER TABLE category ADD COLUMN finish_mode TEXT NOT NULL DEFAULT 'laps'"
        )
        db._commit()
    if "time_limit_sec" not in category_cols:
        db._exec("ALTER TABLE category ADD COLUMN time_limit_sec INTEGER DEFAULT NULL")
        db._commit()

    deduplicate_results_by_race_rider(db)
    round_timestamp_columns(db)
    repair_mojibake_text_fields(db)
    db._exec(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_result_race_rider "
        "ON result(race_id, rider_id)"
    )
    db._commit()


def repair_mojibake_text(value: str) -> str:
    if not value:
        return value

    suspicious_chars = {
        "\xa0",
        "\u0402",
        "\u0409",
        "\u040e",
        "\u0453",
        "\u0459",
        "\u0491",
        "\u2018",
        "\u201a",
        "\u201c",
        "\u201d",
        "\u2013",
        "\u2014",
        "\u2020",
        "\u2026",
        "\u20ac",
    }

    def mojibake_score(text: str) -> int:
        return sum(text.count(char) for char in suspicious_chars)

    def rebuild_utf8_bytes(text: str) -> bytes:
        rebuilt = bytearray()
        for ch in text:
            for encoding in ("cp1251", "cp1252", "latin1"):
                try:
                    rebuilt.extend(ch.encode(encoding))
                    break
                except UnicodeEncodeError:
                    continue
            else:
                rebuilt.extend(b"?")
        return bytes(rebuilt)

    try:
        repaired = rebuild_utf8_bytes(value).decode("utf-8")
    except UnicodeDecodeError:
        return value
    if repaired == value:
        return value
    score_before = mojibake_score(value)
    score_after = mojibake_score(repaired)
    return repaired if score_after < score_before else value


def repair_mojibake_text_fields(db) -> None:
    for table, field in _MOJIBAKE_TEXT_FIELDS:
        rows = db._exec(
            f"""
            SELECT id, {field}
            FROM {table}
            WHERE {field} IS NOT NULL
              AND {field} != ''
            """
        ).fetchall()
        for row in rows:
            repaired = repair_mojibake_text(row[field])
            if repaired != row[field]:
                db._exec(
                    f"UPDATE {table} SET {field}=? WHERE id=?",
                    (repaired, row["id"]),
                )


def round_timestamp_columns(db) -> None:
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
            db._exec(
                f"""
                UPDATE {table}
                SET {column} = CAST(ROUND({column}) AS INTEGER)
                WHERE {column} IS NOT NULL
                  AND {column} != CAST({column} AS INTEGER)
                """
            )


def deduplicate_results_by_race_rider(db) -> None:
    duplicate_groups = db._exec(
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

    with db._transaction():
        for group in duplicate_groups:
            ids = [int(part) for part in str(group["ids"]).split(",") if part]
            if len(ids) < 2:
                continue

            keep_id = max(ids)
            drop_ids = [result_id for result_id in ids if result_id != keep_id]

            keep_row = db._exec(
                "SELECT * FROM result WHERE id=?",
                (keep_id,),
            ).fetchone()
            keep_data = dict(keep_row) if keep_row else {}

            for drop_id in drop_ids:
                drop_row = db._exec(
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
                    db._exec(
                        f"UPDATE result SET {set_clause} WHERE id=?",
                        (*merged_fields.values(), keep_id),
                    )
                    keep_data.update(merged_fields)

                db._exec(
                    "UPDATE lap SET result_id=? WHERE result_id=?",
                    (keep_id, drop_id),
                )
                db._exec(
                    "UPDATE penalty SET result_id=? WHERE result_id=?",
                    (keep_id, drop_id),
                )
                db._exec("DELETE FROM result WHERE id=?", (drop_id,))
