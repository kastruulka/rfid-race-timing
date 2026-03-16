import logging
import threading
import time
from typing import Callable, Optional

from sllurp.llrp import LLRPReaderConfig, LLRPReaderClient
from .models import TagEvent
from .processor import TagProcessor


class RFIDReader:
    def __init__(
        self,
            ip: str,
            port: int,
            finish_antennas: set[int],
            on_event: Callable[[TagEvent], None],
    ) -> None:
        self.ip = ip
        self.port = port
        self.finish_antennas = finish_antennas
        self.on_event = on_event

        self._client: Optional[LLRPReaderClient] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False

        self._logger = logging.getLogger(self.__class__.__name__)

        # Инициализация процессора для фильтрации считываний
        self.processor = TagProcessor(
            rssi_window_sec=2.0,
            min_lap_time_sec=120.0,
            on_pass=self._on_processor_pass
        )

    def _on_processor_pass(self, epc: str, timestamp: float, rssi: float, antenna: int):
        ts_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
        epc_short = f"...{epc[-4:]}" if len(epc) >= 4 else epc

        event = TagEvent(
            timestamp_str=ts_str,
            epc=epc,
            epc_short=epc_short,
            rssi=rssi,
            antenna=antenna,
        )

        self._logger.debug(
            "Processed valid pass: time=%s ant=%s rssi=%s epc=%s",
            ts_str, antenna, rssi, epc_short,
        )
        self.on_event(event)

    def _tag_report_cb(self, reader, tag_reports):
        """Сырой коллбек от ридера."""
        now = time.time()

        for tag in tag_reports:
            epc = tag.get("EPC") or tag.get("EPC-96") or tag.get("EPCData") or b""
            if isinstance(epc, bytes):
                epc = epc.hex()
            else:
                epc = str(epc)

            rssi_raw = tag.get("PeakRSSI", "N/A")
            ant = tag.get("AntennaID", "N/A")

            if isinstance(ant, int) and ant not in self.finish_antennas:
                continue

            # числовое значение RSSI для поиска максимума
            try:
                rssi = float(rssi_raw)
            except (ValueError, TypeError):
                rssi = -100.0  # дефолтное низкое значение, если ридер не отдал RSSI

            # сырое считывание в процессор на фильтрацию
            self.processor.feed(epc, rssi, ant, timestamp=now)

    def _reader_loop(self):
        from sllurp.llrp import LLRPReaderConfig, LLRPReaderClient

        config = LLRPReaderConfig()
        config.antennas = [1, 2, 3, 4]
        config.tx_power = {1: 87, 2: 87, 3: 87, 4: 87}
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
        except Exception:
            self._logger.exception("Ошибка в потоке ридера")
        finally:
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            self._logger.info("Поток ридера завершён")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_flag = False
        
        # фоновый тик процессора
        self.processor.start()
        
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag = True
        self.processor.stop()
        
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass