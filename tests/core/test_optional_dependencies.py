from __future__ import annotations

import importlib

import pytest

from mellowlang import net_core


def test_websocket_dependency_is_loaded_only_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import_module = importlib.import_module

    def import_without_websockets(name: str, package: str | None = None):
        if name == "websockets":
            raise ModuleNotFoundError(name)
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", import_without_websockets)

    with pytest.raises(RuntimeError, match=r"pip install mellowlang\[net\]"):
        net_core._load_websockets()


def test_default_host_does_not_require_websocket_dependency() -> None:
    from mellowlang.host.runtime import default_host

    assert default_host() is not None
