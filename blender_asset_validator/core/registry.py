from typing import Callable

_CHECKS: dict[str, Callable] = {}


def register_check(func: Callable) -> Callable:
    key = f"{func.__module__}.{func.__name__}"
    _CHECKS[key] = func
    return func


def get_checks() -> list[Callable]:
    return list(_CHECKS.values())
