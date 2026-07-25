from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

class Signal(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    WARNING = "warning"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"

class EntryStatus(str, Enum):
    READY = "READY"
    WAIT = "WAIT"
    HIGH_RISK = "HIGH_RISK"
    REJECT = "REJECT"

@dataclass(frozen=True)
class Evidence:
    name: str
    signal: Signal
    source: str
    timestamp: str
    critical: bool = False
    detail: str = ""

@dataclass
class Decision:
    status: EntryStatus
    reasons: List[str] = field(default_factory=list)
    vetoes: List[str] = field(default_factory=list)
    audit: Dict[str, str] = field(default_factory=dict)
