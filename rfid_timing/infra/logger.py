import os
import time


class RawLogger:
    def __init__(self, filepath: str = "data/raw_log.csv"):
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        self._filepath = filepath

        write_header = not os.path.exists(filepath) or os.path.getsize(filepath) == 0

        # каждая строка сразу на диск
        self._file = open(filepath, "a", buffering=1, encoding="utf-8")

        if write_header:
            self._file.write("timestamp,epc,rssi,antenna,event_type\n")

    def log_raw(self, timestamp: float, epc: str, rssi: float, antenna: int):
        self._file.write(f"{timestamp:.3f},{epc},{rssi},{antenna},RAW\n")

    def log_pass(self, timestamp: float, epc: str, rssi: float = 0, antenna: int = 0):
        self._file.write(f"{timestamp:.3f},{epc},{rssi},{antenna},PASS\n")

    def log_event(self, event_type: str, epc: str = "", details: str = ""):
        ts = time.time()
        self._file.write(f"{ts:.3f},{epc},,, {event_type}:{details}\n")

    def close(self):
        if self._file and not self._file.closed:
            self._file.close()
