from __future__ import annotations

import sys

from mellowlang import __version__

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] in {"--version", "-V", "version"}:
        print(f"__main__ {__version__}")
        raise SystemExit(0)
    from mellowlang.cli import main
    raise SystemExit(main())
