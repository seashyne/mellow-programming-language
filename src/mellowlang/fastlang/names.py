"""One Mellow identifier in, one safe Python identifier out."""

from __future__ import annotations


def _py_name(name: str) -> str:
    """Convert Mellow identifier to safe Python identifier."""
    # Avoid Python keywords
    _kw = {'for', 'while', 'if', 'else', 'elif', 'def', 'class', 'return',
           'import', 'from', 'as', 'try', 'except', 'finally', 'raise',
           'pass', 'break', 'continue', 'and', 'or', 'not', 'in', 'is',
           'None', 'True', 'False', 'lambda', 'with', 'yield', 'global',
           'nonlocal', 'del', 'assert', 'print', 'exec', 'eval'}
    if name in _kw:
        return f"_{name}_"
    return name.replace('-', '_').replace('.', '_')
