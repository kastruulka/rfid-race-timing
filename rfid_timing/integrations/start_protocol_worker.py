import logging
import sqlite3
import threading
import time
from typing import Dict, Optional, Tuple

from ..http import actions
from ..database.database import Database
from ..app.race_engine import RaceEngine

logger = logging.getLogger(__name__)

_worker_lock = threading.Lock()
_workers: Dict[Tuple[int, int], "StartProtocolWorker"] = {}


class StartProtocolWorker:
    def __init__(
        self,
        db: Database,
        engine: RaceEngine,
        poll_interval_sec: float = 0.25,
    ):
        self._db = db
        self._engine = engine
        self._poll_interval_sec = poll_interval_sec
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="start-protocol-worker",
            daemon=True,
        )
        self._started = False
        self._start_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._thread.start()
            self._started = True

    def stop(self) -> None:
        self._stop_event.set()
        if self._started and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def launch(self) -> None:
        self.start()

    def stop_category(self, category_id: int) -> None:
        for entry in self._db.start_protocol_repo.get_start_protocol(category_id):
            if entry.get("status") in {"PLANNED", "STARTING"}:
                self._db.start_protocol_repo.update_start_protocol_entry(
                    int(entry["id"]),
                    planned_time=None,
                    actual_time=None,
                    status="WAITING",
                )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                due_entries = (
                    self._db.start_protocol_repo.claim_due_start_protocol_entries(
                        time.time() * 1000
                    )
                )
                for entry in due_entries:
                    self._start_entry(
                        entry_id=int(entry["id"]),
                        rider_id=int(entry["rider_id"]),
                        planned_time=float(entry["planned_time"]),
                        category_id=int(entry["category_id"]),
                    )
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower():
                    logger.debug(
                        "start protocol worker skipped tick because database is locked"
                    )
                else:
                    logger.exception("start protocol worker tick failed")
            except Exception:
                logger.exception("start protocol worker tick failed")
            self._stop_event.wait(self._poll_interval_sec)

    def _start_entry(
        self,
        entry_id: int,
        rider_id: int,
        planned_time: float,
        category_id: int,
    ) -> None:
        current_entry = next(
            (
                entry
                for entry in self._db.start_protocol_repo.get_start_protocol(
                    category_id
                )
                if int(entry["id"]) == int(entry_id)
            ),
            None,
        )
        if current_entry is None:
            return

        current_status = current_entry.get("status")
        current_planned_time = current_entry.get("planned_time")
        if current_status != "STARTING" or int(current_planned_time or 0) != int(
            planned_time or 0
        ):
            logger.info(
                "protocol worker skipped stale entry category=%s rider=%s entry=%s status=%s planned=%s",
                category_id,
                rider_id,
                entry_id,
                current_status,
                current_planned_time,
            )
            return

        try:
            body, status = actions.action_individual_start(
                self._engine,
                rider_id,
                start_time=planned_time,
            )
            if status == 200:
                self._db.start_protocol_repo.update_start_protocol_entry(
                    entry_id,
                    actual_time=planned_time,
                    status="STARTED",
                )
                return

            logger.warning(
                "protocol start failed for category=%s rider=%s entry=%s: %s",
                category_id,
                rider_id,
                entry_id,
                body.get("error"),
            )
            self._db.start_protocol_repo.update_start_protocol_entry(
                entry_id,
                actual_time=None,
                status="ERROR",
            )
        except Exception:
            logger.exception(
                "protocol worker crashed for category=%s rider=%s entry=%s",
                category_id,
                rider_id,
                entry_id,
            )
            try:
                self._db.start_protocol_repo.update_start_protocol_entry(
                    entry_id,
                    actual_time=None,
                    status="ERROR",
                )
            except Exception:
                logger.exception(
                    "failed to store protocol error state for entry=%s",
                    entry_id,
                )


def get_start_protocol_worker(
    db: Optional[Database],
    engine: Optional[RaceEngine],
    poll_interval_sec: float = 0.25,
) -> Optional[StartProtocolWorker]:
    if db is None or engine is None:
        return None

    key = (id(db), id(engine))
    with _worker_lock:
        worker = _workers.get(key)
        if worker is None:
            worker = StartProtocolWorker(
                db=db,
                engine=engine,
                poll_interval_sec=poll_interval_sec,
            )
            _workers[key] = worker
        worker.start()
        return worker
