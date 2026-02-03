"""Pin state parsing and representation for Bedrock protocol.

Parses the output of `pins` and `pin-status` commands into structured data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class PinState:
    """State of a single GPIO pin."""

    gpio: int
    mode: str = "unknown"  # unknown, in, out, adc, i2c, uart, pwm, reserved
    drive: int | None = None  # 0, 1, or None if not meaningful/unknown
    level: int | None = None  # 0, 1, or None if unreadable
    pull: str = "none"  # none, up, down
    owner: str | None = None
    flags: set[str] = field(default_factory=set)  # safe, strapping, input-only, flash
    label: str | None = None  # Populated from board manifest

    def is_safe(self) -> bool:
        """Check if this is the SAFE pin."""
        return "safe" in self.flags

    def is_strapping(self) -> bool:
        """Check if this is a strapping pin."""
        return "strapping" in self.flags

    def is_input_only(self) -> bool:
        """Check if this pin is input-only."""
        return "input-only" in self.flags

    def is_flash(self) -> bool:
        """Check if this pin is used for flash."""
        return "flash" in self.flags

    def is_dangerous(self) -> bool:
        """Check if modifying this pin is dangerous."""
        return self.is_strapping() or self.is_flash()


def _normalize_marker_line(line: str) -> str:
    """Normalize a noisy serial line into a protocol marker line.

    Serial boot logs or monitor quirks can prefix Bedrock protocol output with
    junk characters. Recover protocol lines by locating the earliest `! ` or `#`.
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


def parse_pin_kv(line: str) -> PinState | None:
    """Parse a single `! pin ...` line into a PinState.

    Example line:
        ! pin gpio=4 mode=in level=1 pull=up owner=button flags=safe

    Args:
        line: A protocol response line starting with `! pin`.

    Returns:
        PinState, or None if parsing fails.
    """
    line = _normalize_marker_line(line)
    if not line.startswith("! pin "):
        return None

    # Extract key=value pairs
    kv_pattern = re.compile(r"(\w+)=(\S+)")
    matches = kv_pattern.findall(line)

    if not matches:
        return None

    data = dict(matches)

    if "gpio" not in data:
        return None

    try:
        gpio = int(data["gpio"])
    except ValueError:
        return None

    # Parse drive (optional)
    drive = None
    if "drive" in data and data["drive"] != "-":
        try:
            drive = int(data["drive"])
        except ValueError:
            pass

    # Parse level
    level = None
    if "level" in data and data["level"] != "-":
        try:
            level = int(data["level"])
        except ValueError:
            pass

    # Parse owner
    owner = data.get("owner")
    if owner == "-":
        owner = None

    # Parse flags
    flags_str = data.get("flags", "-")
    if flags_str == "-":
        flags = set()
    else:
        flags = set(flags_str.split(","))

    return PinState(
        gpio=gpio,
        mode=data.get("mode", "unknown"),
        drive=drive,
        level=level,
        pull=data.get("pull", "none"),
        owner=owner,
        flags=flags,
    )


def parse_pins_response(text: str) -> tuple[str | None, dict[int, PinState]]:
    """Parse a complete `pins` response.

    Args:
        text: The full response from the `pins` command.

    Returns:
        Tuple of (board_id or None, dict mapping gpio -> PinState).
    """
    board_id = None
    pins: dict[int, PinState] = {}

    for line in text.splitlines():
        line = _normalize_marker_line(line)
        if not line:
            continue

        if line.startswith("! board "):
            board_id = line[8:].strip()
        elif line.startswith("! pin "):
            state = parse_pin_kv(line)
            if state is not None:
                pins[state.gpio] = state

    return board_id, pins


def parse_pin_value_response(text: str) -> int | None:
    """Parse a `pin-read` response.

    Args:
        text: The response from `pin-read`.

    Returns:
        The value (0 or 1), or None if parsing fails.
    """
    for line in text.splitlines():
        line = _normalize_marker_line(line)
        if not line:
            continue
        if line.startswith("! value "):
            try:
                return int(line[8:].strip())
            except ValueError:
                return None
    return None
