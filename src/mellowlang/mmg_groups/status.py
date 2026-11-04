"""What this build of the MMG runtime can do and where it can show it."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict


def mmg_status() -> Dict[str, Any]:
    return {
        'engine': 'mellow-magic-graphics',
        'backend': 'mmg-render-core/tk-canvas',
        'portable_bundle': True,
        'python_required': True,
        'platform': sys.platform,
        'display_available': bool(os.environ.get('DISPLAY') or sys.platform.startswith('win') or sys.platform == 'darwin'),
        'features': ['scene-graph', 'sprite', 'texture', 'camera', 'frame-loop', 'input-events', 'render-graph'],
        'note': 'MMG Render Core is a cross-platform render/runtime foundation. It is not a shader/GPU-native engine yet.',
    }
