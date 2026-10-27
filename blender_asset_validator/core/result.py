from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class CheckResult:
    severity: Severity
    message: str
    object_name: Optional[str] = None
    fix_hint: Optional[str] = None
    check_name: str = ""
    fix: Optional[Callable[[], Optional[str]]] = None
    select: Optional[Callable[[], None]] = None  # opens the object in Edit Mode with the culprits selected
    waived: Optional[str] = None  # the reason, if the artist accepted this warning (core/waivers.py)

