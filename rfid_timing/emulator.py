import time
import random
import threading
from typing import Callable, Optional

from .models import TagEvent
from .processor import TagProcessor


class EmulatorReader:
    def __init__(
        self,
        on_event: Callable[[TagEvent], None],
        epc_list: Optional[list[str]] = None,
        db=None,
        rssi_window_sec: float = 2.0,
        min_lap_time_sec: float = 10.0,
    ):
        self._static_epc_list = epc_list or []
        self._db = db
        self.on_event = on_event
        self._stop_flag = False
        self._thread = None

        self.processor = TagProcessor(
            rssi_window_sec=rssi_window_sec,
            min_lap_time_sec=min_lap_time_sec,
            on_pass=self._on_processor_pass
        )

    def _get_epc_list(self) -> list[str]:
        if self._db:
            epc_map = self._db.get_epc_map()
            if epc_map:
                return list(epc_map.keys())
        return list(self._static_epc_list)

    def _on_processor_pass(self, epc: str, timestamp: float, rssi: float, antenna: int):
        ts_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
        epc_short = f"...{epc[-4:]}" if len(epc) >= 4 else epc

        event = TagEvent(
            timestamp_str=ts_str,
            epc=epc,
            epc_short=epc_short,
            rssi=round(rssi, 1),
            antenna=antenna,
        )
        self.on_event(event)

    def _simulate_pass(self, epc: str):
        num_reads = random.randint(5, 15)
        antenna = random.choice([1, 2, 3, 4])
        base_rssi = random.uniform(-120.0, -30.0)

        for i in range(num_reads):
            if self._stop_flag:
                break
            noise = random.uniform(-5.0, 5.0)
            current_rssi = base_rssi + noise
            self.processor.feed(epc, current_rssi, antenna, timestamp=time.time())
            time.sleep(random.uniform(0.01, 0.05))

    def _run_loop(self):
        print("Эмулятор запущен! Генерируем тестовые проезды...")
        lap = 1

        while not self._stop_flag:
            # обновление список EPC перед каждым кругом
            current_epcs = self._get_epc_list()

            if not current_epcs:
                for _ in range(50):
                    if self._stop_flag:
                        break
                    time.sleep(0.1)
                continue

            print(f"\n--- Симуляция круга {lap} ({len(current_epcs)} меток) ---")

            current_riders = list(current_epcs)
            random.shuffle(current_riders)

            for epc in current_riders:
                if self._stop_flag:
                    break
                self._simulate_pass(epc)
                time.sleep(random.uniform(1.0, 10.0))

            sleep_time = self.processor.min_lap_time_sec + random.uniform(2.0, 5.0)
            print(f"Все проехали. Ждем {sleep_time:.1f} сек до следующего круга...")

            for _ in range(int(sleep_time * 10)):
                if self._stop_flag:
                    break
                time.sleep(0.1)

            lap += 1

    def start(self):
        self.processor.start()
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_flag = True
        self.processor.stop()