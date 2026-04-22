from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


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
