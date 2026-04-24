from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyncTraceState:
    last_import_hash: str | None = None
    participant_starts: list[dict[str, Any]] = field(default_factory=list)
    pass_events: list[dict[str, Any]] = field(default_factory=list)
