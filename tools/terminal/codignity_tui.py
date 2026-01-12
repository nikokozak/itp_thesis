#!/usr/bin/env python3
"""Codignity TUI - ncurses interface for Codignity nodes.

Run from repo root:
    .venv/bin/python tools/terminal/codignity_tui.py [--port PORT]

Examples:
    codignity_tui.py                    # Auto-detect port
    codignity_tui.py --port /dev/ttyUSB0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the codignity package is importable when run from repo root
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from codignity.ui.screens import run_tui


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Codignity TUI - ncurses interface for Codignity nodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        help="Serial port path (auto-detects if omitted).",
    )

    args = parser.parse_args(argv)

    try:
        return run_tui(port=args.port)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
