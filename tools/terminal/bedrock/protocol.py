"""Bedrock protocol handling: probe, mode detection, command parsing.

This module provides functions for detecting whether a device is running
Bedrock, probing its identity, and parsing protocol responses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from .session import SerialSession, SerialError, SerialTimeoutError, MARKER_OK, MARKER_END


@dataclass
class ProbeResult:
    """Result of probing a Bedrock node."""

    port: str
    mode: Literal["repl", "protocol", "unknown"]
    bedrock_loaded: bool
    node_id: str | None = None
    role: str | None = None
    ver: str | None = None
    mcu: str | None = None
    fifo: int | None = None
    units: str | None = None
    pins: str | None = None
    children: int | None = None
    raw_identity: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "port": self.port,
            "mode": self.mode,
            "bedrock_loaded": self.bedrock_loaded,
            "node_id": self.node_id,
            "role": self.role,
            "ver": self.ver,
            "mcu": self.mcu,
            "fifo": self.fifo,
            "units": self.units,
            "pins": self.pins,
            "children": self.children,
        }


def _normalize_marker_line(line: str) -> str:
    """Normalize a noisy serial line into a protocol marker line.

    Some serial monitors or device boot logs can prefix protocol output with
    non-UTF8 noise or partial fragments. This helper tries to recover the
    start of a Bedrock protocol line by locating the earliest `! ` or `#`.
    """
    line = line.strip()
    if not line:
        return ""

    if line.startswith("! ") or line.startswith("#"):
        return line

    bang = line.find("! ")
    hash_pos = line.find("#")
    starts = [pos for pos in (bang, hash_pos) if pos != -1]
    if not starts:
        return ""
    return line[min(starts) :]


def parse_identity(response: str) -> dict[str, str]:
    """Parse identity response lines into key-value pairs.

    Parses lines like:
        ! id node1
        ! role gateway
        ! ver thesis-0.1

    Args:
        response: The full response text from `?` or `explain` command.

    Returns:
        Dictionary mapping keys to values.
    """
    result: dict[str, str] = {}
    for line in response.splitlines():
        line = _normalize_marker_line(line)
        if not line:
            continue
        if line.startswith("! "):
            if line == "! end":
                continue
            parts = line[2:].split(None, 1)
            if len(parts) >= 1:
                key = parts[0]
                value = parts[1] if len(parts) > 1 else ""
                result[key] = value
    return result


def is_error(response: str) -> tuple[bool, str | None]:
    """Check if response contains an error.

    Looks for lines starting with `# err` or `# `.

    Args:
        response: The response text to check.

    Returns:
        Tuple of (is_error, error_message).
    """
    for line in response.splitlines():
        line = _normalize_marker_line(line)
        if not line:
            continue
        if line.startswith("# err "):
            return True, line[6:]
        if line.startswith("# "):
            return True, line[2:]
    return False, None


def probe(session: SerialSession, timeout_s: float = 3.0) -> ProbeResult:
    """Probe a device to detect Bedrock and get its identity.

    Algorithm:
    1. Try `meta id` (protocol command) - if responds with `! end`, Bedrock is loaded
    2. If timeout, try `revive` (REPL command) to enter protocol mode
    3. If revive succeeds, try `?` to get identity
    4. Fall back to checking plain REPL mode

    Args:
        session: An open SerialSession.
        timeout_s: Timeout for each probe attempt.

    Returns:
        ProbeResult with device information.
    """
    port = session.port

    # Try protocol probe first: `meta id`
    try:
        response = session.send_protocol("meta id", timeout_s)
        # Success - we're in protocol mode with Bedrock loaded
        identity = parse_identity(response)

        # Get full identity with `?`
        try:
            full_response = session.send_protocol("?", timeout_s)
            identity = parse_identity(full_response)
        except SerialTimeoutError:
            pass

        return _build_probe_result(port, "protocol", True, identity)

    except SerialTimeoutError:
        # Drain any leftover response from failed protocol attempt
        session.drain(0.3)

    # Protocol probe failed - try REPL mode
    # First, try `revive` to enter protocol mode (Bedrock loaded but in REPL)
    try:
        session.send_line("revive")
        result = session.read_until(MARKER_OK, timeout_s)
        if result.found and b"not found" not in result.data.lower():
            # revive succeeded - now try protocol probe
            session.drain(0.2)
            try:
                response = session.send_protocol("?", timeout_s)
                identity = parse_identity(response)
                return _build_probe_result(port, "protocol", True, identity)
            except SerialTimeoutError:
                # revive worked but protocol probe failed
                return ProbeResult(
                    port=port,
                    mode="repl",
                    bedrock_loaded=True,
                )
    except SerialError:
        pass

    # Drain buffer before next attempt
    session.drain(0.3)

    # Check if we're in plain REPL mode (ESP32forth without Bedrock)
    try:
        session.send_line("sp0 sp!")  # Safe no-op that resets stack
        result = session.read_until(MARKER_OK, timeout_s)
        if result.found:
            return ProbeResult(
                port=port,
                mode="repl",
                bedrock_loaded=False,
            )
    except SerialError:
        pass

    # Could not determine mode
    return ProbeResult(
        port=port,
        mode="unknown",
        bedrock_loaded=False,
    )


def _build_probe_result(
    port: str,
    mode: Literal["repl", "protocol", "unknown"],
    bedrock_loaded: bool,
    identity: dict[str, str],
) -> ProbeResult:
    """Build a ProbeResult from parsed identity."""
    fifo = None
    if "fifo" in identity:
        try:
            fifo = int(identity["fifo"].strip())
        except ValueError:
            pass

    children = None
    if "children" in identity:
        try:
            children = int(identity["children"].strip())
        except ValueError:
            pass

    return ProbeResult(
        port=port,
        mode=mode,
        bedrock_loaded=bedrock_loaded,
        node_id=identity.get("id"),
        role=identity.get("role"),
        ver=identity.get("ver"),
        mcu=identity.get("mcu"),
        fifo=fifo,
        units=identity.get("units"),
        pins=identity.get("pins"),
        children=children,
        raw_identity=identity,
    )


def ensure_protocol(session: SerialSession, timeout_s: float = 3.0) -> bool:
    """Ensure the device is in protocol mode.

    If Bedrock is loaded but in REPL mode, sends `revive` to enter protocol mode.

    Args:
        session: An open SerialSession.
        timeout_s: Timeout for commands.

    Returns:
        True if now in protocol mode, False otherwise.
    """
    # Try a protocol command
    try:
        session.send_protocol("meta id", timeout_s)
        return True
    except SerialTimeoutError:
        # Drain any leftover response
        session.drain(0.3)

    # Try revive (Bedrock loaded but in REPL mode)
    try:
        session.send_line("revive")
        result = session.read_until(MARKER_OK, timeout_s)
        if result.found and b"not found" not in result.data.lower():
            # revive succeeded - verify protocol mode
            session.drain(0.2)
            try:
                session.send_protocol("meta id", timeout_s)
                return True
            except SerialTimeoutError:
                pass
    except SerialError:
        pass

    return False


def ensure_repl(session: SerialSession, timeout_s: float = 3.0) -> bool:
    """Ensure the device is in REPL mode.

    If in protocol mode, sends `repl` command to exit.

    Args:
        session: An open SerialSession.
        timeout_s: Timeout for commands.

    Returns:
        True if now in REPL mode, False otherwise.
    """
    # Try a REPL command first
    try:
        session.send_line("sp0 sp!")
        result = session.read_until(MARKER_OK, timeout_s)
        if result.found:
            return True
    except SerialError:
        pass

    # Try sending `repl` command (protocol mode exit)
    try:
        response = session.send_protocol("repl", timeout_s)
        # Should get `! ok` then `! end`
        # Now try REPL mode
        session.send_line("sp0 sp!")
        result = session.read_until(MARKER_OK, timeout_s)
        if result.found:
            return True
    except SerialError:
        pass

    return False


def parse_meta_dump(response: str) -> dict[str, str]:
    """Parse `meta dump` response into key-value pairs.

    The response format is:
        ! key1 value1
        ! key2 value2
        ! end

    Args:
        response: The response from `meta dump`.

    Returns:
        Dictionary of meta key-value pairs.
    """
    result: dict[str, str] = {}
    for line in response.splitlines():
        line = _normalize_marker_line(line)
        if not line:
            continue
        if line.startswith("! ") and line != "! end":
            parts = line[2:].split(None, 1)
            if len(parts) == 2:
                result[parts[0]] = parts[1]
    return result


def extract_def_name(define_line: str) -> str | None:
    """Extract the word name from a define line.

    Args:
        define_line: A line like "define : foo 123 ;"

    Returns:
        The word name (e.g., "foo") or None if parsing fails.
    """
    # Pattern: define : <name> ... ;
    match = re.match(r"define\s*:\s*(\S+)", define_line)
    if match:
        return match.group(1)
    return None
