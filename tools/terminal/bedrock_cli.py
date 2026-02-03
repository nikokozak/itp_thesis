#!/usr/bin/env python3
"""Bedrock CLI - Command-line interface for Bedrock Protocol nodes.

Run from repo root:
    .venv/bin/python tools/terminal/bedrock_cli.py <subcommand> [options]

Examples:
    bedrock_cli.py probe
    bedrock_cli.py send "?"
    bedrock_cli.py meta dump
    bedrock_cli.py define ": foo 123 ;"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

# Ensure the bedrock package is importable when run from repo root
_this_dir = Path(__file__).parent
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from bedrock.session import SerialSession, SerialError
from bedrock.protocol import (
    probe,
    ProbeResult,
    ensure_protocol,
    ensure_repl,
    parse_meta_dump,
    is_error,
)
from bedrock.transcript import Transcript, NullTranscript
from bedrock.snapshot import (
    Snapshot,
    SnapshotDiff,
    compute_diff,
    format_diff,
    extract_def_name,
    load_baseline_defs,
)
from bedrock.defs_log import (
    append_define,
    load_defs,
    load_defs_from_file,
    merge_defs,
)
from bedrock.pins import (
    PinState,
    parse_pins_response,
    parse_pin_kv,
    parse_pin_value_response,
)
from bedrock.boards import get_manifest, list_boards, BoardManifest

if TYPE_CHECKING:
    from bedrock.transcript import Transcript as TranscriptType


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
    print(f"Bedrock loaded: {result.bedrock_loaded}")
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
                        "Is Bedrock loaded? Try `probe` first.",
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
                        "Is Bedrock loaded? Try `probe` first.",
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
                        "Is Bedrock loaded? Try `probe` first.",
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
    """Handle the `load` subcommand - load Bedrock firmware."""
    # Resolve firmware path relative to repo root
    if args.file:
        firmware_path = Path(args.file)
    else:
        # Default: firmware/esp32/bedrock.fs relative to repo root
        repo_root = _this_dir.parent.parent
        firmware_path = repo_root / "firmware" / "esp32" / "bedrock.fs"

    if not firmware_path.exists():
        print(f"Error: Firmware file not found: {firmware_path}", file=sys.stderr)
        return 1

    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                # Step 1: Ensure REPL mode before line-by-line load.
                transcript.record_comment("Entering REPL mode...")
                print("Entering REPL mode...")
                if not ensure_repl(session, timeout_s=args.timeout):
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

                # Step 3: Validate (still in REPL after loading the file).
                # Note: calling `revive` here would restore the previously saved image,
                # discarding the newly loaded definitions.
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

                # Step 4: Persist if requested
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
                        "Is Bedrock loaded? Try `probe` first.",
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
                    print(f"  Loaded {len(base_defs)} defs from .bedrock/defs/{node_id}.defs")

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
        print("  1. Load Bedrock firmware (interrupts autoexec)")
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
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                # Step 1: Ensure REPL mode before applying restore steps.
                transcript.record_comment("Entering REPL mode...")
                print("Entering REPL mode...")
                if not ensure_repl(session, timeout_s=args.timeout):
                    print(
                        "Error: Could not enter REPL mode.\n"
                        "Try: Hold SAFE + press EN to stay in REPL.",
                        file=sys.stderr,
                    )
                    return 1

                session.drain(0.2)

                # Step 2: Load Bedrock firmware
                repo_root = _this_dir.parent.parent
                firmware_path = repo_root / "firmware" / "esp32" / "bedrock.fs"

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

                # Step 3: Apply meta set commands (still in REPL after loading the file).
                # Note: calling `revive` here would restore the previously saved image,
                # discarding the newly loaded definitions.
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
            print(f"  Bedrock loaded: {result.bedrock_loaded}")

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
                        "Is Bedrock loaded? Try `probe` first.",
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
                # - "Core firmware" means Bedrock's shipped words (derived from local `firmware/esp32/bedrock.fs`),
                #   not ESP32forth kernel words.
                # - This keeps `snapshot diff` focused on user-defined words.
                repo_root = _this_dir.parent.parent
                firmware_path = repo_root / "firmware" / "esp32" / "bedrock.fs"
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


def render_pin_footprint(
    board: BoardManifest,
    pins: dict[int, PinState],
    selected_gpio: int | None = None,
) -> str:
    """Render a board footprint view with pin states.

    Args:
        board: The board manifest with physical layout.
        pins: GPIO -> PinState mapping from device.
        selected_gpio: Optional GPIO to highlight.

    Returns:
        ASCII rendering of the board footprint.
    """
    left = board.left_column()
    right = board.right_column()
    rows = max(len(left), len(right))

    lines = []
    lines.append(f"  {board.display_name}")
    lines.append("  " + "=" * 50)
    lines.append("")

    # Header
    lines.append("  Left                                        Right")
    lines.append("  " + "-" * 22 + "    " + "-" * 22)

    for i in range(rows):
        left_pin = left[i] if i < len(left) else None
        right_pin = right[i] if i < len(right) else None

        left_str = _format_pin_cell(left_pin, pins, selected_gpio)
        right_str = _format_pin_cell(right_pin, pins, selected_gpio)

        lines.append(f"  {left_str}    {right_str}")

    lines.append("")
    lines.append("  Legend: [L]=level [M]=mode [O]=owner  X=flash  !=strapping  I=input-only  S=safe")
    return "\n".join(lines)


def _format_pin_cell(
    pin_def: "PinDef | None",
    pins: dict[int, PinState],
    selected_gpio: int | None,
) -> str:
    """Format a single pin cell for footprint display."""
    from bedrock.boards import PinDef

    if pin_def is None:
        return " " * 22

    # Base label
    label = pin_def.label.ljust(4)

    # For non-GPIO pins (power, ground, control)
    if pin_def.gpio is None:
        kind_marker = {"power": "+", "gnd": "-", "control": "~"}.get(pin_def.kind, " ")
        return f"{label} {kind_marker}                  "

    gpio = pin_def.gpio
    state = pins.get(gpio)

    # Highlight marker
    marker = ">" if gpio == selected_gpio else " "

    if state is None:
        return f"{marker}{label} (gpio{gpio:02d})  ?        "

    # Level
    if state.level is not None:
        level_str = str(state.level)
    else:
        level_str = "-"

    # Mode (abbreviated)
    mode_abbr = {
        "unknown": "?",
        "in": "I",
        "out": "O",
        "adc": "A",
        "i2c": "2",
        "uart": "U",
        "pwm": "P",
        "reserved": "R",
    }.get(state.mode, "?")

    # Owner (truncated)
    owner = state.owner[:6] if state.owner else "-"

    # Warning flags
    warn = ""
    if state.is_flash():
        warn = "X"
    elif state.is_strapping():
        warn = "!"
    elif state.is_input_only():
        warn = "I"
    elif state.is_safe():
        warn = "S"

    return f"{marker}{label} G{gpio:02d} L{level_str} M{mode_abbr} O{owner.ljust(6)}{warn}"


def cmd_pins(args: argparse.Namespace) -> int:
    """Handle the `pins` subcommand - show pin footprint view."""
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
                        "Is Bedrock loaded? Try `probe` first.",
                        file=sys.stderr,
                    )
                    return 1

                # Get pins dump
                transcript.record_sent("pins")
                response = session.send_protocol("pins", timeout_s=args.timeout)
                transcript.record_received(response)

                board_id, pins = parse_pins_response(response)

                if args.json:
                    output = {
                        "board": board_id,
                        "pins": {
                            gpio: {
                                "gpio": state.gpio,
                                "mode": state.mode,
                                "level": state.level,
                                "pull": state.pull,
                                "owner": state.owner,
                                "flags": list(state.flags),
                            }
                            for gpio, state in pins.items()
                        },
                    }
                    print(json.dumps(output, indent=2))
                    return 0

                # Try to get board manifest
                board = None
                if board_id:
                    board = get_manifest(board_id)
                    if board is None:
                        print(f"Warning: Unknown board '{board_id}'", file=sys.stderr)

                if board:
                    # Render footprint view
                    print(render_pin_footprint(board, pins))
                else:
                    # Fallback: simple list
                    print("Pin states (no board manifest):")
                    print("-" * 60)
                    for gpio in sorted(pins.keys()):
                        state = pins[gpio]
                        level = state.level if state.level is not None else "-"
                        owner = state.owner or "-"
                        flags = ",".join(state.flags) if state.flags else "-"
                        print(
                            f"  GPIO{gpio:02d}: mode={state.mode:8s} "
                            f"level={level} pull={state.pull:4s} "
                            f"owner={owner:8s} flags={flags}"
                        )

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_status(args: argparse.Namespace) -> int:
    """Handle the `pin status` subcommand."""
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
                        "Is Bedrock loaded? Try `probe` first.",
                        file=sys.stderr,
                    )
                    return 1

                cmd = f"pin-status {args.pin}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                # Parse the pin state
                for line in response.splitlines():
                    state = parse_pin_kv(line)
                    if state:
                        if args.json:
                            output = {
                                "gpio": state.gpio,
                                "mode": state.mode,
                                "level": state.level,
                                "pull": state.pull,
                                "owner": state.owner,
                                "flags": list(state.flags),
                            }
                            print(json.dumps(output, indent=2))
                        else:
                            level = state.level if state.level is not None else "-"
                            owner = state.owner or "-"
                            flags = ",".join(state.flags) if state.flags else "-"
                            print(f"GPIO{state.gpio}:")
                            print(f"  Mode:  {state.mode}")
                            print(f"  Level: {level}")
                            print(f"  Pull:  {state.pull}")
                            print(f"  Owner: {owner}")
                            print(f"  Flags: {flags}")
                        return 0

                print("Error: No pin state in response", file=sys.stderr)
                return 1

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_claim(args: argparse.Namespace) -> int:
    """Handle the `pin claim` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                cmd = f"pin-claim {args.pin} {args.owner}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    if error_msg == "pin_owned":
                        print("Hint: Pin is already owned by another owner.", file=sys.stderr)
                    return 1

                print(f"Claimed {args.pin} for '{args.owner}'")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_release(args: argparse.Namespace) -> int:
    """Handle the `pin release` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                cmd = f"pin-release {args.pin}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                print(f"Released {args.pin}")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_read(args: argparse.Namespace) -> int:
    """Handle the `pin read` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                cmd = f"pin-read {args.pin}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                value = parse_pin_value_response(response)
                if value is not None:
                    print(value)
                else:
                    print("Error: Could not parse value from response", file=sys.stderr)
                    return 1

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_trace(args: argparse.Namespace) -> int:
    """Handle the `pin trace` subcommand.

    Captures a time series by repeatedly calling `pin-read` and storing samples
    on the host (not the MCU).
    """
    try:
        seconds = float(args.seconds)
        hz = float(args.hz)
    except (TypeError, ValueError):
        print("Error: seconds and hz must be numeric", file=sys.stderr)
        return 1

    if seconds <= 0:
        print("Error: seconds must be > 0", file=sys.stderr)
        return 1
    if hz <= 0:
        print("Error: hz must be > 0", file=sys.stderr)
        return 1

    interval_s = 1.0 / hz

    # Resolve output path
    if args.out:
        out_path = Path(args.out)
    else:
        repo_root = _this_dir.parent.parent
        out_dir = repo_root / ".bedrock" / "traces"
        stamp = time.strftime("%Y%m%d-%H%M%S")
        pin_label = str(args.pin).replace("/", "_")
        out_path = out_dir / f"pin-{pin_label}-{stamp}.csv"

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Error: Could not create output directory: {exc}", file=sys.stderr)
        return 1

    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                # Optional one-shot pin config before capture.
                if args.mode or args.pull:
                    mode = args.mode or "in"
                    cmd = f"pin-mode {args.pin} {mode}"
                    if args.pull:
                        cmd += f" pull={args.pull}"
                    transcript.record_sent(cmd)
                    response = session.send_protocol(cmd, timeout_s=args.timeout)
                    transcript.record_received(response)
                    has_error, error_msg = is_error(response)
                    if has_error:
                        print(f"Error: {error_msg}", file=sys.stderr)
                        return 1

                # Validate pin + get canonical gpio number.
                cmd = f"pin-status {args.pin}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)
                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                pin_state = None
                for line in response.splitlines():
                    state = parse_pin_kv(line.strip())
                    if state:
                        pin_state = state
                        break

                if pin_state is None:
                    print("Error: Could not parse pin-status response", file=sys.stderr)
                    return 1
                if pin_state.is_flash():
                    print("Error: Pin is marked as flash; refusing to sample.", file=sys.stderr)
                    return 1

                # Capture loop
                transcript.record_comment(
                    f"Tracing pin {args.pin} for {seconds}s at target {hz}Hz -> {out_path}"
                )
                print(f"Tracing {args.pin} for {seconds}s at {hz}Hz")
                print(f"Writing {out_path}")

                start = time.perf_counter()
                deadline = start + seconds
                next_tick = start
                last_report = start

                samples: list[tuple[float, int]] = []

                while True:
                    now = time.perf_counter()
                    if now >= deadline:
                        break

                    if now < next_tick:
                        time.sleep(min(0.01, next_tick - now))
                        continue

                    resp = session.send_protocol(f"pin-read {args.pin}", timeout_s=args.timeout)
                    value = parse_pin_value_response(resp)
                    if value is None:
                        # Represent parse failures as -1.
                        value = -1

                    t_s = time.perf_counter() - start
                    samples.append((t_s, int(value)))

                    next_tick += interval_s
                    if next_tick < now - interval_s:
                        # If we fell behind, resync to avoid spiraling.
                        next_tick = now + interval_s

                    if not args.quiet and (now - last_report) >= 0.25:
                        last_report = now
                        pct = int(min(100.0, (now - start) * 100.0 / seconds))
                        print(f"\r  [{pct:3d}%] {len(samples)} samples", end="", flush=True)

                if not args.quiet:
                    print(f"\r  [100%] {len(samples)} samples")

                # Write CSV
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("# Bedrock pin trace\n")
                    f.write(f"# port: {session.port}\n")
                    f.write(f"# pin: {args.pin} (gpio {pin_state.gpio})\n")
                    f.write(f"# seconds: {seconds}\n")
                    f.write(f"# target_hz: {hz}\n")
                    f.write("t_s,value\n")
                    for t_s, v in samples:
                        f.write(f"{t_s:.6f},{v}\n")

                elapsed = max(1e-6, time.perf_counter() - start)
                eff_hz = len(samples) / elapsed
                print(f"Done: {len(samples)} samples in {elapsed:.2f}s ({eff_hz:.1f}Hz effective)")

                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1


def cmd_pin_write(args: argparse.Namespace) -> int:
    """Handle the `pin write` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                cmd = f"pin-write {args.pin} {args.value}"
                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                print(f"Wrote {args.value} to {args.pin}")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_pin_mode(args: argparse.Namespace) -> int:
    """Handle the `pin mode` subcommand."""
    try:
        with SerialSession.open(
            port=args.port,
            baud=args.baud,
            settle_s=args.settle,
        ) as session:
            with get_transcript(args, session.port) as transcript:
                if not ensure_protocol(session, timeout_s=args.timeout):
                    print("Error: Could not enter protocol mode.", file=sys.stderr)
                    return 1

                cmd = f"pin-mode {args.pin} {args.mode}"
                if args.pull:
                    cmd += f" pull={args.pull}"

                transcript.record_sent(cmd)
                response = session.send_protocol(cmd, timeout_s=args.timeout)
                transcript.record_received(response)

                has_error, error_msg = is_error(response)
                if has_error:
                    print(f"Error: {error_msg}", file=sys.stderr)
                    return 1

                pull_str = f" with pull={args.pull}" if args.pull else ""
                print(f"Set {args.pin} to {args.mode}{pull_str}")
                return 0

    except SerialError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ---- Main ----


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bedrock CLI - Command-line interface for Bedrock nodes.",
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
    p_load = subparsers.add_parser("load", help="Load Bedrock firmware onto device")
    add_common_args(p_load)
    p_load.add_argument(
        "--file",
        type=Path,
        help="Firmware file path (default: firmware/esp32/bedrock.fs)",
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
        help="Output snapshot file path (.brsnap)",
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

    # pins (show footprint view)
    p_pins = subparsers.add_parser("pins", help="Show pin states in board footprint view")
    add_common_args(p_pins)
    p_pins.add_argument("--json", action="store_true", help="Output as JSON")
    p_pins.set_defaults(func=cmd_pins)

    # pin (with subcommands: status, claim, release, read, write, mode)
    p_pin = subparsers.add_parser("pin", help="Single pin operations")
    pin_sub = p_pin.add_subparsers(dest="pin_cmd", required=True)

    # pin status
    p_pin_status = pin_sub.add_parser("status", help="Get single pin status")
    add_common_args(p_pin_status)
    p_pin_status.add_argument("pin", help="Pin identifier (e.g., D4, GPIO4, 4)")
    p_pin_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_pin_status.set_defaults(func=cmd_pin_status)

    # pin claim
    p_pin_claim = pin_sub.add_parser("claim", help="Claim a pin for an owner")
    add_common_args(p_pin_claim)
    p_pin_claim.add_argument("pin", help="Pin identifier")
    p_pin_claim.add_argument("owner", help="Owner label (e.g., button, led, sensor)")
    p_pin_claim.set_defaults(func=cmd_pin_claim)

    # pin release
    p_pin_release = pin_sub.add_parser("release", help="Release pin ownership")
    add_common_args(p_pin_release)
    p_pin_release.add_argument("pin", help="Pin identifier")
    p_pin_release.set_defaults(func=cmd_pin_release)

    # pin read
    p_pin_read = pin_sub.add_parser("read", help="Read pin level")
    add_common_args(p_pin_read)
    p_pin_read.add_argument("pin", help="Pin identifier")
    p_pin_read.set_defaults(func=cmd_pin_read)

    # pin trace
    p_pin_trace = pin_sub.add_parser("trace", help="Capture a host-side time series from pin-read")
    add_common_args(p_pin_trace)
    p_pin_trace.add_argument("pin", help="Pin identifier")
    p_pin_trace.add_argument(
        "--seconds",
        type=float,
        default=1.0,
        help="Capture duration in seconds (default: 1.0).",
    )
    p_pin_trace.add_argument(
        "--hz",
        type=float,
        default=50.0,
        help="Target sample rate in Hz (best-effort; default: 50).",
    )
    p_pin_trace.add_argument(
        "--out",
        type=Path,
        help="Output CSV path (default: .bedrock/traces/pin-<pin>-<timestamp>.csv).",
    )
    p_pin_trace.add_argument(
        "--mode",
        choices=["in", "out"],
        help="Optional pin mode to set before tracing.",
    )
    p_pin_trace.add_argument(
        "--pull",
        choices=["up", "down", "none"],
        help="Optional pull resistor config (implies --mode in if --mode omitted).",
    )
    p_pin_trace.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    p_pin_trace.set_defaults(func=cmd_pin_trace)

    # pin write
    p_pin_write = pin_sub.add_parser("write", help="Write pin level")
    add_common_args(p_pin_write)
    p_pin_write.add_argument("pin", help="Pin identifier")
    p_pin_write.add_argument("value", choices=["0", "1"], help="Value to write (0 or 1)")
    p_pin_write.set_defaults(func=cmd_pin_write)

    # pin mode
    p_pin_mode = pin_sub.add_parser("mode", help="Set pin mode")
    add_common_args(p_pin_mode)
    p_pin_mode.add_argument("pin", help="Pin identifier")
    p_pin_mode.add_argument("mode", choices=["in", "out"], help="Mode (in or out)")
    p_pin_mode.add_argument(
        "--pull",
        choices=["up", "down", "none"],
        help="Pull resistor configuration",
    )
    p_pin_mode.set_defaults(func=cmd_pin_mode)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
