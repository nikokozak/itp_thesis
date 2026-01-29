#!/usr/bin/env python3
"""Bedrock TUI - ncurses interface for Bedrock Protocol nodes.

Run from repo root:
    .venv/bin/python tools/terminal/bedrock_tui.py [--port PORT] [--theme THEME]

Examples:
    bedrock_tui.py                    # Auto-detect port
    bedrock_tui.py --port /dev/ttyUSB0
    bedrock_tui.py --theme classic     # Conservative 8-color theme
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the bedrock package is importable when run from repo root
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from bedrock.ui.screens import run_tui


PORT_ENV = "BEDROCK_PORT"
PORT_ENV_LEGACY = "CODIGNITY_PORT"
LAST_PORT_PATH = Path.home() / ".bedrock" / "last_port"


def _load_last_port() -> str | None:
    try:
        return LAST_PORT_PATH.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _save_last_port(port: str) -> None:
    try:
        LAST_PORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_PORT_PATH.write_text(port + "\n", encoding="utf-8")
    except OSError:
        pass


def _port_score(port: str) -> int:
    score = 0
    if port.startswith("/dev/cu."):
        score += 50
    if "usbserial" in port:
        score += 40
    if "SLAB_USBtoUART" in port:
        score += 30
    if "wchusbserial" in port:
        score += 20
    if "usbmodem" in port:
        score += 10
    return score


def _dedupe_cu_tty(ports: list[str]) -> list[str]:
    """Prefer /dev/cu.* over /dev/tty.* when both exist."""
    port_set = set(ports)
    deduped: list[str] = []
    for port in ports:
        if port.startswith("/dev/tty."):
            cu_port = "/dev/cu." + port[len("/dev/tty.") :]
            if cu_port in port_set:
                continue
        deduped.append(port)
    return deduped


def _prompt_select_port(options: list[tuple[str, str]]) -> str | None:
    """Prompt user to select a port from labeled options."""
    if not sys.stdin.isatty():
        return None

    print("\nMultiple serial devices detected:", file=sys.stderr)
    for idx, (port, label) in enumerate(options, start=1):
        print(f"  {idx}) {port}  {label}".rstrip(), file=sys.stderr)

    while True:
        choice = input(f"Select port [1-{len(options)}] (Enter to cancel): ").strip()
        if choice == "":
            return None
        try:
            index = int(choice)
        except ValueError:
            continue
        if 1 <= index <= len(options):
            return options[index - 1][0]


def resolve_port(explicit_port: str | None) -> str | None:
    """Resolve which serial port to use when `--port` isn't provided."""
    if explicit_port:
        return explicit_port

    env_port = os.environ.get(PORT_ENV, "").strip() or os.environ.get(PORT_ENV_LEGACY, "").strip()
    if env_port:
        return env_port

    from bedrock.session import list_candidate_ports, SerialSession
    from bedrock.protocol import probe

    ports = list_candidate_ports()
    if not ports:
        return None

    ports = _dedupe_cu_tty(ports)
    ports = sorted(ports, key=lambda p: (-_port_score(p), p))

    last_port = _load_last_port()
    if last_port and last_port in ports:
        return last_port

    if len(ports) == 1:
        _save_last_port(ports[0])
        return ports[0]

    # Probe ports to find a Bedrock node (best-effort).
    results: list[tuple[str, object]] = []
    for port in ports:
        try:
            with SerialSession.open(port=port, settle_s=4.0, quiet=True) as session:
                results.append((port, probe(session, timeout_s=2.5)))
        except Exception as exc:
            results.append((port, exc))

    def label_for(result: object) -> str:
        from bedrock.protocol import ProbeResult

        if isinstance(result, ProbeResult):
            if result.bedrock_loaded:
                ident = " ".join(
                    part
                    for part in (
                        f"id:{result.node_id}" if result.node_id else "",
                        f"role:{result.role}" if result.role else "",
                        f"mode:{result.mode}",
                    )
                    if part
                )
                return f"[bedrock] {ident}".rstrip()
            return f"[{result.mode}] bedrock:no"
        return "[unavailable]"

    bedrock_ports = [
        port for port, result in results
        if getattr(result, "bedrock_loaded", False)
    ]
    if len(bedrock_ports) == 1:
        _save_last_port(bedrock_ports[0])
        return bedrock_ports[0]

    # If multiple Bedrock nodes are present, prompt selection.
    if len(bedrock_ports) > 1:
        options = [(port, label_for(result)) for port, result in results]
        selected = _prompt_select_port(options)
        if selected:
            _save_last_port(selected)
        return selected

    # No Bedrock nodes detected: if exactly one responsive REPL target exists, use it.
    repl_ports = [
        port for port, result in results
        if getattr(result, "mode", None) == "repl"
    ]
    if len(repl_ports) == 1:
        _save_last_port(repl_ports[0])
        return repl_ports[0]

    # Otherwise, prompt if possible; fall back to the best-scored port.
    options = [(port, label_for(result)) for port, result in results]
    selected = _prompt_select_port(options)
    if selected:
        _save_last_port(selected)
        return selected

    return ports[0]


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bedrock TUI - ncurses interface for Bedrock Protocol nodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--port",
        help=(
            f"Serial port path (auto-detects if omitted; env: {PORT_ENV})."
        ),
    )
    parser.add_argument(
        "--theme",
        choices=["cyberpunk", "classic"],
        help="Color theme (default: cyberpunk). Also configurable via BEDROCK_TUI_THEME.",
    )

    args = parser.parse_args(argv)

    try:
        port = resolve_port(args.port)
        return run_tui(port=port, theme=args.theme)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
