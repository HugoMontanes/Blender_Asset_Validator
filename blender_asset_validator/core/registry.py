from typing import Callable, List

_CHECKS: List[Callable] = []


def register_check(func: Callable) -> Callable:
    _CHECKS.append(func)
    return func


def get_checks() -> List[Callable]:
    return list(_CHECKS)
