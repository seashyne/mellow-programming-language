"""Mellow Code Assistant.

Offline + deterministic helper that explains script structure and provides hints.
"""

from .core import ASSISTANT_VERSION, AssistantReport, analyze_source, render_human

__all__ = ["ASSISTANT_VERSION", "AssistantReport", "analyze_source", "render_human"]
