# safety/alerts.py

from dataclasses import dataclass
from time import time

@dataclass
class AlertEvent:
    type: str      # CRITICAL_ALERT | INFO
    message: str
    timestamp: float = time()
