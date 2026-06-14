"""In-memory renderer for Mellow UI v1.

The renderer converts function components + virtual elements into normalized dicts.
This version does not implement Fiber, async scheduling, or Roblox rendering yet.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from .element import Element, create_element, is_element

TEXT_NODE = "Text"


def _normalize_child(child: Any) -> Dict[str, Any]:
    if is_element(child):
        return render_to_tree(child)

    # Text nodes let Mellow UI support children like "Hello".
    return {
        "type": TEXT_NODE,
        "props": {"Value": str(child)},
        "children": [],
    }


def render_to_tree(element: Element) -> Dict[str, Any]:
    if not is_element(element):
        raise TypeError("render_to_tree expected a Mellow UI Element")

    if callable(element.type):
        component_props = dict(element.props)
        if element.children:
            component_props["Children"] = element.children
        rendered = element.type(component_props)
        return render_to_tree(rendered)

    return {
        "type": element.type,
        "props": dict(element.props),
        "children": [_normalize_child(child) for child in element.children],
    }


def render_to_json(element: Element, *, indent: int | None = 2) -> str:
    """Render an element to deterministic JSON for tools and previews."""
    return json.dumps(render_to_tree(element), ensure_ascii=False, indent=indent)


class Root:
    def __init__(self, container_name: str):
        self.container_name = container_name
        self.current_element = None
        self.current_tree = None

    def render(self, element: Element) -> Dict[str, Any]:
        self.current_element = element
        self.current_tree = {
            "container": self.container_name,
            "tree": render_to_tree(element),
        }
        return self.current_tree

    def unmount(self) -> None:
        self.current_element = None
        self.current_tree = None


def create_root(container_name: str) -> Root:
    return Root(container_name)
