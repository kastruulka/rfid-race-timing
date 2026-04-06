import ipaddress
import logging
import os
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_NETS = [
    "169.254.0.0/16",
    "192.168.0.0/16",
    "10.0.0.0/8",
    "172.16.0.0/12",
]


def build_allowed_networks() -> List[ipaddress._BaseNetwork]:
    raw = os.environ.get("RFID_ALLOWED_READER_NETS", "")
    items = [part.strip() for part in raw.split(",") if part.strip()]
    cidrs = items or DEFAULT_ALLOWED_NETS
    nets: List[ipaddress._BaseNetwork] = []
    for cidr in cidrs:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            logger.warning(
                "Пропускаю неверную подсеть в RFID_ALLOWED_READER_NETS: %s",
                cidr,
            )
    return nets


def is_ip_allowed(ip_str: str, allowed_nets: List[ipaddress._BaseNetwork]) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in allowed_nets)
