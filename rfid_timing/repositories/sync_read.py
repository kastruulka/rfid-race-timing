from typing import Any


class SyncReadRepository:
    def __init__(self, db):
        self._db = db

    def get_participant_starts(self) -> list[dict[str, Any]]:
        return list(self._db.sync_state.participant_starts)

    def get_pass_events(self) -> list[dict[str, Any]]:
        return list(self._db.sync_state.pass_events)

    def get_last_import_hash(self) -> str | None:
        value = self._db.sync_state.last_import_hash
        return str(value) if value is not None else None
