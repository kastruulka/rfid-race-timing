import logging
import random
import threading
import time
from typing import Callable, Dict, List, Optional

from ..models import TagEvent, make_tag_event
from ..processor import TagProcessor

logger = logging.getLogger(__name__)

EMULATOR_POLL_INTERVAL_SEC = 0.2
EMULATOR_FIRST_PASS_GRACE_SEC = 3.5


class EmulatorReader:
    def __init__(
        self,
        on_event: Callable[[TagEvent], None],
        epc_list: Optional[list[str]] = None,
        db=None,
        antennas: Optional[List[int]] = None,
        rssi_window_sec: float = 0.5,
        min_lap_time_sec: float = 10.0,
    ):
        self._static_epc_list = epc_list or []
        self._db = db
        self._antennas = list(antennas or [1, 2, 3, 4])
        self.on_event = on_event
        self._stop_flag = False
        self._thread = None
        self._profiles: Dict[str, Dict] = {}

        self.processor = TagProcessor(
            rssi_window_sec=rssi_window_sec,
            min_lap_time_sec=min_lap_time_sec,
            on_pass=self._on_processor_pass,
        )

    def _get_epc_list(self) -> list[str]:
        if self._db:
            epc_map = self._db.get_epc_map()
            if epc_map:
                return list(epc_map.keys())
        return list(self._static_epc_list)

    def _get_active_entries(self) -> List[Dict]:
        if not self._db:
            return []

        race_id = self._db.get_current_race_id()
        if race_id is None:
            return []

        epc_map = self._db.get_epc_map()
        if not epc_map:
            return []

        riders_by_id: Dict[int, Dict] = {}
        for epc, rider in epc_map.items():
            rider_data = dict(rider)
            rider_data["epc"] = epc
            riders_by_id[rider_data["id"]] = rider_data

        categories = {c["id"]: c for c in self._db.get_categories()}
        active_entries: List[Dict] = []

        for category_id, category in categories.items():
            if self._db.is_category_closed(category_id, race_id):
                continue

            for result in self._db.get_results_by_category(category_id, race_id):
                if result.get("status") != "RACING" or not result.get("start_time"):
                    continue
                rider = riders_by_id.get(result["rider_id"])
                if not rider or not rider.get("epc"):
                    continue
                active_entries.append(
                    {
                        "epc": rider["epc"],
                        "rider": rider,
                        "result": result,
                        "category": category,
                    }
                )

        return active_entries

    def _on_processor_pass(self, epc: str, timestamp: float, rssi: float, antenna: int):
        self.on_event(make_tag_event(epc, timestamp, round(rssi, 1), antenna))

    def _choose_secondary_antenna(self, primary: int) -> int:
        if len(self._antennas) <= 1:
            return primary
        choices = [ant for ant in self._antennas if ant != primary]
        return random.choice(choices) if choices else primary

    def _create_profile(self, entry: Dict, now: float) -> Dict:
        rider = entry["rider"]
        result = entry["result"]
        category = entry.get("category") or {}

        min_gap = float(self.processor.min_lap_time_sec)
        base_pace = max(min_gap + 2.0, min_gap * random.uniform(1.15, 1.85))
        consistency = random.uniform(0.035, 0.10)
        fatigue_per_lap = random.uniform(0.08, 0.45)
        primary_antenna = random.choice(self._antennas)
        start_time_sec = float(result["start_time"]) / 1000.0
        has_warmup = bool(category.get("has_warmup_lap", 1))
        first_factor = (
            random.uniform(0.72, 0.90) if has_warmup else random.uniform(0.95, 1.08)
        )
        pack_offset = random.uniform(0.4, 3.2)
        first_pass_at = max(
            now + 0.3,
            start_time_sec
            + max(
                EMULATOR_FIRST_PASS_GRACE_SEC, base_pace * first_factor + pack_offset
            ),
        )

        return {
            "result_id": result["id"],
            "start_time_sec": start_time_sec,
            "rider_number": rider.get("number"),
            "category_id": category.get("id"),
            "base_pace_sec": base_pace,
            "consistency": consistency,
            "fatigue_per_lap_sec": fatigue_per_lap,
            "primary_antenna": primary_antenna,
            "peak_rssi": random.uniform(-58.0, -36.0),
            "dropout_rate": random.uniform(0.015, 0.06),
            "shadow_read_rate": random.uniform(0.18, 0.40),
            "reads_per_pass": random.randint(7, 16),
            "passes_emitted": 0,
            "next_pass_at": first_pass_at,
        }

    def _sync_profiles(self, active_entries: List[Dict], now: float):
        active_epcs = set()

        for entry in active_entries:
            epc = entry["epc"]
            active_epcs.add(epc)
            result = entry["result"]
            profile = self._profiles.get(epc)

            if (
                profile is None
                or profile.get("result_id") != result["id"]
                or profile.get("start_time_sec") != float(result["start_time"]) / 1000.0
            ):
                self._profiles[epc] = self._create_profile(entry, now)

        stale_epcs = [epc for epc in self._profiles.keys() if epc not in active_epcs]
        for epc in stale_epcs:
            self._profiles.pop(epc, None)

    def _next_lap_interval(self, profile: Dict, is_missed_pass: bool = False) -> float:
        laps_done = profile["passes_emitted"]
        fatigue = min(profile["fatigue_per_lap_sec"] * laps_done, 8.0)
        pace = profile["base_pace_sec"] + fatigue
        variation = random.gauss(0.0, pace * profile["consistency"])
        interval = max(self.processor.min_lap_time_sec + 1.5, pace + variation)
        if is_missed_pass:
            interval += random.uniform(0.8, 3.5)
        return interval

    def _feed_burst(self, epc: str, profile: Dict):
        reads_total = profile["reads_per_pass"]
        burst_duration = random.uniform(0.16, 0.42)
        burst_start = time.time() - burst_duration
        primary = profile["primary_antenna"]

        for idx in range(reads_total):
            if self._stop_flag:
                break
            progress = idx / max(reads_total - 1, 1)
            shape = 1.0 - abs(progress - 0.5) * 2.0
            fade = (1.0 - shape) * random.uniform(7.0, 16.0)
            antenna = primary
            if random.random() < profile["shadow_read_rate"]:
                antenna = self._choose_secondary_antenna(primary)
                fade += random.uniform(2.0, 6.0)
            rssi = profile["peak_rssi"] - fade + random.uniform(-2.0, 2.0)
            ts = burst_start + burst_duration * progress
            self.processor.feed(epc, rssi, antenna, timestamp=ts)

        if random.random() < 0.08:
            shadow_ts = time.time() - random.uniform(0.02, 0.15)
            self.processor.feed(
                epc,
                profile["peak_rssi"] - random.uniform(10.0, 18.0),
                self._choose_secondary_antenna(primary),
                timestamp=shadow_ts,
            )

    def _process_due_pass(self, entry: Dict, profile: Dict):
        epc = entry["epc"]
        rider = entry["rider"]

        if random.random() < profile["dropout_rate"]:
            profile["next_pass_at"] = time.time() + self._next_lap_interval(
                profile, is_missed_pass=True
            )
            logger.debug(
                "Emulator skipped a pass for rider #%s (%s)",
                rider.get("number", "?"),
                epc,
            )
            return

        self._feed_burst(epc, profile)
        profile["passes_emitted"] += 1
        profile["next_pass_at"] = time.time() + self._next_lap_interval(profile)

    def _simulate_pass(self, epc: str):
        num_reads = random.randint(5, 15)
        antenna = random.choice(self._antennas)
        base_rssi = random.uniform(-120.0, -30.0)

        for _ in range(num_reads):
            if self._stop_flag:
                break
            noise = random.uniform(-5.0, 5.0)
            self.processor.feed(epc, base_rssi + noise, antenna, timestamp=time.time())
            time.sleep(random.uniform(0.01, 0.05))

    def _run_realistic_loop(self):
        logger.info("Emulator started in realistic mode")

        while not self._stop_flag:
            now = time.time()
            active_entries = self._get_active_entries()
            self._sync_profiles(active_entries, now)

            if not active_entries:
                time.sleep(EMULATOR_POLL_INTERVAL_SEC)
                continue

            due_entries = [
                entry
                for entry in active_entries
                if self._profiles.get(entry["epc"], {}).get("next_pass_at", now + 3600)
                <= now
            ]

            if due_entries:
                due_entries.sort(
                    key=lambda entry: self._profiles[entry["epc"]]["next_pass_at"]
                )
                for entry in due_entries:
                    if self._stop_flag:
                        break
                    profile = self._profiles.get(entry["epc"])
                    if not profile:
                        continue
                    self._process_due_pass(entry, profile)
                    time.sleep(random.uniform(0.01, 0.06))
                continue

            next_due = min(
                self._profiles[entry["epc"]]["next_pass_at"] for entry in active_entries
            )
            sleep_for = max(0.02, min(EMULATOR_POLL_INTERVAL_SEC, next_due - now))
            time.sleep(sleep_for)

    def _run_loop(self):
        if self._db:
            self._run_realistic_loop()
            return

        logger.info("Emulator started in fallback mode")
        lap = 1

        while not self._stop_flag:
            current_epcs = self._get_epc_list()

            if not current_epcs:
                for _ in range(50):
                    if self._stop_flag:
                        break
                    time.sleep(0.1)
                continue

            logger.info("Simulated lap %s (%s tags)", lap, len(current_epcs))

            current_riders = list(current_epcs)
            random.shuffle(current_riders)

            for epc in current_riders:
                if self._stop_flag:
                    break
                self._simulate_pass(epc)
                time.sleep(random.uniform(1.0, 10.0))

            sleep_time = self.processor.min_lap_time_sec + random.uniform(2.0, 5.0)
            logger.info("Waiting %.1f sec before next simulated lap", sleep_time)

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
