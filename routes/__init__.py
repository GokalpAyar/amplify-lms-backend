# routes/__init__.py
# Lazily expose route modules so demo mode can avoid importing JWT/user logic.

from __future__ import annotations

import sys
from importlib import import_module
from types import ModuleType

__all__ = ["assignments", "auth", "responses", "speech", "users"]


def __getattr__(name: str) -> ModuleType:
    if name in __all__:
        module = import_module(f"{__name__}.{name}")
        setattr(sys.modules[__name__], name, module)
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")