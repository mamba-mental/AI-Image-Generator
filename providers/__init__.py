"""Provider registry. registry() -> {name: adapter instance}."""
from .fal import FalProvider

_REGISTRY = None


def registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = {p.name: p for p in (FalProvider(),)}
    return _REGISTRY


def get(name):
    return registry().get(name)
