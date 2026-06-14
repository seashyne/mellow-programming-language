"""Mellow UI Framework v1.

Small React-like UI core for Mellow tools and future Roblox rendering.
"""
from .runtime.element import Element, create_element
from .runtime.renderer import Root, create_root, render_to_json, render_to_tree
from .runtime.state import State, use_state
from . import components

# React-like aliases
createElement = create_element
createRoot = create_root
useState = use_state

# Built-in components
Screen = components.Screen
Frame = components.Frame
TextLabel = components.TextLabel
Button = components.Button
ProgressBar = components.ProgressBar

__all__ = [
    "Element",
    "Root",
    "State",
    "create_element",
    "createElement",
    "create_root",
    "createRoot",
    "render_to_tree",
    "render_to_json",
    "use_state",
    "useState",
    "Screen",
    "Frame",
    "TextLabel",
    "Button",
    "ProgressBar",
]
