from collections import deque
from typing import Deque, List
from ..domain.models import TagEvent


class EventStore:
    def __init__(self, max_events: int = 500):
        self._events: Deque[TagEvent] = deque(maxlen=max_events)

    def add_event(self, event: TagEvent) -> None:
        # новые события кладём в начало
        self._events.appendleft(event)

    def get_events(self) -> List[TagEvent]:
        return list(self._events)
