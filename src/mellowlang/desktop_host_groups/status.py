"""The capability report `mellow desktop status` prints."""

from __future__ import annotations

import sys
from typing import Dict


def desktop_status() -> Dict[str, Any]:
    return {
        'ok': True,
        'engine': 'native-ui-runtime',
        'backend': 'ttk',
        'cross_platform': ['windows', 'linux'],
        'supported': ['window', 'label', 'button', 'input', 'textarea', 'checkbox', 'select', 'slider', 'listbox', 'menu', 'menu_item', 'vstack', 'hstack', 'grid', 'run'],
        'builder': 'portable-bundle',
        'requires_pyinstaller': False,
        'python': sys.version.split()[0],
        'platform': sys.platform,
    }
