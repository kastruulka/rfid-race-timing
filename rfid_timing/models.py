from dataclasses import dataclass
from typing import Union


@dataclass
class TagEvent:
    timestamp_str: str  # "HH:MM:SS"
    epc: str  # полный EPC
    epc_short: str  # усечённый EPC для отображения
    rssi: Union[int, float, str]
    antenna: Union[int, str]
