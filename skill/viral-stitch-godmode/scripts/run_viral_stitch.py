from __future__ import annotations

import os
import subprocess
import sys


INSTALL_URL = "https://github.com/D0ubl3-A/viral-stitch-godmode/releases/download/v1.3.0/viral_stitch_godmode-1.3.0-py3-none-any.whl"


def main() -> int:
    try:
        import viral_stitch.cli  # noqa: F401
    except ImportError:
        print("Viral Stitch Godmode is not installed.", file=sys.stderr)
        print(f"Install with: {sys.executable} -m pip install {INSTALL_URL}", file=sys.stderr)
        return 2
    env = os.environ.copy()
    command = [sys.executable, "-m", "viral_stitch.cli", *sys.argv[1:]]
    return subprocess.run(command, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
