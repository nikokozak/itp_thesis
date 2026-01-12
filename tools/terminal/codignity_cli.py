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
import time
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
from codignity.snapshot import (
    Snapshot,
    SnapshotDiff,
    compute_diff,
    format_diff,
    extract_def_name,
    load_baseline_defs,
)
from codignity.defs_log import (
    append_define,
    load_defs,
    load_defs_from_file,
    merge_defs,
)

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

                # Capture define to per-node defs log
                # Get node_id from meta id
                node_id = "unknown"
                try:
                    id_response = session.send_protocol("meta id", timeout_s=args.timeout)
                    for line in id_response.splitlines():
                        if line.startswith("! id "):
                            node_id = line[5:].strip()
                            break
                except Exception:
                    pass  # Fall back to "unknown"

                defs_path = append_define(node_id, cmd, port=session.port)
                print(f"Defined: {body}")
                print(f"  (captured to {defs_path})")
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


def cmd_load(args: argparse.Namespace) -> int:
    """Handle the `load` subcommand - load Codignity firmware."""
    # Resolve firmware path relative to repo root
    if args.file:
        firmware_path = Path(args.file)
    else:
        # Default: firmware/esp32/codignity.fs relative to repo root
        repo_root = _this_dir.parent.parent
        firmware_path = repo_root / "firmware" / "esp32" / "codignity.fs"

    if not firmware_path.exists():
        print(f"Error: Firmware file not found: {firmware_path}", file=sys.stderr)
        return 1

    try:
        # Use short settle (2s) to interrupt autoexec and get clean REPL
        # ESP32forth's autoexec waits ~3s, so 2s settle + sending input interrupts it
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=2.0,  # Short settle to interrupt autoexec
        ) as session:
            with get_transcript(args, session.port) as transcript:
                # Step 1: Interrupt autoexec and get REPL prompt
                transcript.record_comment("Interrupting autoexec to enter REPL...")
                print("Entering REPL mode...")

                # Send empty line to interrupt autoexec
                session.send_line("")
                result = session.read_until(b" ok", args.timeout)
                if not result.found:
                    # Try again with stack reset
                    session.send_line("sp0 sp!")
                    result = session.read_until(b" ok", args.timeout)

                if not result.found:
                    print(
                        "Error: Could not enter REPL mode.\n"
                        "Try: Hold SAFE + press EN to stay in REPL.",
                        file=sys.stderr,
                    )
                    return 1

                session.drain(0.2)  # Clear any remaining output

                # Step 2: Load firmware line by line
                transcript.record_comment(f"Loading {firmware_path.name}...")
                print(f"Loading {firmware_path}...")

                with open(firmware_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                total_lines = len(lines)
                loaded = 0
                errors = 0

                for i, line in enumerate(lines):
                    line = line.rstrip("\n\r")

                    # Skip empty lines and comments
                    if not line.strip() or line.strip().startswith("\\"):
                        continue

                    # Send line and wait for ok
                    if not args.no_mute:
                        # Show progress
                        pct = (i + 1) * 100 // total_lines
                        print(f"\r  [{pct:3d}%] {loaded} lines loaded...", end="", flush=True)
                    else:
                        transcript.record_sent(line)

                    try:
                        response = session.send_repl(line, timeout_s=args.timeout)
                        if not args.no_mute:
                            pass  # Muted
                        else:
                            transcript.record_received(response)
                            print(response, end="")
                        loaded += 1
                    except SerialError as e:
                        errors += 1
                        print(f"\nError at line {i+1}: {e}", file=sys.stderr)
                        print(f"  Line: {line[:60]}...", file=sys.stderr)
                        if errors > 3:
                            print("Too many errors, aborting.", file=sys.stderr)
                            return 1

                print(f"\r  [100%] {loaded} lines loaded.    ")

                # Step 3: Enter protocol mode with revive
                transcript.record_comment("Entering protocol mode...")
                print("Entering protocol mode...")
                session.drain(0.2)  # Clear any buffered output from firmware load
                session.send_line("revive")
                result = session.read_until(b" ok", args.timeout)
                if not result.found:
                    print("Warning: revive did not return ok", file=sys.stderr)

                session.drain(0.3)

                # Step 4: Validate
                transcript.record_comment("Validating...")
                print("Validating...")
                transcript.record_sent("validate")
                response = session.send_protocol("validate", timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Validation failed: {error_msg}", file=sys.stderr)
                    return 1

                if "! ok" in response:
                    print("Validation passed.")
                else:
                    print(f"Unexpected validation response: {response}", file=sys.stderr)
                    return 1

                # Step 5: Persist if requested
                if args.persist:
                    transcript.record_comment("Persisting with safe-save...")
                    print("Running safe-save...")
                    transcript.record_sent("safe-save")
                    response = session.send_protocol("safe-save", timeout_s=args.timeout)
                    transcript.record_received(response)

                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"safe-save failed: {error_msg}", file=sys.stderr)
                        return 1

                    print("Saved to flash.")

                    transcript.record_comment("Restarting...")
                    print("Restarting...")
                    transcript.record_sent("restart")
                    response = session.send_protocol("restart", timeout_s=args.timeout)
                    transcript.record_received(response)
                    print("Device restarting.")

                print("Load complete.")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_snapshot_create(args: argparse.Namespace) -> int:
    """Handle the `snapshot create` subcommand."""
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

                # Get identity info
                transcript.record_sent("?")
                response = session.send_protocol("?", timeout_s=args.timeout)
                transcript.record_received(response)

                # Parse identity
                identity: dict[str, str] = {}
                for line in response.splitlines():
                    line = line.strip()
                    if line.startswith("! ") and line != "! end":
                        parts = line[2:].split(None, 1)
                        if len(parts) >= 1:
                            key = parts[0]
                            value = parts[1] if len(parts) > 1 else ""
                            identity[key] = value

                # Get all meta
                transcript.record_sent("meta")
                response = session.send_protocol("meta", timeout_s=args.timeout)
                transcript.record_received(response)
                meta = parse_meta_dump(response)

                # Load defs from per-node defs log (cross-invocation capture)
                node_id = identity.get("id", "unknown")
                base_defs = load_defs(node_id)
                if base_defs:
                    print(f"  Loaded {len(base_defs)} defs from .codignity/defs/{node_id}.defs")

                # Merge with --defs file if provided
                override_defs: list[str] = []
                if args.defs:
                    defs_path = Path(args.defs)
                    if not defs_path.exists():
                        print(f"Error: Defs file not found: {defs_path}", file=sys.stderr)
                        return 1
                    override_defs = load_defs_from_file(defs_path)
                    if override_defs:
                        print(f"  Loaded {len(override_defs)} defs from {defs_path}")

                # Merge and de-dup by word name
                defs, merge_notes = merge_defs(base_defs, override_defs)
                for note in merge_notes:
                    print(f"  Note: {note}")

                # Create snapshot
                snapshot = Snapshot.create_now(
                    node_id=identity.get("id"),
                    role=identity.get("role"),
                    ver=identity.get("ver"),
                    meta=meta,
                    defs=defs,
                    notes={},
                )

                # Optionally run safe-save before snapshot
                if args.save_first:
                    transcript.record_comment("Running safe-save before snapshot...")
                    print("Running safe-save...")
                    transcript.record_sent("safe-save")
                    response = session.send_protocol("safe-save", timeout_s=args.timeout)
                    transcript.record_received(response)

                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"safe-save failed: {error_msg}", file=sys.stderr)
                        return 1

                    snapshot.notes["safe-save"] = "ok"

                # Save snapshot
                out_path = Path(args.out)
                snapshot.save(out_path)

                print(f"Snapshot saved to: {out_path}")
                print(f"  Node: {snapshot.node_id or 'unknown'}")
                print(f"  Role: {snapshot.role or 'unknown'}")
                print(f"  Meta keys: {len(snapshot.meta)}")
                print(f"  Defs: {len(snapshot.defs)}")

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_snapshot_restore(args: argparse.Namespace) -> int:
    """Handle the `snapshot restore` subcommand."""
    # Load snapshot file first
    snap_path = Path(args.input)
    if not snap_path.exists():
        print(f"Error: Snapshot file not found: {snap_path}", file=sys.stderr)
        return 1

    try:
        snapshot = Snapshot.load(snap_path)
    except ValueError as e:
        print(f"Error parsing snapshot: {e}", file=sys.stderr)
        return 1

    print(f"Loaded snapshot: {snap_path}")
    print(f"  Date: {snapshot.date}")
    print(f"  Node: {snapshot.node_id or 'unknown'}")
    print(f"  Role: {snapshot.role or 'unknown'}")
    print(f"  Meta keys: {len(snapshot.meta)}")
    print(f"  Defs: {len(snapshot.defs)}")

    # Confirm unless --yes
    if not args.yes:
        print("\nThis will:")
        print("  1. Load Codignity firmware (interrupts autoexec)")
        print("  2. Apply all meta set commands")
        print("  3. Apply all define commands")
        print("  4. Validate")
        print("  5. Run safe-save and restart")
        print("\nContinue? [y/N] ", end="", flush=True)
        response = input().strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return 0

    try:
        # Use short settle to interrupt autoexec
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=2.0,  # Short settle to interrupt autoexec
        ) as session:
            with get_transcript(args, session.port) as transcript:
                # Step 1: Get into REPL mode
                transcript.record_comment("Interrupting autoexec to enter REPL...")
                print("Entering REPL mode...")

                session.send_line("")
                result = session.read_until(b" ok", args.timeout)
                if not result.found:
                    session.send_line("sp0 sp!")
                    result = session.read_until(b" ok", args.timeout)

                if not result.found:
                    print(
                        "Error: Could not enter REPL mode.\n"
                        "Try: Hold SAFE + press EN to stay in REPL.",
                        file=sys.stderr,
                    )
                    return 1

                session.drain(0.2)

                # Step 2: Load Codignity firmware
                repo_root = _this_dir.parent.parent
                firmware_path = repo_root / "firmware" / "esp32" / "codignity.fs"

                if not firmware_path.exists():
                    print(f"Error: Firmware not found: {firmware_path}", file=sys.stderr)
                    return 1

                transcript.record_comment(f"Loading {firmware_path.name}...")
                print(f"Loading {firmware_path.name}...")

                with open(firmware_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                total_lines = len(lines)
                loaded = 0

                for i, line in enumerate(lines):
                    line = line.rstrip("\n\r")
                    if not line.strip() or line.strip().startswith("\\"):
                        continue

                    pct = (i + 1) * 100 // total_lines
                    print(f"\r  [{pct:3d}%] {loaded} lines loaded...", end="", flush=True)

                    try:
                        session.send_repl(line, timeout_s=args.timeout)
                        loaded += 1
                    except SerialError as e:
                        print(f"\nError loading firmware: {e}", file=sys.stderr)
                        print("Aborting restore (no changes persisted).", file=sys.stderr)
                        return 1

                print(f"\r  [100%] {loaded} lines loaded.    ")

                # Step 3: Enter protocol mode
                transcript.record_comment("Entering protocol mode...")
                print("Entering protocol mode...")
                session.drain(0.2)  # Clear any buffered output from firmware load
                session.send_line("revive")
                result = session.read_until(b" ok", args.timeout)
                if not result.found:
                    # Warn but continue - protocol commands will fail if not actually in protocol mode
                    print("Warning: revive did not return ok", file=sys.stderr)
                session.drain(0.3)

                # Step 4: Apply meta set commands
                if snapshot.meta:
                    transcript.record_comment("Applying meta settings...")
                    print(f"Applying {len(snapshot.meta)} meta settings...")

                    for key, value in snapshot.meta.items():
                        cmd = f"meta {key} {value}"
                        transcript.record_sent(cmd)
                        response = session.send_protocol(cmd, timeout_s=args.timeout)
                        transcript.record_received(response)

                        has_error, error_msg = is_error(response)
                        if has_error:
                            print(f"\nError setting meta {key}: {error_msg}", file=sys.stderr)
                            print("Aborting restore (no changes persisted).", file=sys.stderr)
                            return 1

                # Step 5: Apply define commands
                if snapshot.defs:
                    transcript.record_comment("Applying definitions...")
                    print(f"Applying {len(snapshot.defs)} definitions...")

                    for defn in snapshot.defs:
                        # Ensure it starts with "define"
                        if not defn.startswith("define"):
                            defn = f"define {defn}"

                        transcript.record_sent(defn)
                        response = session.send_protocol(defn, timeout_s=args.timeout)
                        transcript.record_received(response)

                        has_error, error_msg = is_error(response)
                        if has_error:
                            name = extract_def_name(defn) or defn[:40]
                            print(f"\nError defining {name}: {error_msg}", file=sys.stderr)
                            print("Aborting restore (no changes persisted).", file=sys.stderr)
                            return 1

                # Step 6: Validate
                transcript.record_comment("Validating...")
                print("Validating...")
                transcript.record_sent("validate")
                response = session.send_protocol("validate", timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Validation failed: {error_msg}", file=sys.stderr)
                    print("Aborting restore (no changes persisted).", file=sys.stderr)
                    return 1

                if "! ok" not in response:
                    print(f"Unexpected validation response: {response}", file=sys.stderr)
                    return 1

                print("Validation passed.")

                # Step 7: safe-save
                transcript.record_comment("Persisting with safe-save...")
                print("Running safe-save...")
                transcript.record_sent("safe-save")
                response = session.send_protocol("safe-save", timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"safe-save failed: {error_msg}", file=sys.stderr)
                    return 1

                print("Saved to flash.")

                # Step 8: restart
                transcript.record_comment("Restarting...")
                print("Restarting...")
                transcript.record_sent("restart")
                response = session.send_protocol("restart", timeout_s=args.timeout)
                transcript.record_received(response)
                print("Device restarting...")

                # Close session before re-probe
                port = session.port

        # Step 9: Re-probe to verify
        print("Waiting for device to boot...")
        time.sleep(2)  # Give device time to restart

        with SerialSession.open(
            port=port,
            baud=args.baud,
            settle_s=5.0,  # Full settle for autoexec
        ) as session2:
            transcript.record_comment("Re-probing after restart...")
            result = probe(session2, timeout_s=args.timeout)
            print("\nRestore complete. Final state:")
            print(f"  Node ID: {result.node_id or 'unknown'}")
            print(f"  Role: {result.role or 'unknown'}")
            print(f"  Mode: {result.mode}")
            print(f"  Codignity loaded: {result.codignity_loaded}")

        return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_snapshot_diff(args: argparse.Namespace) -> int:
    """Handle the `snapshot diff` subcommand."""
    # Load snapshot file first
    snap_path = Path(args.input)
    if not snap_path.exists():
        print(f"Error: Snapshot file not found: {snap_path}", file=sys.stderr)
        return 1

    try:
        snapshot = Snapshot.load(snap_path)
    except ValueError as e:
        print(f"Error parsing snapshot: {e}", file=sys.stderr)
        return 1

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

                # Get live meta
                transcript.record_sent("meta")
                response = session.send_protocol("meta", timeout_s=args.timeout)
                transcript.record_received(response)
                live_meta = parse_meta_dump(response)

                # Get live defs (from source command)
                transcript.record_sent("source")
                response = session.send_protocol("source", timeout_s=args.timeout)
                transcript.record_received(response)

                # Parse define names from source output
                # Format is "! : name  body ;" for each definition
                live_defs_all: list[str] = []
                for line in response.splitlines():
                    line = line.strip()
                    if line.startswith("! : "):
                        # Format: "! : <name>  <body>"
                        rest = line[4:].strip()
                        # Name is the first token
                        parts = rest.split(None, 1)
                        if parts:
                            live_defs_all.append(parts[0])

                # Diff noise suppression:
                # - "Core firmware" means Codignity's shipped words (derived from local `firmware/esp32/codignity.fs`),
                #   not ESP32forth kernel words.
                # - This keeps `snapshot diff` focused on user-defined words.
                repo_root = _this_dir.parent.parent
                firmware_path = repo_root / "firmware" / "esp32" / "codignity.fs"
                baseline_defs = load_baseline_defs(firmware_path)

                if baseline_defs:
                    live_defs = [d for d in live_defs_all if d not in baseline_defs]
                else:
                    # Could not load baseline - skip live-only defs section
                    print("Warning: Could not load firmware baseline; skipping live-only defs.")
                    live_defs = []

                # Compute diff
                diff = compute_diff(snapshot, live_meta, live_defs)

                print(f"Comparing snapshot ({snap_path.name}) vs live node:")
                print(f"  Snapshot: {snapshot.node_id or 'unknown'} @ {snapshot.date}")
                if baseline_defs:
                    print(f"  Baseline: {len(baseline_defs)} core defs filtered")
                print()
                print(format_diff(diff))

                return 0 if not diff.has_differences else 1

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


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

    # load
    p_load = subparsers.add_parser("load", help="Load Codignity firmware onto device")
    add_common_args(p_load)
    p_load.add_argument(
        "--file",
        type=Path,
        help="Firmware file path (default: firmware/esp32/codignity.fs)",
    )
    p_load.add_argument(
        "--persist",
        action="store_true",
        help="Run safe-save and restart after loading",
    )
    p_load.add_argument(
        "--no-mute",
        action="store_true",
        help="Show all output (normally muted for cleaner progress)",
    )
    p_load.set_defaults(func=cmd_load)

    # snapshot (with subcommands: create, restore, diff)
    p_snapshot = subparsers.add_parser("snapshot", help="Snapshot/restore node state")
    snapshot_sub = p_snapshot.add_subparsers(dest="snapshot_cmd", required=True)

    # snapshot create
    p_snap_create = snapshot_sub.add_parser("create", help="Create snapshot of node state")
    add_common_args(p_snap_create)
    p_snap_create.add_argument(
        "--out", "-o",
        required=True,
        help="Output snapshot file path (.cdsnap)",
    )
    p_snap_create.add_argument(
        "--defs",
        help="File containing define commands to include",
    )
    p_snap_create.add_argument(
        "--save-first",
        action="store_true",
        help="Run safe-save before creating snapshot",
    )
    p_snap_create.set_defaults(func=cmd_snapshot_create)

    # snapshot restore
    p_snap_restore = snapshot_sub.add_parser("restore", help="Restore node from snapshot")
    add_common_args(p_snap_restore)
    p_snap_restore.add_argument(
        "--in", "-i",
        dest="input",
        required=True,
        help="Snapshot file to restore from",
    )
    p_snap_restore.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    p_snap_restore.set_defaults(func=cmd_snapshot_restore)

    # snapshot diff
    p_snap_diff = snapshot_sub.add_parser("diff", help="Compare live node vs snapshot")
    add_common_args(p_snap_diff)
    p_snap_diff.add_argument(
        "--in", "-i",
        dest="input",
        required=True,
        help="Snapshot file to compare against",
    )
    p_snap_diff.set_defaults(func=cmd_snapshot_diff)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
