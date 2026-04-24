import time
from typing import Optional


def fmt_ms(ms: Optional[int]) -> str:
    if ms is None:
        return "--"
    total_sec = abs(ms) / 1000.0
    minutes = int(total_sec // 60)
    seconds = total_sec % 60
    return f"{minutes:02d}:{seconds:04.1f}"


def fmt_gap(ms: Optional[int]) -> str:
    if ms is None or ms == 0:
        return ""
    return "+" + fmt_ms(ms)


def fmt_speed(distance_km: Optional[float], time_ms: Optional[int]) -> str:
    if not distance_km or not time_ms or time_ms <= 0:
        return "--"
    hours = time_ms / 1000.0 / 3600.0
    return f"{distance_km / hours:.1f}"


def fmt_start_time(start_time_ms: Optional[int]) -> str:
    if start_time_ms is None:
        return "--"
    return time.strftime("%H:%M:%S", time.localtime(start_time_ms / 1000.0))


def fmt_start_time_precise(start_time_ms: Optional[int]) -> str:
    if start_time_ms is None:
        return "--"
    base = time.strftime("%H:%M:%S", time.localtime(start_time_ms / 1000.0))
    tenth = int((int(start_time_ms) % 1000) / 100)
    return f"{base}.{tenth}"


def fmt_start_offset(
    start_time_ms: Optional[int], first_start_ms: Optional[int]
) -> str:
    if start_time_ms is None or first_start_ms is None:
        return ""
    diff_ms = start_time_ms - first_start_ms
    if diff_ms <= 0:
        return "00:00"
    total_sec = diff_ms / 1000.0
    return f"+{int(total_sec // 60):02d}:{int(total_sec) % 60:02d}"


def fmt_start_offset_precise(
    start_time_ms: Optional[int], first_start_ms: Optional[int]
) -> str:
    if start_time_ms is None or first_start_ms is None:
        return ""
    diff_ms = int(start_time_ms) - int(first_start_ms)
    if diff_ms <= 0:
        return "00:00.0"
    total_sec = diff_ms / 1000.0
    minutes = int(total_sec // 60)
    seconds = total_sec % 60
    return f"+{minutes:02d}:{seconds:04.1f}"
