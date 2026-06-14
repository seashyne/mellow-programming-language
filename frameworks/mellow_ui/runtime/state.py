"""Very small state primitive for Mellow UI v1.

This is not a full React hook implementation. It is a useful v1 object API:

    count = use_state(0)
    count.value
    count.set(1)

Future versions can connect State.set() to root re-render scheduling.
"""
from __future__ import annotations

from typing import Any, Callable, List


class State:
    def __init__(self, value: Any):
        self.value = value
        self._listeners: List[Callable[[Any], None]] = []

    def set(self, value: Any) -> Any:
        self.value = value
        for listener in list(self._listeners):
            listener(value)
        return value

    def subscribe(self, listener: Callable[[Any], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe


def use_state(initial: Any) -> State:
    return State(initial)
