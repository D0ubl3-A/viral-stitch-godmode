from __future__ import annotations

import sys

from . import engine
from .godmode import extension_main


EXTENSIONS = {"doctor", "plan", "audit-manifest", "patch-visuals"}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in EXTENSIONS:
        return extension_main(sys.argv[1:])
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())

