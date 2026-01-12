#!/usr/bin/env python3

import argparse
import glob
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    import serial  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: pyserial\n"
        "Install: python3 -m pip install -r tools/terminal/requirements.txt"
    ) from exc


def _autodetect_port() -> str:
    patterns = [
        "/dev/cu.usbserial-*",
        "/dev/tty.usbserial-*",
        "/dev/cu.SLAB_USBtoUART*",
        "/dev/tty.SLAB_USBtoUART*",
        "/dev/cu.wchusbserial*",
        "/dev/tty.wchusbserial*",
        "/dev/cu.usbmodem*",
        "/dev/tty.usbmodem*",
    ]
    ports: list[str] = []
    for pattern in patterns:
        ports.extend(glob.glob(pattern))
    ports = sorted(set(ports))

    if not ports:
        raise SystemExit(
            "No serial ports detected.\n"
            "Pass --port explicitly (e.g. /dev/cu.usbserial-0001)."
        )
    if len(ports) > 1:
        raise SystemExit(
            "Multiple serial ports detected; pass --port explicitly:\n"
            + "\n".join(f"- {p}" for p in ports)
        )
    return ports[0]


def _read_until(
    ser: serial.Serial, marker: bytes, timeout_s: float
) -> tuple[bytes, bool]:
    deadline = time.time() + timeout_s
    buf = bytearray()
    while time.time() < deadline:
        chunk = ser.read(1024)
        if chunk:
            buf.extend(chunk)
            if marker in buf:
                pos = buf.find(marker)
                end = pos + len(marker)
                if buf[end : end + 2] == b"\r\n":
                    end += 2
                return bytes(buf[:end]), True
            continue
        time.sleep(0.01)
    return bytes(buf), False


def _looks_fatal(buf: bytes) -> bool:
    return b"Guru Meditation Error" in buf or b"ERROR:" in buf


@dataclass(frozen=True)
class Until:
    name: str
    marker: bytes


def _until_arg(value: str) -> Until:
    if value == "prompt":
        return Until("prompt", b"--> ")
    if value == "end":
        return Until("end", b"! end")
    if value == "ok":
        return Until("ok", b" ok\r\n")
    return Until("custom", value.encode("utf-8"))


def _send_line(ser: serial.Serial, line: str) -> None:
    ser.write(line.encode("utf-8") + b"\r\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Send lines to an ESP32forth console over serial and print the response."
    )
    parser.add_argument("--port", help="Serial port path (auto-detects if omitted).")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200).")
    parser.add_argument(
        "--until",
        type=_until_arg,
        default=_until_arg("prompt"),
        help="Read-until marker: prompt | end | ok | <custom string> (default: prompt).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Read timeout per command, seconds (default: 2.0).",
    )
    parser.add_argument(
        "--settle",
        type=float,
        default=4.0,
        help="Seconds to wait after opening the port (default: 4.0).",
    )
    parser.add_argument(
        "--esp32-reset",
        action="store_true",
        help="Toggle DTR/RTS to reset an ESP32 DevKit (use if the port-open leaves the board unresponsive).",
    )
    parser.add_argument(
        "--preline",
        help="Optional line to send once after opening the port (useful to exit protocol mode via 'repl').",
    )
    parser.add_argument(
        "--echo-sent",
        action="store_true",
        help="Echo sent lines to stdout prefixed with '> ' (useful for transcripts).",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--line", help="Send a single line (wraps with CRLF).")
    group.add_argument("--file", help="Send a file line-by-line.")
    args = parser.parse_args(argv)

    port = args.port or _autodetect_port()
    until: Until = args.until

    ser = serial.Serial(port, baudrate=args.baud, timeout=0.1, rtscts=False, dsrdtr=False)
    try:
        # Avoid accidental ESP32 auto-reset on port open (best-effort).
        # (When reset is explicitly requested, do not interfere.)
        if not args.esp32_reset:
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass
        time.sleep(args.settle)
        if args.esp32_reset:
            # Best-effort reset sequence for common ESP32 DevKit auto-reset circuits.
            for dtr, rts in [(False, False), (True, True), (True, False), (False, True)]:
                ser.dtr = dtr
                ser.rts = rts
                time.sleep(0.2)
            ser.rts = True
            time.sleep(0.15)
            ser.rts = False
            time.sleep(0.5)
        ser.reset_input_buffer()

        # Synchronize only when expecting an interactive prompt.
        if until.name == "prompt":
            # Avoid sending a blank line: some Forth consoles repeat the last command on empty input.
            _send_line(ser, "sp0 sp!")
            buf, found = _read_until(ser, until.marker, args.timeout)
            if _looks_fatal(buf):
                print("Device reported ERROR/Guru while syncing prompt; aborting.", file=sys.stderr)
                return 2
            if not found and args.preline:
                _send_line(ser, args.preline)
                buf, found = _read_until(ser, until.marker, args.timeout)
                if _looks_fatal(buf):
                    print("Device reported ERROR/Guru while running --preline; aborting.", file=sys.stderr)
                    return 2
                if not found:
                    print(
                        f"Timed out waiting for prompt marker after --preline: {until.marker!r}",
                        file=sys.stderr,
                    )
                    return 2
            if not found:
                print(f"Timed out waiting for prompt marker: {until.marker!r}", file=sys.stderr)
                return 2
            ser.reset_input_buffer()

        if args.line is not None:
            ser.reset_input_buffer()
            _send_line(ser, args.line)
            buf, found = _read_until(ser, until.marker, args.timeout)
            sys.stdout.buffer.write(buf)
            if _looks_fatal(buf):
                print("Device reported ERROR/Guru; aborting.", file=sys.stderr)
                return 2
            if not found:
                print(
                    f"Timed out waiting for marker: {until.marker!r}",
                    file=sys.stderr,
                )
                return 2
            return 0

        def open_text_file(path: str) -> tuple[str, object]:
            handle = open(path, "r", encoding="utf-8")
            return path, handle

        def resolve_include(current_path: str, include_arg: str) -> str:
            raw = Path(include_arg)
            if raw.is_absolute():
                return str(raw)
            candidate = (Path(current_path).parent / raw).resolve()
            if candidate.exists():
                return str(candidate)
            return str(raw)

        file_stack: list[tuple[str, object, int]] = []
        top_path, top_handle = open_text_file(args.file)
        file_stack.append((top_path, top_handle, 0))

        current_until = until
        echo_sent = bool(args.echo_sent)
        mute_output = False

        while file_stack:
            current_path, handle, line_no = file_stack[-1]
            raw = handle.readline()
            if raw == "":
                handle.close()
                file_stack.pop()
                continue
            line_no += 1
            file_stack[-1] = (current_path, handle, line_no)
            line = raw.rstrip("\n")
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                parts = stripped[1:].strip().split()
                if not parts:
                    continue
                cmd = parts[0].lower()
                if cmd == "sleep" and len(parts) >= 2:
                    try:
                        time.sleep(float(parts[1]))
                    except ValueError:
                        print(
                            f"Invalid #sleep value in {current_path}:{line_no}: {parts[1]!r}",
                            file=sys.stderr,
                        )
                        return 2
                    continue
                if cmd == "until" and len(parts) >= 2:
                    current_until = _until_arg(parts[1])
                    continue
                if cmd == "echo" and len(parts) >= 2:
                    val = parts[1].lower()
                    if val in {"1", "true", "on", "yes"}:
                        echo_sent = True
                        continue
                    if val in {"0", "false", "off", "no"}:
                        echo_sent = False
                        continue
                    print(
                        f"Invalid #echo value in {current_path}:{line_no}: {parts[1]!r}",
                        file=sys.stderr,
                    )
                    return 2
                if cmd == "mute" and len(parts) >= 2:
                    val = parts[1].lower()
                    if val in {"1", "true", "on", "yes"}:
                        mute_output = True
                        continue
                    if val in {"0", "false", "off", "no"}:
                        mute_output = False
                        continue
                    print(
                        f"Invalid #mute value in {current_path}:{line_no}: {parts[1]!r}",
                        file=sys.stderr,
                    )
                    return 2
                if cmd == "include" and len(parts) >= 2:
                    include_path = resolve_include(current_path, parts[1])
                    try:
                        inc_path, inc_handle = open_text_file(include_path)
                    except OSError as exc:
                        print(
                            f"Failed to open #include target {include_path!r} from {current_path}:{line_no}: {exc}",
                            file=sys.stderr,
                        )
                        return 2
                    file_stack.append((inc_path, inc_handle, 0))
                    continue
                continue

            ser.reset_input_buffer()
            if echo_sent and not mute_output:
                print(f"> {line}", flush=True)
            _send_line(ser, line)
            buf, found = _read_until(ser, current_until.marker, args.timeout)
            if not mute_output:
                sys.stdout.buffer.write(buf)
            if _looks_fatal(buf):
                print(
                    f"Device reported ERROR/Guru while sending {current_path}:{line_no}",
                    file=sys.stderr,
                )
                print(f"Line: {line!r}", file=sys.stderr)
                return 2
            if not found:
                print(
                    f"Timed out waiting for marker while sending {current_path}:{line_no}: {current_until.marker!r}",
                    file=sys.stderr,
                )
                print(f"Line: {line!r}", file=sys.stderr)
                return 2
        return 0
    finally:
        try:
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass
        ser.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
