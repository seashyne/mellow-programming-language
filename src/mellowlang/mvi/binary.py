"""Where the compiled runtime and the core module sit under the project root, so a lowering can
   record what it needs and a run can find the executable."""

from __future__ import annotations

import os
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _standalone_binary() -> Path:
    name = 'mellowrt.exe' if os.name == 'nt' else 'mellowrt'
    root = _project_root() / 'native' / 'standalone' / 'build'
    # Multi-config generators (Visual Studio, Xcode) emit into per-configuration
    # subdirectories; standalone_runtime_status() uses the same candidate order.
    for candidate in (root / name, root / 'Release' / name, root / 'Debug' / name):
        if candidate.exists():
            return candidate
    return root / name


def _core_module_candidates() -> list[Path]:
    root = _project_root()
    return [root / 'stdlib' / 'core.mellow', root / 'stdlib' / 'core.mel']
