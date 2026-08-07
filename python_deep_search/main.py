from __future__ import annotations

import argparse
import sys

from .cli import run_cli
from .gui import run_gui


def entrypoint(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deep Search launcher")
    parser.add_argument("--mode", choices=["gui", "cli"], default="gui")
    args, rest = parser.parse_known_args(argv)

    if args.mode == "gui":
        run_gui()
        return 0

    return run_cli(rest)


if __name__ == "__main__":
    sys.exit(entrypoint())
