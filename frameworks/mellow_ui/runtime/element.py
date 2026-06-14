"""Mellow UI virtual element model.

This is intentionally small and React-like:
- create_element(type, props, children)
- function components
- normalized element trees for tools/renderers
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

ElementType = Union[str, Callable[[Dict[str, Any]], "Element"]]


@dataclass
class Element:
    type: ElementType
    props: Dict[str, Any] = field(default_factory=dict)
    children: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.props is None:
            self.props = {}
        if self.children is None:
            self.children = []


def _flatten_children(children: Any) -> List[Any]:
    if children is None:
        return []
    if isinstance(children, (list, tuple)):
        out: List[Any] = []
        for child in children:
            out.extend(_flatten_children(child))
        return out
    return [children]


def create_element(type_: ElementType, props: Optional[Dict[str, Any]] = None, children: Any = None) -> Element:
    """Create a Mellow UI virtual element.

    Children can be passed either as the third argument or inside props["Children"].
    The output mirrors React-like shape but stays simple for Mellow v1.
    """
    normalized_props = dict(props or {})
    prop_children = normalized_props.pop("Children", None)
    normalized_children = _flatten_children(children if children is not None else prop_children)
    return Element(type_, normalized_props, normalized_children)


def is_element(value: Any) -> bool:
    return isinstance(value, Element)
