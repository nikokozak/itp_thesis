#!/usr/bin/env python3

import argparse
import glob
import sys
import time
from dataclasses import dataclass

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
                return bytes(buf), True
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
        help="Read-until marker: prompt | end | <custom string> (default: prompt).",
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
        default=0.7,
        help="Seconds to wait after opening the port (default: 0.7).",
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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--line", help="Send a single line (wraps with CRLF).")
    group.add_argument("--file", help="Send a file line-by-line.")
    args = parser.parse_args(argv)

    port = args.port or _autodetect_port()
    until: Until = args.until

    ser = serial.Serial(port, baudrate=args.baud, timeout=0.1)
    try:
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

        with open(args.file, "r", encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, start=1):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                ser.reset_input_buffer()
                _send_line(ser, line)
                buf, found = _read_until(ser, until.marker, args.timeout)
                sys.stdout.buffer.write(buf)
                if _looks_fatal(buf):
                    print(
                        f"Device reported ERROR/Guru while sending {args.file}:{line_no}",
                        file=sys.stderr,
                    )
                    print(f"Line: {line!r}", file=sys.stderr)
                    return 2
                if not found:
                    print(
                        f"Timed out waiting for marker while sending {args.file}:{line_no}: {until.marker!r}",
                        file=sys.stderr,
                    )
                    print(f"Line: {line!r}", file=sys.stderr)
                    return 2
        return 0
    finally:
        ser.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
