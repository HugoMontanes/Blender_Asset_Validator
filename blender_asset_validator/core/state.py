from typing import List
from .result import CheckResult

_results: List[CheckResult] = []


def set_results(results: List[CheckResult]) -> None:
    global _results
    _results = results


def get_results() -> List[CheckResult]:
    return _results


def clear_results() -> None:
    global _results
    _results = []
