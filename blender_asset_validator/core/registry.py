from typing import Callable

_CHECKS: dict[str, Callable] = {}


def register_check(func: Callable = None, *, roles=("asset", "lod")):
    """@register_check, or @register_check(roles=...) for a check that also (or
    only) applies to other object roles (core/roles.py)."""
    def add(f: Callable) -> Callable:
        f.roles = frozenset(roles)
        _CHECKS[f"{f.__module__}.{f.__name__}"] = f
        return f
    return add(func) if func is not None else add


def get_checks() -> list[Callable]:
    return list(_CHECKS.values())
