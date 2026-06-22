"""
MellowLang LSP Server
"""

from __future__ import annotations

import sys
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

PYGLS_IMPORT_ERROR: str | None = None
PYGLS_BACKEND = "stub"
HAVE_PYGLS = False

TEXT_DOCUMENT_COMPLETION = 'textDocument/completion'
TEXT_DOCUMENT_DEFINITION = 'textDocument/definition'
TEXT_DOCUMENT_DID_CHANGE = 'textDocument/didChange'
TEXT_DOCUMENT_DID_OPEN = 'textDocument/didOpen'
TEXT_DOCUMENT_DOCUMENT_SYMBOL = 'textDocument/documentSymbol'
TEXT_DOCUMENT_HOVER = 'textDocument/hover'

try:
    # pygls v2.x moved LanguageServer under pygls.lsp.server and prefers lsprotocol types
    from pygls.lsp.server import LanguageServer
    from lsprotocol import types as lsp_types

    CompletionItem = lsp_types.CompletionItem
    CompletionItemKind = lsp_types.CompletionItemKind
    CompletionList = lsp_types.CompletionList
    CompletionOptions = lsp_types.CompletionOptions
    CompletionParams = lsp_types.CompletionParams
    DefinitionParams = lsp_types.DefinitionParams
    Diagnostic = lsp_types.Diagnostic
    DiagnosticSeverity = lsp_types.DiagnosticSeverity
    DidChangeTextDocumentParams = lsp_types.DidChangeTextDocumentParams
    DidOpenTextDocumentParams = lsp_types.DidOpenTextDocumentParams
    DocumentSymbol = lsp_types.DocumentSymbol
    DocumentSymbolParams = lsp_types.DocumentSymbolParams
    Hover = lsp_types.Hover
    HoverParams = lsp_types.HoverParams
    Location = lsp_types.Location
    MarkupContent = lsp_types.MarkupContent
    MarkupKind = lsp_types.MarkupKind
    Position = lsp_types.Position
    Range = lsp_types.Range
    SymbolKind = lsp_types.SymbolKind

    HAVE_PYGLS = True
    PYGLS_BACKEND = "pygls-v2"
except Exception as e_v2:  # pragma: no cover - environment dependent
    try:
        # pygls v1.x API
        from pygls.server import LanguageServer
        from pygls.lsp.types import (
            CompletionItem,
            CompletionItemKind,
            CompletionList,
            CompletionOptions,
            CompletionParams,
            DefinitionParams,
            Diagnostic,
            DiagnosticSeverity,
            DidChangeTextDocumentParams,
            DidOpenTextDocumentParams,
            DocumentSymbol,
            DocumentSymbolParams,
            Hover,
            HoverParams,
            Location,
            MarkupContent,
            MarkupKind,
            Position,
            Range,
            SymbolKind,
        )

        HAVE_PYGLS = True
        PYGLS_BACKEND = "pygls-v1"
    except Exception as e_v1:  # pragma: no cover - fallback for test/import environments
        PYGLS_IMPORT_ERROR = f"v2 import failed: {e_v2!r}; v1 import failed: {e_v1!r}"

        class _FeatureMixin:
            def feature(self, *args, **kwargs):
                def deco(fn):
                    return fn
                return deco
            def start_io(self):
                raise RuntimeError('pygls is required to start the Mellow LSP server')

        class LanguageServer(_FeatureMixin):
            def __init__(self, *args, **kwargs):
                pass
            def publish_diagnostics(self, uri, diags):
                self._last_publish = (uri, diags)

        @dataclass
        class Position:
            line: int
            character: int

        @dataclass
        class Range:
            start: Position
            end: Position

        @dataclass
        class Diagnostic:
            range: Range
            message: str
            severity: int
            source: str

        class DiagnosticSeverity:
            Error = 1
            Warning = 2
            Information = 3
            Hint = 4

        class CompletionItemKind:
            Function = 3
            Variable = 6
            Keyword = 14

        @dataclass
        class CompletionItem:
            label: str
            kind: int | None = None
            detail: str | None = None
            documentation: str | None = None

        @dataclass
        class CompletionList:
            is_incomplete: bool
            items: list

        @dataclass
        class CompletionOptions:
            trigger_characters: list

        @dataclass
        class MarkupContent:
            kind: str
            value: str

        class MarkupKind:
            Markdown = 'markdown'

        @dataclass
        class Hover:
            contents: MarkupContent
            range: Range | None = None

        @dataclass
        class Location:
            uri: str
            range: Range

        class SymbolKind:
            Function = 12
            Event = 24
            Variable = 13

        @dataclass
        class DocumentSymbol:
            name: str
            detail: str | None
            kind: int
            range: Range
            selection_range: Range

        class CompletionParams: pass
        class DefinitionParams: pass
        class DidChangeTextDocumentParams: pass
        class DidOpenTextDocumentParams: pass
        class DocumentSymbolParams: pass
        class HoverParams: pass


def lsp_runtime_status() -> dict[str, object]:
    return {
        "ready": HAVE_PYGLS,
        "backend": PYGLS_BACKEND,
        "error": PYGLS_IMPORT_ERROR,
    }
from mellowlang import __version__
from mellowlang.lint import lint_source

KEYWORDS: dict[str, str] = {
    'if': 'Conditional branch.',
    'else': 'Fallback branch for an `if`.',
    'end': 'Closes block-style syntax.',
    'loop': 'Loop keyword used in several loop forms.',
    'while': 'Loop while condition stays true.',
    'repeat': 'Repeat a block until a condition becomes true.',
    'until': 'Condition terminator for `repeat` blocks.',
    'for': 'Iterate over ranges or collections.',
    'in': 'Used by `for` loops to bind iterables.',
    'break': 'Exit the current loop early.',
    'continue': 'Skip to the next loop iteration.',
    'and': 'Logical AND.',
    'or': 'Logical OR.',
    'not': 'Logical NOT.',
    'skill': 'Declare a reusable function-like skill.',
    'on': 'Declare an event handler block.',
    'emit': 'Send an event to listeners.',
    'catch': 'Catch a thrown runtime error inside `try`.',
    'try': 'Begin a protected block with optional catch/finally.',
    'import': 'Import a module or package.',
    'vec': 'Create a vector value.',
    'vector': 'Alias for vector constructors/utilities.',
    'vec2': 'Create a 2D vector.',
    'vec3': 'Create a 3D vector.',
    'vec4': 'Create a 4D vector.',
    'true': 'Boolean true.',
    'false': 'Boolean false.',
    'nil': 'Empty/null-like value.',
}

BUILTINS: dict[str, str] = {
    'print': 'Print values to stdout.',
    'len': 'Return the length of a list, string, or map.',
    'type': 'Return the runtime type name of a value.',
    'math': 'Math helper namespace/module.',
    'time': 'Time helper namespace/module.',
    'random': 'Random number helper.',
    'file_read': 'Read a UTF-8 text file.',
    'file_write': 'Write text to a file.',
    'json_encode': 'Encode a value to JSON text.',
    'json_decode': 'Decode JSON text to a value.',
}

DOCS: dict[str, tuple[str, str]] = {}
DOCS.update({k: ('keyword', v) for k, v in KEYWORDS.items()})
DOCS.update({k: ('builtin', v) for k, v in BUILTINS.items()})
DOC_STORE: Dict[str, str] = {}

SKILL_RE = re.compile(r'^\s*skill\s+([A-Za-z_][\w]*)\s*\((.*?)\)')
ON_RE = re.compile(r'^\s*on\s+([A-Za-z_][\w]*)\s*\((.*?)\)')
KEEP_RE = re.compile(r'^\s*(?:keep\s+)?([A-Za-z_][\w]*)\s*=')
WORD_RE = re.compile(r'[A-Za-z_][\w]*')


def _full_line_range(line0: int) -> Range:
    return Range(start=Position(line=line0, character=0), end=Position(line=line0, character=9999))


def _range_for_word(line0: int, start: int, end: int) -> Range:
    return Range(start=Position(line=line0, character=start), end=Position(line=line0, character=end))


def _extract_word(text: str, line: int, char: int) -> Optional[str]:
    lines = text.splitlines()
    if line < 0 or line >= len(lines):
        return None
    raw = lines[line]
    for m in WORD_RE.finditer(raw):
        if m.start() <= char <= m.end():
            return m.group(0)
    return None


def _iter_symbols(text: str):
    for idx, raw in enumerate(text.splitlines()):
        m = SKILL_RE.match(raw)
        if m:
            yield {'kind': 'skill', 'name': m.group(1), 'line': idx, 'range': _range_for_word(idx, m.start(1), m.end(1)), 'detail': f"skill({m.group(2)})"}
            continue
        m = ON_RE.match(raw)
        if m:
            yield {'kind': 'event', 'name': m.group(1), 'line': idx, 'range': _range_for_word(idx, m.start(1), m.end(1)), 'detail': f"on({m.group(2)})"}
            continue
        m = KEEP_RE.match(raw)
        if m and not raw.lstrip().startswith('#'):
            yield {'kind': 'variable', 'name': m.group(1), 'line': idx, 'range': _range_for_word(idx, m.start(1), m.end(1)), 'detail': 'top-level value'}


def _diagnostic_severity(kind: str) -> int:
    return {
        'SYNTAX': DiagnosticSeverity.Error,
        'UNDEFINED': DiagnosticSeverity.Warning,
        'UNUSED': DiagnosticSeverity.Hint,
        'SHADOW': DiagnosticSeverity.Warning,
        'STYLE': DiagnosticSeverity.Information,
    }.get(kind, DiagnosticSeverity.Warning)


def _mk_diag(msg: str, line0: int, kind: str) -> Diagnostic:
    return Diagnostic(range=_full_line_range(line0), message=msg, severity=_diagnostic_severity(kind), source='mellow')


class MellowLangLanguageServer(LanguageServer):
    pass


server = MellowLangLanguageServer('mellowlang-lsp', __version__)


def _publish(ls: MellowLangLanguageServer, uri: str, text: str):
    DOC_STORE[uri] = text
    issues = lint_source(text)
    diags: List[Diagnostic] = []
    for iss in issues:
        line0 = max(0, (iss.line or 1) - 1)
        diags.append(_mk_diag(iss.message, line0, iss.kind))
    ls.publish_diagnostics(uri, diags)


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: MellowLangLanguageServer, params: DidOpenTextDocumentParams):
    _publish(ls, params.text_document.uri, params.text_document.text)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: MellowLangLanguageServer, params: DidChangeTextDocumentParams):
    text = params.content_changes[0].text
    _publish(ls, params.text_document.uri, text)


@server.feature(TEXT_DOCUMENT_COMPLETION, CompletionOptions(trigger_characters=['.', ':', '(', ' ']))
def completions(ls: MellowLangLanguageServer, params: CompletionParams):
    items: List[CompletionItem] = []
    for kw, doc in sorted(KEYWORDS.items()):
        items.append(CompletionItem(label=kw, kind=CompletionItemKind.Keyword, detail='keyword', documentation=doc))
    for name, doc in sorted(BUILTINS.items()):
        items.append(CompletionItem(label=name, kind=CompletionItemKind.Function, detail='builtin', documentation=doc))
    uri = params.text_document.uri
    for sym in _iter_symbols(DOC_STORE.get(uri, '')):
        kind = CompletionItemKind.Function if sym['kind'] == 'skill' else CompletionItemKind.Variable
        items.append(CompletionItem(label=sym['name'], kind=kind, detail=sym['detail'], documentation=f"Local {sym['kind']} defined in this file."))
    return CompletionList(is_incomplete=False, items=items)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: MellowLangLanguageServer, params: HoverParams):
    uri = params.text_document.uri
    text = DOC_STORE.get(uri, '')
    word = _extract_word(text, params.position.line, params.position.character)
    if not word:
        return None
    if word in DOCS:
        label, doc = DOCS[word]
        return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=f"**{word}** ({label})\n\n{doc}"))
    for sym in _iter_symbols(text):
        if sym['name'] == word:
            return Hover(contents=MarkupContent(kind=MarkupKind.Markdown, value=f"**{word}** ({sym['kind']})\n\n{sym['detail']}"), range=sym['range'])
    return None


@server.feature(TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbols(ls: MellowLangLanguageServer, params: DocumentSymbolParams):
    uri = params.text_document.uri
    text = DOC_STORE.get(uri, '')
    out: List[DocumentSymbol] = []
    for sym in _iter_symbols(text):
        kind = {'skill': SymbolKind.Function, 'event': SymbolKind.Event, 'variable': SymbolKind.Variable}[sym['kind']]
        out.append(DocumentSymbol(name=sym['name'], detail=sym['detail'], kind=kind, range=_full_line_range(sym['line']), selection_range=sym['range']))
    return out


@server.feature(TEXT_DOCUMENT_DEFINITION)
def definition(ls: MellowLangLanguageServer, params: DefinitionParams):
    uri = params.text_document.uri
    text = DOC_STORE.get(uri, '')
    word = _extract_word(text, params.position.line, params.position.character)
    if not word:
        return None
    defs = []
    for sym in _iter_symbols(text):
        if sym['kind'] == 'skill' and sym['name'] == word:
            defs.append(Location(uri=uri, range=sym['range']))
    return defs or None


def start_lsp(*, show_banner: bool | None = None) -> int:
    if not HAVE_PYGLS:
        detail = PYGLS_IMPORT_ERROR or 'unknown pygls import failure'
        raise RuntimeError(
            "Mellow LSP could not start.\n"
            f"pygls import failed: {detail}\n\n"
            "Fix options:\n"
            "  1) Reinstall the project in this environment: python -m pip install -e .\n"
            "  2) Verify pygls is installed for the same Python as `mellow`\n"
            "  3) Run `mellow doctor --strict` to inspect LSP readiness\n"
        )
    if show_banner is None:
        show_banner = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if show_banner:
        print(
            "Mellow LSP is ready and waiting for an editor over stdio.\n"
            "This process stays open until the editor disconnects.\n"
            "Setup guide: docs/LSP.md\n"
            "VS Code: install the extension from vscode-extension, then open a .mellow file.\n"
            "Press Ctrl+C to stop this standalone server.",
            file=sys.stderr,
            flush=True,
        )
    server.start_io()
    return 0


if __name__ == '__main__':
    raise SystemExit(start_lsp())
