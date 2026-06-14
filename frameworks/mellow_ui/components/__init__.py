from __future__ import annotations

from typing import Any, Dict, Optional

from ..runtime.element import create_element


def Screen(props: Optional[Dict[str, Any]] = None):
    return create_element("Screen", props or {})


def Frame(props: Optional[Dict[str, Any]] = None):
    return create_element("Frame", props or {})


def TextLabel(text: str = "", props: Optional[Dict[str, Any]] = None):
    merged = dict(props or {})
    merged.setdefault("Text", text)
    return create_element("TextLabel", merged)


def Button(text: str = "", props: Optional[Dict[str, Any]] = None):
    merged = dict(props or {})
    merged.setdefault("Text", text)
    return create_element("Button", merged)


def ProgressBar(value: float = 0, props: Optional[Dict[str, Any]] = None):
    merged = dict(props or {})
    merged["Value"] = max(0, min(1, float(value)))
    return create_element("ProgressBar", merged)
