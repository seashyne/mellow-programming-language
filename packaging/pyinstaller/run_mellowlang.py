import sys
from pathlib import Path

def _dev_add_src_to_path() -> None:
    """
    Dev mode: allow `python packaging/pyinstaller/run_mellowlang.py`
    to import from repo ./src without installing the package.
    In frozen mode, PyInstaller handles sys.path.
    """
    if getattr(sys, "frozen", False):
        return

    # .../packaging/pyinstaller/run_mellowlang.py -> project root is parents[2]
    repo_root = Path(__file__).resolve().parents[2]
    src_path = repo_root / "src"
    sys.path.insert(0, str(src_path))

_dev_add_src_to_path()

from mellowlang.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
