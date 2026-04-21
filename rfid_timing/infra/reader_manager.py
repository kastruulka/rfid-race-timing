import logging
import threading
import time
from importlib import import_module
from typing import Callable

from .emulator import EmulatorReader
from ..config.config_state import ConfigState

logger = logging.getLogger(__name__)


class ReaderManager:
    def __init__(self, config_state: ConfigState, on_event: Callable, db=None):
        self._config = config_state
        self._on_event = on_event
        self._db = db
        self._reader = None
        self._lock = threading.Lock()
        self._status = "stopped"
        self._last_error = ""

    @property
    def reader(self):
        return self._reader

    def _set_manager_status(self, status: str, last_error: str = "") -> None:
        self._status = status
        self._last_error = last_error

    def _mode_for_reader(self, reader) -> str:
        if reader is None:
            return "none"
        return "emulator" if isinstance(reader, EmulatorReader) else "reader"

    def _reader_runtime_status(self, reader) -> dict:
        if reader is None:
            return {"status": self._status, "last_error": self._last_error}
        getter = getattr(reader, "get_runtime_status", None)
        if callable(getter):
            runtime = getter()
            return {
                "status": runtime.get("status", self._status),
                "last_error": runtime.get("last_error", self._last_error),
            }
        return {"status": self._status, "last_error": self._last_error}

    def start(self, reason: str = "manual_start"):
        with self._lock:
            if self._reader is not None:
                return
            self._set_manager_status("starting")
            try:
                self._create_reader()
                if self._reader:
                    logger.info(
                        "Starting %s (reason=%s)",
                        self._mode_for_reader(self._reader),
                        reason,
                    )
                    self._reader.start()
                    runtime = self._reader_runtime_status(self._reader)
                    self._set_manager_status(
                        runtime["status"],
                        runtime.get("last_error", ""),
                    )
            except Exception as exc:
                self._set_manager_status("error", str(exc))
                raise

    def restart(self, reason: str = "config_reload"):
        with self._lock:
            old_reader = self._reader
            old_mode = self._mode_for_reader(old_reader)
            logger.info(
                "Restarting reader runtime (reason=%s, old_mode=%s)", reason, old_mode
            )

            if old_reader is not None:
                try:
                    self._set_manager_status("stopping")
                    stop_duration_ms = self._stop_reader(old_reader)
                    logger.info(
                        "Stopped %s during restart (reason=%s, stop_join_ms=%.1f)",
                        old_mode,
                        reason,
                        stop_duration_ms,
                    )
                except Exception as exc:
                    self._set_manager_status("error", str(exc))
                    logger.warning(
                        "Stop failed during restart (reason=%s): %s", reason, exc
                    )
                self._reader = None

            self._set_manager_status("starting")
            try:
                self._create_reader()
                new_mode = self._mode_for_reader(self._reader)
                if self._reader:
                    logger.info(
                        "Starting %s after restart (reason=%s)", new_mode, reason
                    )
                    self._reader.start()
                    runtime = self._reader_runtime_status(self._reader)
                    self._set_manager_status(
                        runtime["status"],
                        runtime.get("last_error", ""),
                    )
                    logger.info(
                        "Started %s after restart (status=%s)",
                        new_mode,
                        runtime["status"],
                    )
                else:
                    new_mode = "none"
                    self._set_manager_status("stopped")
            except Exception as exc:
                self._set_manager_status("error", str(exc))
                raise

            return {
                "old_mode": old_mode,
                "new_mode": new_mode,
                "switched": old_mode != new_mode,
                "status": self._status,
                "last_error": self._last_error,
            }

    def stop(self, reason: str = "manual_stop"):
        with self._lock:
            if self._reader is not None:
                self._set_manager_status("stopping")
                stop_duration_ms = self._stop_reader(self._reader)
                logger.info(
                    "Stopped %s (reason=%s, stop_join_ms=%.1f)",
                    self._mode_for_reader(self._reader),
                    reason,
                    stop_duration_ms,
                )
                runtime = self._reader_runtime_status(self._reader)
                self._reader = None
                if runtime["status"] == "error":
                    self._set_manager_status("error", runtime.get("last_error", ""))
                else:
                    self._set_manager_status("stopped")

    def get_status(self) -> dict:
        with self._lock:
            mode = self._mode_for_reader(self._reader)
            runtime = self._reader_runtime_status(self._reader)
            status = runtime["status"] if self._reader is not None else self._status
            last_error = (
                runtime.get("last_error", "")
                if self._reader is not None
                else self._last_error
            )
            return {
                "running": status in {"starting", "running", "stopping"},
                "mode": mode,
                "status": status,
                "last_error": last_error,
                "use_emulator": self._config["use_emulator"],
                "reader_ip": self._config["reader_ip"],
                "reader_port": self._config["reader_port"],
                "tx_power": self._config["tx_power"],
                "antennas": self._config["antennas"],
                "rssi_window_sec": self._config["rssi_window_sec"],
                "min_lap_time_sec": self._config["min_lap_time_sec"],
                "emulator_min_lap_sec": self._config["emulator_min_lap_sec"],
            }

    def _create_reader(self):
        use_emulator = self._config["use_emulator"]
        reader_ip = self._config["reader_ip"]
        reader_port = self._config["reader_port"]
        tx_power = self._config["tx_power"]
        antennas = self._config["antennas"]
        rssi_window_sec = self._config["rssi_window_sec"]
        min_lap_time_sec = self._config["min_lap_time_sec"]
        emulator_min_lap_sec = self._config["emulator_min_lap_sec"]

        if use_emulator:
            logger.info(
                "Создаю EmulatorReader (RSSI=%.1f сек, мин.круг=%.1f сек)",
                rssi_window_sec,
                emulator_min_lap_sec,
            )
            self._reader = EmulatorReader(
                on_event=self._on_event,
                db=self._db,
                antennas=antennas,
                rssi_window_sec=rssi_window_sec,
                min_lap_time_sec=emulator_min_lap_sec,
            )
        else:
            logger.info(
                "Создаю RFIDReader %s:%d (TX=%.1f dBm, ант=%s, RSSI=%.1f сек, мин.круг=%.1f сек)",
                reader_ip,
                reader_port,
                tx_power,
                antennas,
                rssi_window_sec,
                min_lap_time_sec,
            )
            rfid_reader_class = _load_hardware_reader_class()
            self._reader = rfid_reader_class(
                ip=reader_ip,
                port=reader_port,
                finish_antennas=set(antennas),
                on_event=self._on_event,
                tx_power=tx_power,
                antennas=antennas,
                rssi_window_sec=rssi_window_sec,
                min_lap_time_sec=min_lap_time_sec,
            )

    def _stop_reader(self, reader) -> float:
        started_at = time.perf_counter()
        reader.stop()
        return (time.perf_counter() - started_at) * 1000.0


def _load_hardware_reader_class():
    module = import_module(".reader", package=__package__)
    return module.RFIDReader
