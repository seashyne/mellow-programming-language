"""Turn mellow-web source into a `WebComponent`: the header, the state
declarations and the indented view tree."""

from __future__ import annotations

from .lexing import (
    _CALL_RE,
    _HEADER_RE,
    _STATE_RE,
    _split_args,
    _strip_imports_and_comments,
)
from .model import MellowWebError, WebComponent, WebNode, WebState
from .values import _is_quoted, _unquote


def parse_web_source(source: str, *, filename: str = "<mellow-web>") -> WebComponent:
    body = _strip_imports_and_comments(source.splitlines())
    if not body:
        raise MellowWebError(f"{filename}: empty mellow-web source")

    first_no, first_indent, first_text = body[0]
    if first_indent != 0:
        raise MellowWebError(f"{filename}:{first_no}: component header must start at column 1")
    match = _HEADER_RE.match(first_text)
    if not match:
        raise MellowWebError(f"{filename}:{first_no}: expected `page Name` or `component Name`")
    kind, name = match.groups()

    states: list[WebState] = []
    view_items: list[tuple[int, int, str]] = []
    in_view = False
    for line_no, indent, text in body[1:]:
        if indent == 0:
            raise MellowWebError(f"{filename}:{line_no}: only one page/component per file is supported")
        top_text = text.strip()
        if indent == 2 and top_text == "view:":
            in_view = True
            continue
        if in_view:
            view_items.append((line_no, indent, text))
            continue
        state_match = _STATE_RE.match(top_text)
        if state_match and indent == 2:
            states.append(WebState(state_match.group(1), state_match.group(2).strip()))
            continue
        if top_text:
            raise MellowWebError(f"{filename}:{line_no}: expected state declaration or `view:`")

    if not view_items:
        raise MellowWebError(f"{filename}: missing view body")
    view = _parse_nodes(view_items, base_indent=min(indent for _, indent, _ in view_items), filename=filename)
    return WebComponent(kind=kind, name=name, states=states, view=view)


def _parse_nodes(items: list[tuple[int, int, str]], *, base_indent: int, filename: str) -> list[WebNode]:
    roots: list[WebNode] = []
    stack: list[tuple[int, WebNode]] = []
    for line_no, indent, text in items:
        if indent < base_indent or (indent - base_indent) % 2 != 0:
            raise MellowWebError(f"{filename}:{line_no}: view indentation must use 2-space steps")
        node = _parse_node(text, filename=filename, line_no=line_no)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            stack[-1][1].children.append(node)
        else:
            roots.append(node)
        stack.append((indent, node))
    return roots


def _parse_node(text: str, *, filename: str, line_no: int) -> WebNode:
    if _is_quoted(text):
        return WebNode(name="Text", text=_unquote(text))
    match = _CALL_RE.match(text)
    if not match:
        raise MellowWebError(f"{filename}:{line_no}: expected `Name(...)` view node")
    name, raw_args = match.groups()
    args, props = _split_args(raw_args or "")
    return WebNode(name=name, args=args, props=props)
