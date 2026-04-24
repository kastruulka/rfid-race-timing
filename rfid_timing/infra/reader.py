import logging
import threading
import time
from typing import TYPE_CHECKING, Callable, Optional

from ..domain.models import TagEvent, make_tag_event
from ..domain.processor import TagProcessor

if TYPE_CHECKING:
    from sllurp.llrp import LLRPReaderClient


def dbm_to_power_index(dbm: float) -> int:
    idx = int((dbm - 10.0) * 4) + 1
    return max(1, min(idx, 91))


class RFIDReader:
    STOP_JOIN_TIMEOUT_SEC = 5.0

    def __init__(
        self,
        ip: str,
        port: int,
        finish_antennas: set[int],
        on_event: Callable[[TagEvent], None],
        on_raw_event: Optional[Callable[[TagEvent], None]] = None,
        tx_power: float = 30.0,
        antennas: list[int] = None,
        rssi_window_sec: float = 0.5,
        min_lap_time_sec: float = 120.0,
    ) -> None:
        self.ip = ip
        self.port = port
        self.finish_antennas = finish_antennas
        self.on_event = on_event
        self.on_raw_event = on_raw_event
        self.tx_power = tx_power
        self.antennas = antennas or [1, 2, 3, 4]

        self._client: Optional["LLRPReaderClient"] = None
        self._thread: Optional[threading.Thread] = None
        self._logger = logging.getLogger(self.__class__.__name__)
        self._status_lock = threading.Lock()
        self._status = "stopped"
        self._last_error = ""

        self.processor = TagProcessor(
            rssi_window_sec=rssi_window_sec,
            min_lap_time_sec=min_lap_time_sec,
            on_pass=self._on_processor_pass,
        )

    def _set_runtime_status(self, status: str, last_error: str = "") -> None:
        with self._status_lock:
            self._status = status
            self._last_error = last_error

    def get_runtime_status(self) -> dict:
        with self._status_lock:
            return {
                "status": self._status,
                "last_error": self._last_error,
            }

    def _on_processor_pass(self, epc: str, timestamp: float, rssi: float, antenna: int):
        event = make_tag_event(epc, timestamp, rssi, antenna)
        self._logger.debug(
            "Processed valid pass: time=%s ant=%s rssi=%s epc=%s",
            event.timestamp_str,
            antenna,
            rssi,
            event.epc_short,
        )
        self.on_event(event)

    def _tag_report_cb(self, reader, tag_reports):
        now = time.time()

        for tag in tag_reports:
            epc = tag.get("EPC") or tag.get("EPC-96") or tag.get("EPCData") or b""
            if isinstance(epc, bytes):
                epc = epc.hex()
            else:
                epc = str(epc)

            ant = tag.get("AntennaID", "N/A")
            rssi_raw = tag.get("PeakRSSI", "N/A")
            try:
                rssi = float(rssi_raw)
            except (ValueError, TypeError):
                rssi = -100.0

            if self.on_raw_event:
                self.on_raw_event(make_tag_event(epc, now, rssi, ant))

            if isinstance(ant, int) and ant not in self.finish_antennas:
                continue

            self.processor.feed(epc, rssi, ant, timestamp=now)

    def _reader_loop(self):
        from sllurp.llrp import LLRPReaderConfig, LLRPReaderClient

        self._set_runtime_status("running")

        config = LLRPReaderConfig()
        config.antennas = list(self.antennas)

        power_idx = dbm_to_power_index(self.tx_power)
        config.tx_power = {ant: power_idx for ant in self.antennas}

        self._logger.info(
            "Конфигурация ридера: TX=%.1f dBm (idx=%d), антенны=%s",
            self.tx_power,
            power_idx,
            self.antennas,
        )

        config.mode_identifier = 1004
        config.session = 2
        config.tag_population = 1
        config.report_every_n_tags = 1
        config.tag_content_selector["EnableAntennaID"] = True
        config.tag_content_selector["EnablePeakRSSI"] = True

        self._client = LLRPReaderClient(self.ip, self.port, config=config)
        self._client.add_tag_report_callback(self._tag_report_cb)

        self._logger.info("Подключение к ридеру %s:%s", self.ip, self.port)
        try:
            self._client.connect()
            self._logger.info("Ридер подключен, ожидание меток...")
            self._client.join(None)
        except Exception as exc:
            self._set_runtime_status("error", str(exc))
            self._logger.exception("Ошибка в потоке ридера")
        finally:
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception as exc:
                    self._logger.debug(
                        "Reader disconnect during cleanup failed: %s", exc
                    )
            if self.get_runtime_status()["status"] != "error":
                self._set_runtime_status("stopped")
            self._logger.info("Поток ридера завершен")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._set_runtime_status("starting")
        self.processor.start()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._set_runtime_status("stopping")
        self.processor.stop()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception as exc:
                self._logger.debug("Reader disconnect during stop failed: %s", exc)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self.STOP_JOIN_TIMEOUT_SEC)
            if thread.is_alive():
                self._set_runtime_status("error", "thread stop timeout")
                self._logger.warning("RFIDReader thread did not stop within timeout")
                return
        self._thread = None
        self._client = None
        self._set_runtime_status("stopped")
