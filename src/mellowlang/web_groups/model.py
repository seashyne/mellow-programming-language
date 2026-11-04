"""The mellow-web data model: the error every stage raises, and the
page/component tree the parser builds and the emitter walks."""

from __future__ import annotations

from dataclasses import dataclass, field


class MellowWebError(ValueError):
    pass


@dataclass
class WebState:
    name: str
    value: str


@dataclass
class WebNode:
    name: str
    args: list[str] = field(default_factory=list)
    props: dict[str, str] = field(default_factory=dict)
    children: list["WebNode"] = field(default_factory=list)
    text: str | None = None


@dataclass
class WebComponent:
    kind: str
    name: str
    states: list[WebState]
    view: list[WebNode]
