"""Every test gets a fresh, in-memory runtime config (no Mongo). Tests tweak it via the ``rt``
fixture or ``runtime.current()``, which returns the same object for the whole test."""
import pytest

from app import runtime


@pytest.fixture(autouse=True)
def rt(monkeypatch):
    cfg = runtime.RuntimeConfig()
    monkeypatch.setattr(runtime, "current", lambda: cfg)
    return cfg
