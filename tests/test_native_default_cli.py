from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_run_command_defaults_to_c_engine():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [sys.executable, "-m", "mellowlang", "run", "--help"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "default: c" in result.stdout
