"""Assembly of the block parser and the parse_program() entry point."""

from __future__ import annotations

from typing import List

from ..ast import Program
from .block_core import BlockParserBase
from .errors import ParseError
from .line_text import _rewrite_modern_aliases
from .stmt_bindings import BindingMixin
from .stmt_calls import ModuleCallMixin
from .stmt_control import ConditionalMixin, ExceptionHandlerMixin
from .stmt_definitions import DefinitionMixin
from .stmt_loops import LoopFormMixin, LoopHeadMixin
from .stmt_output import OutputMixin, UtilityMixin


class BlockParser(LoopHeadMixin, DefinitionMixin, ExceptionHandlerMixin, ConditionalMixin,
                  LoopFormMixin, BindingMixin, OutputMixin, UtilityMixin, ModuleCallMixin,
                  BlockParserBase):
    """Every statement run, in BLOCK_RUNS order."""


def _parse_block(lines: List[str], start: int, base_indent: int,
                 filename: str | None = None):
    return BlockParser(lines, start, base_indent, filename).parse()


def parse_program(lines: List[str], filename: str | None = None) -> Program:
    filename = filename or '<script>'
    ParseError.DEFAULT_FILENAME = filename
    clean = [ln.rstrip("\n") for ln in lines]
    clean = _rewrite_modern_aliases(clean)
    body, _ = BlockParser(clean, 0, 0, filename).parse()
    return Program(body)
