from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import escape
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


_HEADER_RE = re.compile(r"^(page|component)\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
_STATE_RE = re.compile(r"^state\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
_CALL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*(?:\((.*)\))?\s*$")
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def compile_file_to_tsx(input_path: str | Path, out_path: str | Path | None = None) -> dict[str, Any]:
    source_path = Path(input_path)
    component = parse_web_source(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    tsx = emit_tsx(component)
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(tsx, encoding="utf-8")
    return {"ok": True, "component": component.name, "kind": component.kind, "tsx": tsx}


def prepare_react_dev_app(
    input_path: str | Path,
    *,
    app_dir: str | Path = ".mellow/web-dev",
    install: bool = True,
) -> dict[str, Any]:
    source_path = Path(input_path).resolve()
    target_dir = Path(app_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    src_dir = target_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    generated = compile_file_to_tsx(source_path, target_dir / "MellowApp.tsx")
    _write_dev_file(target_dir / "package.json", _dev_package_json())
    _write_dev_file(target_dir / "index.html", _dev_index_html())
    _write_dev_file(target_dir / "tsconfig.json", _dev_tsconfig_json())
    _write_dev_file(target_dir / "vite.config.ts", _dev_vite_config())
    _write_dev_file(src_dir / "main.tsx", _dev_main_tsx())

    if install and not (target_dir / "node_modules").exists():
        npm = shutil.which("npm")
        if npm is None:
            raise MellowWebError("npm was not found on PATH; install Node.js/npm to run mellow web dev")
        completed = subprocess.run([npm, "install"], cwd=target_dir, check=False)
        if completed.returncode != 0:
            raise MellowWebError(f"npm install failed with exit code {completed.returncode}")

    return {
        "ok": True,
        "app_dir": str(target_dir),
        "source": str(source_path),
        "component": generated["component"],
        "tsx": str(target_dir / "MellowApp.tsx"),
    }


def run_react_dev_app(
    input_path: str | Path,
    *,
    app_dir: str | Path = ".mellow/web-dev",
    port: int = 5179,
    host: str = "127.0.0.1",
    build_only: bool = False,
) -> int:
    prepared = prepare_react_dev_app(input_path, app_dir=app_dir, install=True)
    npm = shutil.which("npm")
    if npm is None:
        raise MellowWebError("npm was not found on PATH; install Node.js/npm to run mellow web dev")
    target_dir = Path(prepared["app_dir"])
    if build_only:
        return int(subprocess.run([npm, "run", "build"], cwd=target_dir, check=False).returncode)
    print(f"[OK] mellow-web generated: {prepared['tsx']}")
    print(f"[OK] React dev server: http://{host}:{port}/")
    return int(subprocess.run([npm, "run", "dev", "--", "--host", host, "--port", str(port)], cwd=target_dir, check=False).returncode)


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


def _write_dev_file(path: Path, content: str) -> None:
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8")


def _dev_package_json() -> str:
    return json.dumps(
        {
            "private": True,
            "type": "module",
            "scripts": {
                "build": "vite build",
                "dev": "vite",
            },
            "dependencies": {
                "@vitejs/plugin-react": "^5.0.0",
                "vite": "^7.0.0",
                "typescript": "^5.8.0",
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
            },
            "devDependencies": {},
        },
        indent=2,
    ) + "\n"


def _dev_index_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mellow Web</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
"""


def _dev_main_tsx() -> str:
    return """import React from "react"
import { createRoot } from "react-dom/client"
import MellowApp from "../MellowApp"

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MellowApp />
  </React.StrictMode>,
)
"""


def _dev_tsconfig_json() -> str:
    return json.dumps(
        {
            "compilerOptions": {
                "jsx": "react-jsx",
                "module": "ESNext",
                "moduleResolution": "Bundler",
                "target": "ES2020",
                "strict": True,
                "skipLibCheck": True,
                "types": ["vite/client"],
            },
            "include": ["src", "MellowApp.tsx"],
        },
        indent=2,
    ) + "\n"


def _dev_vite_config() -> str:
    return """import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

export default defineConfig({
  plugins: [react()],
})
"""


def _strip_imports_and_comments(lines: list[str]) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for idx, raw in enumerate(lines, start=1):
        if "\t" in raw:
            raise MellowWebError(f"line {idx}: tabs are not supported in mellow-web indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("use ") or stripped.startswith("import "):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        out.append((idx, indent, raw.strip()))
    return out


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


def _split_args(raw: str) -> tuple[list[str], dict[str, str]]:
    parts = _split_top_level(raw)
    args: list[str] = []
    props: dict[str, str] = {}
    for part in parts:
        if not part:
            continue
        key, value = _split_named_arg(part)
        if key:
            props[key] = value
        else:
            args.append(part.strip())
    return args, props


def _split_top_level(raw: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    depth = 0
    escape = False
    for ch in raw:
        if quote:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return parts


def _split_named_arg(part: str) -> tuple[str | None, str]:
    quote: str | None = None
    depth = 0
    escape = False
    for idx, ch in enumerate(part):
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            key = part[:idx].strip()
            if _IDENT_RE.match(key):
                return key, part[idx + 1 :].strip()
    return None, part


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


def _tsx_expr(value: str) -> str:
    value = value.strip()
    if _is_quoted(value):
        return json.dumps(_unquote(value))
    return value


def _style_size(value: str) -> str:
    value = value.strip()
    if re.match(r"^-?\d+(\.\d+)?$", value):
        return f"{value}"
    return _tsx_expr(value)


def _setter_name(name: str) -> str:
    return "set" + name[:1].upper() + name[1:]


def _is_quoted(value: str) -> bool:
    return len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}


def _unquote(value: str) -> str:
    if not _is_quoted(value):
        return value
    return json.loads(value) if value[0] == '"' else value[1:-1]
