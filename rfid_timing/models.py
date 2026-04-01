import time
from dataclasses import dataclass
from typing import Union


@dataclass
class TagEvent:
    timestamp_str: str  # "HH:MM:SS"
    epc: str  # полный EPC
    epc_short: str  # усечённый EPC для отображения
    rssi: Union[int, float, str]
    antenna: Union[int, str]


def make_tag_event(epc: str, timestamp: float, rssi: float, antenna: int) -> TagEvent:
    ts_str = time.strftime("%H:%M:%S", time.localtime(timestamp))
    epc_short = f"...{epc[-4:]}" if len(epc) >= 4 else epc
    return TagEvent(
        timestamp_str=ts_str,
        epc=epc,
        epc_short=epc_short,
        rssi=rssi,
        antenna=antenna,
    )
