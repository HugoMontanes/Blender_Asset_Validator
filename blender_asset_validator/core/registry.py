from typing import Callable

_CHECKS: dict[str, Callable] = {}


def register_check(func: Callable = None, *, roles=("asset", "lod"), whole_set=False):
    """@register_check, or @register_check(roles=...) for a check that also (or
    only) applies to other object roles (core/roles.py). Validation calls a check
    one object at a time (so Esc can stop it); whole_set=True gets them all in one
    call, for a check that compares each object with the others."""
    def add(f: Callable) -> Callable:
        f.roles = frozenset(roles)
        f.whole_set = whole_set
        _CHECKS[f"{f.__module__}.{f.__name__}"] = f
        return f
    return add(func) if func is not None else add


def get_checks() -> list[Callable]:
    return list(_CHECKS.values())
