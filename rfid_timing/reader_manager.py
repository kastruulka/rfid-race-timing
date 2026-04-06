import logging
import threading
from typing import Callable

from .reader import RFIDReader
from .emulator import EmulatorReader
from .settings import ConfigState

logger = logging.getLogger(__name__)


class ReaderManager:
    def __init__(self, config_state: ConfigState, on_event: Callable, db=None):
        self._config = config_state
        self._on_event = on_event
        self._db = db
        self._reader = None
        self._lock = threading.Lock()

    @property
    def reader(self):
        return self._reader

    def start(self):
        with self._lock:
            self._create_reader()
            if self._reader:
                self._reader.start()

    def restart(self):
        with self._lock:
            old_mode = (
                "emulator" if isinstance(self._reader, EmulatorReader) else "reader"
            )

            if self._reader is not None:
                try:
                    self._reader.stop()
                    logger.info("Старый %s остановлен", old_mode)
                except Exception as e:
                    logger.warning("Ошибка остановки: %s", e)
                self._reader = None

            self._create_reader()
            new_mode = (
                "emulator" if isinstance(self._reader, EmulatorReader) else "reader"
            )

            if self._reader:
                self._reader.start()
                logger.info("Новый %s запущен", new_mode)

            return {
                "old_mode": old_mode,
                "new_mode": new_mode,
                "switched": old_mode != new_mode,
            }

    def stop(self):
        with self._lock:
            if self._reader is not None:
                self._reader.stop()
                self._reader = None

    def get_status(self) -> dict:
        with self._lock:
            if self._reader is None:
                return {"running": False, "mode": "none"}
            mode = "emulator" if isinstance(self._reader, EmulatorReader) else "reader"
            return {
                "running": True,
                "mode": mode,
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
                "Создаю RFIDReader %s:%d (TX=%.1f dBm, ант=%s, "
                "RSSI=%.1f сек, мин.круг=%.1f сек)",
                reader_ip,
                reader_port,
                tx_power,
                antennas,
                rssi_window_sec,
                min_lap_time_sec,
            )
            self._reader = RFIDReader(
                ip=reader_ip,
                port=reader_port,
                finish_antennas=set(antennas),
                on_event=self._on_event,
                tx_power=tx_power,
                antennas=antennas,
                rssi_window_sec=rssi_window_sec,
                min_lap_time_sec=min_lap_time_sec,
            )
