"""Serial session management for Bedrock nodes.

This module provides the SerialSession class for communicating with ESP32forth
devices running Bedrock firmware. It handles the quirks of ESP32 serial:
- Port-open reset behavior
- Quiet settle period to avoid interrupting autoexec
- DTR/RTS line management
"""

from __future__ import annotations

import glob
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import serial as serial_module


# Markers for response detection
MARKER_END = b"! end"
MARKER_OK = b" ok\r\n"
MARKER_PROMPT = b"--> "


@dataclass(frozen=True)
class ReadResult:
    """Result of a read_until operation."""

    data: bytes
    found: bool

    @property
    def text(self) -> str:
        """Decode data as UTF-8, replacing errors."""
        return self.data.decode("utf-8", errors="replace")


class SerialError(Exception):
    """Base exception for serial communication errors."""


class SerialTimeoutError(SerialError):
    """Read operation timed out waiting for marker."""


class DeviceError(SerialError):
    """Device reported a fatal error (Guru Meditation, etc.)."""


def autodetect_port() -> str:
    """Auto-detect a single USB serial port.

    Returns:
        The detected port path.

    Raises:
        SerialError: If no ports or multiple ports are found.
    """
    ports = list_candidate_ports()

    if not ports:
        raise SerialError(
            "No serial ports detected.\n"
            "Pass --port explicitly (e.g. /dev/cu.usbserial-0001)."
        )
    if len(ports) > 1:
        raise SerialError(
            "Multiple serial ports detected; pass --port explicitly:\n"
            + "\n".join(f"- {p}" for p in ports)
        )
    return ports[0]


def list_candidate_ports() -> list[str]:
    """List likely USB serial ports.

    Returns:
        Sorted list of matching serial device paths.
    """
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
    return ports


def _looks_fatal(buf: bytes) -> bool:
    """Check if buffer contains a fatal ESP32 error.

    Note: 'ERROR: <word> NOT FOUND!' from the REPL is NOT fatal - it just means
    the word doesn't exist. Only 'Guru Meditation Error' indicates a crash.
    """
    return b"Guru Meditation Error" in buf


def _looks_repl_error(buf: bytes) -> bool:
    """Check if buffer contains a REPL error.

    ESP32forth typically emits lines beginning with 'ERROR:' when a word fails
    to execute (e.g., NOT FOUND, stack underflow). This is not a device crash,
    but it should fail higher-level workflows like firmware loading.
    """
    return b"ERROR:" in buf


def _find_line_marker(buf: bytes | bytearray, marker: bytes) -> int | None:
    """Find a marker that must appear as a full line.

    The Bedrock protocol terminator is the line exactly '! end'. Using a raw
    substring search risks false positives if '! end' appears inside payload
    (e.g., in `source` output). This helper only matches when:
      - the marker starts at buffer start or after a newline, AND
      - the marker is followed by a newline (CRLF/LF/CR) or buffer end.

    Returns:
        The end index (including trailing newline if present) or None.
    """
    start = 0
    while True:
        pos = buf.find(marker, start)
        if pos == -1:
            return None

        # Require start-of-line.
        if pos == 0 or buf[pos - 1] in (0x0A, 0x0D):
            end = pos + len(marker)

            # Require end-of-line (or end-of-buffer).
            if end == len(buf):
                return end
            if buf[end : end + 2] == b"\r\n":
                return end + 2
            if buf[end : end + 1] in (b"\n", b"\r"):
                return end + 1

        start = pos + 1


class SerialSession:
    """Manages a serial connection to an ESP32forth/Bedrock device.

    Usage:
        session = SerialSession.open(port="/dev/cu.usbserial-0001")
        try:
            response = session.send_protocol("?")
            print(response)
        finally:
            session.close()

    Or as a context manager:
        with SerialSession.open() as session:
            response = session.send_protocol("?")
    """

    def __init__(self, ser: "serial_module.Serial", port: str) -> None:
        self._ser = ser
        self._port = port

    @property
    def port(self) -> str:
        """The serial port path."""
        return self._port

    @classmethod
    def open(
        cls,
        port: str | None = None,
        baud: int = 115200,
        settle_s: float = 5.0,
        quiet: bool = True,
    ) -> "SerialSession":
        """Open a serial session to a Bedrock device.

        Args:
            port: Serial port path. Auto-detected if None.
            baud: Baud rate (default 115200).
            settle_s: Quiet settle period in seconds (default 5.0).
                      During this time, the port is open but no data is sent,
                      allowing ESP32forth's autoexec (~3s wait + load time) to complete.
            quiet: If True, suppress DTR/RTS toggles that could reset the device.

        Returns:
            A SerialSession instance.

        Raises:
            SerialError: If port detection fails or connection cannot be established.
        """
        try:
            import serial
        except ImportError as exc:
            raise SerialError(
                "Missing dependency: pyserial\n"
                "Install: pip install pyserial"
            ) from exc

        if port is None:
            port = autodetect_port()

        try:
            ser = serial.Serial(port, baudrate=baud, timeout=0.1, rtscts=False, dsrdtr=False)
        except (OSError, serial.SerialException) as exc:
            raise SerialError(f"Could not open serial port {port!r}: {exc}") from exc

        # Avoid accidental ESP32 auto-reset on port open
        if quiet:
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass

        # Quiet settle: wait for autoexec to complete
        if settle_s > 0:
            time.sleep(settle_s)

        ser.reset_input_buffer()
        return cls(ser, port)

    def __enter__(self) -> "SerialSession":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the serial connection."""
        try:
            import serial  # type: ignore
            serial_exc: tuple[type[BaseException], ...] = (OSError, serial.SerialException)
        except ImportError:
            serial_exc = (OSError,)
        try:
            self._ser.dtr = False
            self._ser.rts = False
        except serial_exc:
            pass
        self._ser.close()

    def send_line(self, line: str) -> None:
        """Send a line to the device (appends CRLF)."""
        try:
            import serial  # type: ignore
            serial_exc: tuple[type[BaseException], ...] = (OSError, serial.SerialException)
        except ImportError:
            serial_exc = (OSError,)
        try:
            self._ser.reset_input_buffer()
            self._ser.write(line.encode("utf-8") + b"\r\n")
        except serial_exc as exc:
            raise SerialError(f"Failed to write to {self._port!r}: {exc}") from exc

    def read_until(self, marker: bytes, timeout_s: float) -> ReadResult:
        """Read from device until marker is found or timeout.

        Args:
            marker: Byte sequence to look for.
            timeout_s: Maximum time to wait in seconds.

        Returns:
            ReadResult with data and whether marker was found.
        """
        try:
            import serial  # type: ignore
            serial_exc: tuple[type[BaseException], ...] = (OSError, serial.SerialException)
        except ImportError:
            serial_exc = (OSError,)
        deadline = time.time() + timeout_s
        buf = bytearray()
        while time.time() < deadline:
            try:
                chunk = self._ser.read(1024)
            except serial_exc as exc:
                raise SerialError(f"Failed to read from {self._port!r}: {exc}") from exc
            if chunk:
                buf.extend(chunk)
                if marker in buf:
                    pos = buf.find(marker)
                    end = pos + len(marker)
                    # Include trailing CRLF if present
                    if buf[end : end + 2] == b"\r\n":
                        end += 2
                    return ReadResult(bytes(buf[:end]), True)
                continue
            time.sleep(0.01)
        return ReadResult(bytes(buf), False)

    def read_until_line(self, marker: bytes, timeout_s: float) -> ReadResult:
        """Read from device until a full-line marker is found or timeout."""
        try:
            import serial  # type: ignore
            serial_exc: tuple[type[BaseException], ...] = (OSError, serial.SerialException)
        except ImportError:
            serial_exc = (OSError,)
        deadline = time.time() + timeout_s
        buf = bytearray()
        while time.time() < deadline:
            try:
                chunk = self._ser.read(1024)
            except serial_exc as exc:
                raise SerialError(f"Failed to read from {self._port!r}: {exc}") from exc
            if chunk:
                buf.extend(chunk)
                end = _find_line_marker(buf, marker)
                if end is not None:
                    return ReadResult(bytes(buf[:end]), True)
                continue
            time.sleep(0.01)
        return ReadResult(bytes(buf), False)

    def send_protocol(self, line: str, timeout_s: float = 3.0) -> str:
        """Send a protocol command and wait for `! end` marker.

        Args:
            line: The protocol command (e.g., "?", "meta dump").
            timeout_s: Response timeout in seconds.

        Returns:
            The response text (including the `! end` marker).

        Raises:
            SerialTimeoutError: If `! end` not received within timeout.
            DeviceError: If device reports a fatal error.
        """
        self.send_line(line)
        result = self.read_until_line(MARKER_END, timeout_s)

        if _looks_fatal(result.data):
            raise DeviceError(f"Device reported fatal error: {result.text}")

        if not result.found:
            raise SerialTimeoutError(
                f"Timed out waiting for '! end' after sending: {line!r}\n"
                f"Received so far: {result.text[:200]}"
            )

        return result.text

    def send_repl(self, line: str, timeout_s: float = 3.0) -> str:
        """Send a REPL command and wait for ` ok` marker.

        Args:
            line: The Forth command to execute.
            timeout_s: Response timeout in seconds.

        Returns:
            The response text (including ` ok`).

        Raises:
            SerialTimeoutError: If ` ok` not received within timeout.
            DeviceError: If device reports a fatal error.
        """
        self.send_line(line)
        result = self.read_until(MARKER_OK, timeout_s)

        if _looks_fatal(result.data):
            raise DeviceError(f"Device reported fatal error: {result.text}")

        if _looks_repl_error(result.data):
            raise SerialError(f"Device reported REPL error after sending: {line!r}\n{result.text}")

        if not result.found:
            raise SerialTimeoutError(
                f"Timed out waiting for ' ok' after sending: {line!r}\n"
                f"Received so far: {result.text[:200]}"
            )

        return result.text

    def drain(self, timeout_s: float = 0.5) -> str:
        """Read any pending data from the device.

        Useful for clearing the buffer after operations that may produce
        additional output.

        Args:
            timeout_s: How long to wait for additional data.

        Returns:
            Any data received.
        """
        try:
            import serial  # type: ignore
            serial_exc: tuple[type[BaseException], ...] = (OSError, serial.SerialException)
        except ImportError:
            serial_exc = (OSError,)
        deadline = time.time() + timeout_s
        buf = bytearray()
        while time.time() < deadline:
            try:
                chunk = self._ser.read(1024)
            except serial_exc as exc:
                raise SerialError(f"Failed to read from {self._port!r}: {exc}") from exc
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep(0.01)
        return buf.decode("utf-8", errors="replace")
