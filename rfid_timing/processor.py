import time
import threading
from typing import Callable, Optional, Dict, List, Tuple


class TagProcessor:
    def __init__(
        self,
        rssi_window_sec: float = 0.5,
        min_lap_time_sec: float = 120.0,
        on_pass: Optional[Callable] = None,
        tick_interval: float = 0.1,
    ):
        self.rssi_window_sec = rssi_window_sec
        self.min_lap_time_sec = min_lap_time_sec
        self.on_pass = on_pass  # callback(epc, timestamp, rssi, antenna)

        self._buffers: Dict[str, List[Tuple[float, float, int]]] = {}
        # epc -> [(timestamp, rssi, antenna), ...]

        self._last_pass: Dict[str, float] = {}
        # epc -> timestamp последнего засчитанного проезда

        self._lock = threading.Lock()

        # фоновый тик для сброса буферов
        self._tick_interval = tick_interval
        self._ticker: Optional[threading.Timer] = None
        self._running = False

    def start(self):
        self._running = True
        self._schedule_tick()

    def stop(self):
        self._running = False
        if self._ticker:
            self._ticker.cancel()

    def _schedule_tick(self):
        if self._running:
            self._ticker = threading.Timer(self._tick_interval, self._tick)
            self._ticker.daemon = True
            self._ticker.start()

    def feed(self, epc: str, rssi: float, antenna: int, timestamp: float = None):
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            buf = self._buffers.setdefault(epc, [])
            buf.append((timestamp, rssi, antenna))

    def _tick(self):
        now = time.time()
        passes = []

        with self._lock:
            for epc, buf in list(self._buffers.items()):
                if not buf:
                    continue
                last_reading_time = buf[-1][0]
                if (now - last_reading_time) >= self.rssi_window_sec:
                    result = self._flush(epc)
                    if result:
                        passes.append(result)

        # вызываем callback вне лока
        for epc, ts, rssi, ant in passes:
            if self.on_pass:
                self.on_pass(epc, ts, rssi, ant)

        self._schedule_tick()

    def _flush(self, epc: str):
        buf = self._buffers.pop(epc, [])
        if not buf:
            return None

        best = max(buf, key=lambda x: x[1])
        best_time, best_rssi, best_ant = best

        # антидребезг
        last = self._last_pass.get(epc)
        if last and (best_time - last) < self.min_lap_time_sec:
            return None

        self._last_pass[epc] = best_time
        return (epc, best_time, best_rssi, best_ant)
