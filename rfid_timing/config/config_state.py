import ipaddress
import json
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _validate_ip(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, str):
        return False, "должен быть строкой"
    try:
        addr = ipaddress.IPv4Address(v)
    except (ipaddress.AddressValueError, ValueError):
        return False, f"невалидный IPv4: {v!r}"
    if addr.is_loopback or addr.is_multicast or addr.is_unspecified:
        return False, f"запрещённый адрес: {v}"
    return True, ""


def _validate_port(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, int):
        return False, "должен быть целым числом"
    if not (1 <= v <= 65535):
        return False, f"порт вне диапазона 1-65535: {v}"
    return True, ""


def _validate_tx_power(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, (int, float)):
        return False, "должен быть числом"
    if not (0.0 <= v <= 33.0):
        return False, f"мощность вне диапазона 0-33 dBm: {v}"
    return True, ""


def _validate_antennas(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, list) or not v:
        return False, "должен быть непустым списком"
    if len(v) > 16:
        return False, "слишком много антенн (макс 16)"
    for a in v:
        if not isinstance(a, int) or not (1 <= a <= 16):
            return False, f"номер антенны должен быть 1-16, получено: {a!r}"
    if len(set(v)) != len(v):
        return False, "дублирующиеся номера антенн"
    return True, ""


def _validate_positive_float(lo: float, hi: float, label: str):
    def _inner(v: Any) -> Tuple[bool, str]:
        if not isinstance(v, (int, float)):
            return False, f"{label}: должен быть числом"
        if not (lo <= float(v) <= hi):
            return False, f"{label}: вне диапазона {lo}-{hi}, получено: {v}"
        return True, ""

    return _inner


def _validate_bool(v: Any) -> Tuple[bool, str]:
    if not isinstance(v, bool):
        return False, "должен быть true/false"
    return True, ""


VALIDATORS = {
    "reader_ip": _validate_ip,
    "reader_port": _validate_port,
    "tx_power": _validate_tx_power,
    "antennas": _validate_antennas,
    "rssi_window_sec": _validate_positive_float(0.1, 30.0, "rssi_window_sec"),
    "min_lap_time_sec": _validate_positive_float(1.0, 3600.0, "min_lap_time_sec"),
    "use_emulator": _validate_bool,
    "emulator_min_lap_sec": _validate_positive_float(
        1.0, 600.0, "emulator_min_lap_sec"
    ),
}


class ConfigState:
    DEFAULTS = {
        "reader_ip": "169.254.1.1",
        "reader_port": 5084,
        "tx_power": 30.0,
        "antennas": [1, 2, 3, 4],
        "rssi_window_sec": 0.5,
        "min_lap_time_sec": 120.0,
        "use_emulator": True,
        "emulator_min_lap_sec": 15.0,
    }

    def __init__(self, filepath: str = "data/settings.json"):
        self._filepath = filepath
        self._data: Dict[str, Any] = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(
                "%s повреждён (строка %d, кол %d): %s — используются значения по умолчанию",
                self._filepath,
                e.lineno,
                e.colno,
                e.msg,
            )
            return
        except OSError as e:
            logger.error("Не удалось прочитать %s: %s", self._filepath, e)
            return

        if not isinstance(saved, dict):
            logger.error(
                "%s: ожидался JSON-объект, получен %s — игнорируется",
                self._filepath,
                type(saved).__name__,
            )
            return

        for key, value in saved.items():
            validator = VALIDATORS.get(key)
            if validator is None:
                logger.warning(
                    "%s: неизвестный ключ %r — пропущен", self._filepath, key
                )
                continue
            ok, msg = validator(value)
            if ok:
                self._data[key] = value
            else:
                logger.warning(
                    "%s: ключ %r отклонён (%s) — оставлено значение по умолчанию",
                    self._filepath,
                    key,
                    msg,
                )

    def _save(self):
        os.makedirs(os.path.dirname(self._filepath) or ".", exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> dict:
        return dict(self._data)

    def update(self, **kw) -> List[str]:
        errors = []
        accepted = {}
        for key, value in kw.items():
            validator = VALIDATORS.get(key)
            if validator is None:
                continue
            ok, msg = validator(value)
            if ok:
                accepted[key] = value
            else:
                errors.append(f"{key}: {msg}")
        if accepted:
            self._data.update(accepted)
            self._save()
        return errors

    def __getitem__(self, key):
        return self._data.get(key, self.DEFAULTS.get(key))
