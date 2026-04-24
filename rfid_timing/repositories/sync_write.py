from typing import Any


class SyncWriteRepository:
    def __init__(self, db):
        self._db = db

    def save_import_snapshot(
        self,
        *,
        file_hash: str,
        participant_starts: list[dict[str, Any]] | None = None,
        pass_events: list[dict[str, Any]] | None = None,
    ) -> None:
        self._db.sync_state.last_import_hash = file_hash
        self._db.sync_state.participant_starts = list(participant_starts or [])
        self._db.sync_state.pass_events = list(pass_events or [])

    def set_last_import_hash(self, file_hash: str) -> None:
        self._db.sync_state.last_import_hash = file_hash
