"""Emit the component as TSX: the component shell, the view nodes, the
JSX props and the interpolated text."""

from __future__ import annotations

import json
import re
from html import escape

from .model import WebComponent, WebNode
from .values import _is_quoted, _setter_name, _style_size, _tsx_expr, _unquote


def emit_tsx(component: WebComponent) -> str:
    imports = 'import { useState } from "react"\n\n' if component.states else ""
    lines: list[str] = [imports + f"export default function {component.name}() {{"]
    for state in component.states:
        setter = _setter_name(state.name)
        lines.append(f"  const [{state.name}, {setter}] = useState({_tsx_expr(state.value)})")
    if component.states:
        lines.append("")
    lines.append("  return (")
    if len(component.view) == 1:
        lines.extend(_emit_node(component.view[0], 4))
    else:
        lines.append("    <>")
        for node in component.view:
            lines.extend(_emit_node(node, 6))
        lines.append("    </>")
    lines.append("  )")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _emit_node(node: WebNode, indent: int) -> list[str]:
    tag, props, inline_text = _node_to_jsx(node)
    pad = " " * indent
    if not node.children:
        if inline_text is None:
            return [f"{pad}<{tag}{props} />"]
        return [f"{pad}<{tag}{props}>{inline_text}</{tag}>"]
    lines = [f"{pad}<{tag}{props}>"]
    if inline_text is not None:
        lines.append(f"{pad}  {inline_text}")
    for child in node.children:
        lines.extend(_emit_node(child, indent + 2))
    lines.append(f"{pad}</{tag}>")
    return lines


def _node_to_jsx(node: WebNode) -> tuple[str, str, str | None]:
    primitive = node.name.lower()
    tag = {
        "stack": "div",
        "row": "div",
        "card": "section",
        "title": "h1",
        "subtitle": "h2",
        "text": "p",
        "button": "button",
    }.get(primitive, node.name)

    props: dict[str, str] = dict(node.props)
    inline_text = node.text
    if node.args:
        first = node.args[0]
        if primitive in {"title", "subtitle", "text", "button"} and _is_quoted(first):
            inline_text = _unquote(first)
        elif primitive == "stack":
            props.setdefault("gap", first)
        else:
            props.setdefault("value", first)

    jsx_props = _emit_props(primitive, props)
    return tag, jsx_props, _emit_text(inline_text) if inline_text is not None else None


def _emit_props(primitive: str, props: dict[str, str]) -> str:
    attrs: list[str] = []
    style: dict[str, str] = {}
    if primitive == "stack":
        style.update({"display": '"flex"', "flexDirection": '"column"'})
    elif primitive == "row":
        style.update({"display": '"flex"', "flexDirection": '"row"', "alignItems": '"center"'})
    if "gap" in props:
        style["gap"] = _style_size(props.pop("gap"))

    for key, value in props.items():
        if key == "class":
            key = "className"
        if key == "onClick":
            attrs.append(f"onClick={{{_event_handler(value)}}}")
        elif key == "style":
            attrs.append(f"style={{{value}}}")
        elif key.startswith("on"):
            attrs.append(f"{key}={{() => {_tsx_expr(value)}}}")
        elif _is_quoted(value):
            attrs.append(f"{key}={{{json.dumps(_unquote(value))}}}")
        elif value in {"true", "false"} or re.match(r"^-?\d+(\.\d+)?$", value):
            attrs.append(f"{key}={{{value}}}")
        else:
            attrs.append(f"{key}={{{_tsx_expr(value)}}}")
    if style:
        body = ", ".join(f"{json.dumps(k)}: {v}" for k, v in style.items())
        attrs.append(f"style={{{{{body}}}}}")
    return (" " + " ".join(attrs)) if attrs else ""


def _event_handler(expr: str) -> str:
    inc = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\+=\s*(.+)$", expr)
    if inc:
        name, amount = inc.groups()
        return f"() => {_setter_name(name)}(({name}) => {name} + {_tsx_expr(amount)})"
    dec = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*-=\s*(.+)$", expr)
    if dec:
        name, amount = dec.groups()
        return f"() => {_setter_name(name)}(({name}) => {name} - {_tsx_expr(amount)})"
    assign = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", expr)
    if assign:
        name, value = assign.groups()
        return f"() => {_setter_name(name)}({_tsx_expr(value)})"
    return f"() => {_tsx_expr(expr)}"


def _emit_text(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", text):
        if match.start() > cursor:
            parts.append(json.dumps(text[cursor : match.start()]))
        parts.append(match.group(1))
        cursor = match.end()
    if cursor < len(text):
        parts.append(json.dumps(text[cursor:]))
    if not parts:
        return '""'
    if len(parts) == 1 and parts[0].startswith('"'):
        return escape(text, quote=False)
    return "{" + " + ".join(parts) + "}"
