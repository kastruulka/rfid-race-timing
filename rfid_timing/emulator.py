import time
import random
import threading
from typing import Callable

from .models import TagEvent
from .processor import TagProcessor


class EmulatorReader:

    def __init__(
        self,
        epc_list: list[str],
        on_event: Callable[[TagEvent], None],
        rssi_window_sec: float = 2.0,
        min_lap_time_sec: float = 10.0,
    ):
        self.epc_list = epc_list
        self.on_event = on_event
        self._stop_flag = False
        self._thread = None

        self.processor = TagProcessor(
            rssi_window_sec=rssi_window_sec,
            min_lap_time_sec=min_lap_time_sec,
            on_pass=self._on_processor_pass
        )

    def _on_processor_pass(self, epc: str, timestamp: float, rssi: float, antenna: int):
        # работает если подтвержден проезд
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
        # проезд одной метки мимо антенны (пачка считываний)
        num_reads = random.randint(5, 15)  # от 5 до 15 считываний за проезд
        antenna = random.choice([1, 2, 3, 4])    # cлучайная антенна финиша

        # сигнал нарастает, затем падает
        base_rssi = random.uniform(-120.0, -30.0)

        for i in range(num_reads):
            if self._stop_flag:
                break
            
            # случайный шум  RSSI
            noise = random.uniform(-5.0, 5.0)
            current_rssi = base_rssi + noise
            
            # сырое считывание в процессор
            self.processor.feed(epc, current_rssi, antenna, timestamp=time.time())
            
            # пауза между считываниями ридера (10-50 мс)
            time.sleep(random.uniform(0.01, 0.05))

    def _run_loop(self):
        print("Эмулятор запущен! Генерируем тестовые проезды...")
        lap = 1
        
        while not self._stop_flag:
            print(f"\n--- Симуляция круга {lap} ---")
            
            # перемешиваем гонщиков
            current_riders = list(self.epc_list)
            random.shuffle(current_riders)

            for epc in current_riders:
                if self._stop_flag:
                    break
                
                self._simulate_pass(epc)
                
                # пауза между финишами разных гонщиков (от 1 до 10 секунд)
                time.sleep(random.uniform(1.0, 10.0))

            # Ждем время до следующего круга (чуть больше антидребезга)
            sleep_time = self.processor.min_lap_time_sec + random.uniform(2.0, 5.0)
            print(f"Все проехали. Ждем {sleep_time:.1f} сек до следующего круга...")
            
            # спим короткими интервалами, чтобы можно было быстро остановить скрипт
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