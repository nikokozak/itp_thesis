#!/usr/bin/env python3
"""Codignity CLI - Command-line interface for Codignity nodes.

Run from repo root:
    .venv/bin/python tools/terminal/codignity_cli.py <subcommand> [options]

Examples:
    codignity_cli.py probe
    codignity_cli.py send "?"
    codignity_cli.py meta dump
    codignity_cli.py define ": foo 123 ;"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Ensure the codignity package is importable when run from repo root
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from codignity.session import SerialSession, SerialError
from codignity.protocol import (
    probe,
    ProbeResult,
    ensure_protocol,
    ensure_repl,
    parse_meta_dump,
    is_error,
)
from codignity.transcript import Transcript, NullTranscript

if TYPE_CHECKING:
    from codignity.transcript import Transcript as TranscriptType


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add common arguments to a subcommand parser."""
    parser.add_argument(
        "--port",
        help="Serial port path (auto-detects if omitted).",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate (default: 115200).",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=5.0,
        help="Quiet settle period in seconds (default: 5.0).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="Command timeout in seconds (default: 3.0).",
    )
    parser.add_argument(
        "--transcript",
        type=Path,
        help="Record session to transcript file.",
    )


def get_transcript(args: argparse.Namespace, port: str) -> "TranscriptType":
    """Create a transcript recorder if --transcript specified."""
    if args.transcript:
        return Transcript(args.transcript, port)
    return NullTranscript()


def print_probe_result(result: ProbeResult, as_json: bool = False) -> None:
    """Print probe result in human or JSON format."""
    if as_json:
        print(json.dumps(result.to_dict(), indent=2))
        return

    print(f"Port: {result.port}")
    print(f"Mode: {result.mode}")
    print(f"Codignity loaded: {result.codignity_loaded}")
    if result.node_id:
        print(f"Node ID: {result.node_id}")
    if result.role:
        print(f"Role: {result.role}")
    if result.ver:
        print(f"Version: {result.ver}")
    if result.mcu:
        print(f"MCU: {result.mcu}")
    if result.fifo is not None:
        print(f"FIFO size: {result.fifo}")
    if result.units:
        print(f"Units: {result.units}")
    if result.pins:
        print(f"Pins: {result.pins}")
    if result.children is not None:
        print(f"Children: {result.children}")


# ---- Subcommand handlers ----


def cmd_probe(args: argparse.Namespace) -> int:
    """Handle the `probe` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                transcript.record_comment("Probing device...")
                result = probe(session, timeout_s=args.timeout)
                print_probe_result(result, as_json=args.json)
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_send(args: argparse.Namespace) -> int:
    """Handle the `send` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                line = args.line

                if args.raw:
                    # REPL mode
                    transcript.record_sent(line)
                    response = session.send_repl(line, timeout_s=args.timeout)
                    transcript.record_received(response)
                    print(response, end="")
                else:
                    # Protocol mode - ensure we're in protocol mode first
                    if not ensure_protocol(session, timeout_s=args.timeout):
                        print(
                            "Error: Could not enter protocol mode.\n"
                            "Try: Hold SAFE + press EN to stay in REPL, then run `revive`.",
                            file=sys.stderr,
                        )
                        return 1

                    transcript.record_sent(line)
                    response = session.send_protocol(line, timeout_s=args.timeout)
                    transcript.record_received(response)
                    print(response, end="")

                    # Check for errors
                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"\nError from device: {error_msg}", file=sys.stderr)
                        return 1

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_meta(args: argparse.Namespace) -> int:
    """Handle the `meta` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print(
                        "Error: Could not enter protocol mode.\n"
                        "Is Codignity loaded? Try `probe` first.",
                        file=sys.stderr,
                    )
                    return 1

                if args.meta_cmd == "dump":
                    cmd = "meta"
                    transcript.record_sent(cmd)
                    response = session.send_protocol(cmd, timeout_s=args.timeout)
                    transcript.record_received(response)

                    if args.json:
                        meta = parse_meta_dump(response)
                        print(json.dumps(meta, indent=2))
                    else:
                        print(response, end="")

                elif args.meta_cmd == "get":
                    cmd = f"meta {args.key}"
                    transcript.record_sent(cmd)
                    response = session.send_protocol(cmd, timeout_s=args.timeout)
                    transcript.record_received(response)

                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"Error: {error_msg}", file=sys.stderr)
                        return 1

                    # Parse value from response
                    for line in response.splitlines():
                        if line.startswith("! ") and line != "! end":
                            parts = line[2:].split(None, 1)
                            if len(parts) == 2 and parts[0] == args.key:
                                print(parts[1])
                                break

                elif args.meta_cmd == "set":
                    cmd = f"meta {args.key} {args.value}"
                    transcript.record_sent(cmd)
                    response = session.send_protocol(cmd, timeout_s=args.timeout)
                    transcript.record_received(response)

                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"Error: {error_msg}", file=sys.stderr)
                        return 1

                    print(f"Set {args.key} = {args.value}")

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_define(args: argparse.Namespace) -> int:
    """Handle the `define` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print(
                        "Error: Could not enter protocol mode.\n"
                        "Is Codignity loaded? Try `probe` first.",
                        file=sys.stderr,
                    )
                    return 1

                # User provides body like ": foo 123 ;"
                # We send "define : foo 123 ;"
                body = args.body.strip()
                if body.startswith(":"):
                    cmd = f"define {body}"
                else:
                    # Assume they want to define, add the colon
                    cmd = f"define : {body}"

                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    if error_msg == "define_exists":
                        print("Hint: Word already exists. Use a different name.", file=sys.stderr)
                    elif error_msg == "define_syntax":
                        print("Hint: Check syntax. Format: `: name ... ;`", file=sys.stderr)
                    return 1

                print(f"Defined: {body}")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_simple_protocol(args: argparse.Namespace, command: str) -> int:
    """Handle simple protocol commands (history, source, explain)."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print(
                        "Error: Could not enter protocol mode.\n"
                        "Is Codignity loaded? Try `probe` first.",
                        file=sys.stderr,
                    )
                    return 1

                transcript.record_sent(command)
                response = session.send_protocol(command, timeout_s=args.timeout)
                transcript.record_received(response)
                print(response, end="")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_history(args: argparse.Namespace) -> int:
    """Handle the `history` subcommand."""
    return cmd_simple_protocol(args, "history")


def cmd_source(args: argparse.Namespace) -> int:
    """Handle the `source` subcommand."""
    return cmd_simple_protocol(args, "source")


def cmd_explain(args: argparse.Namespace) -> int:
    """Handle the `explain` subcommand."""
    return cmd_simple_protocol(args, "explain")


def cmd_validate(args: argparse.Namespace) -> int:
    """Handle the `validate` subcommand."""
    return cmd_simple_protocol(args, "validate")


def cmd_identity(args: argparse.Namespace) -> int:
    """Handle the `?` / identity subcommand."""
    return cmd_simple_protocol(args, "?")


# ---- Main ----


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Codignity CLI - Command-line interface for Codignity nodes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # probe
    p_probe = subparsers.add_parser("probe", help="Probe device and identify node")
    add_common_args(p_probe)
    p_probe.add_argument("--json", action="store_true", help="Output as JSON")
    p_probe.set_defaults(func=cmd_probe)

    # send
    p_send = subparsers.add_parser("send", help="Send a single command")
    add_common_args(p_send)
    p_send.add_argument("line", help="Command to send")
    p_send.add_argument("--raw", action="store_true", help="REPL mode (expect ' ok')")
    p_send.set_defaults(func=cmd_send)

    # meta
    p_meta = subparsers.add_parser("meta", help="Read/write node metadata")
    add_common_args(p_meta)
    p_meta.add_argument("--json", action="store_true", help="Output as JSON (dump only)")
    meta_sub = p_meta.add_subparsers(dest="meta_cmd", required=True)

    meta_dump = meta_sub.add_parser("dump", help="Dump all metadata")
    meta_get = meta_sub.add_parser("get", help="Get a metadata value")
    meta_get.add_argument("key", help="Metadata key")
    meta_set = meta_sub.add_parser("set", help="Set a metadata value")
    meta_set.add_argument("key", help="Metadata key")
    meta_set.add_argument("value", help="Metadata value")

    p_meta.set_defaults(func=cmd_meta)

    # define
    p_define = subparsers.add_parser("define", help="Define a new Forth word")
    add_common_args(p_define)
    p_define.add_argument("body", help="Definition body (e.g., ': foo 123 ;')")
    p_define.set_defaults(func=cmd_define)

    # history
    p_history = subparsers.add_parser("history", help="Show modification history")
    add_common_args(p_history)
    p_history.set_defaults(func=cmd_history)

    # source
    p_source = subparsers.add_parser("source", help="Show Forth source code")
    add_common_args(p_source)
    p_source.set_defaults(func=cmd_source)

    # explain
    p_explain = subparsers.add_parser("explain", help="Show detailed node description")
    add_common_args(p_explain)
    p_explain.set_defaults(func=cmd_explain)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate node state")
    add_common_args(p_validate)
    p_validate.set_defaults(func=cmd_validate)

    # identity (?)
    p_identity = subparsers.add_parser("identity", help="Show node identity (?)")
    add_common_args(p_identity)
    p_identity.set_defaults(func=cmd_identity)

    # TODO(thesis): Add load, snapshot subcommands in Phase 2/3

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
