from typing import List, Optional
from .result import CheckResult

# None = never validated this session; [] = validated, no findings. The panel
# needs to tell those apart, so don't collapse this back to a bare [] default.
_results: Optional[List[CheckResult]] = None


def set_results(results: List[CheckResult]) -> None:
    global _results
    _results = results


def get_results() -> Optional[List[CheckResult]]:
    return _results


def clear_results() -> None:
    global _results
    _results = None
