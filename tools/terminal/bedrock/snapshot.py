"""Bedrock snapshot format parser and writer.

Snapshots capture the full state of a Bedrock node for backup/restore.
Format is human-readable with sections for meta, defs, and notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


@dataclass
class Snapshot:
    """A snapshot of a Bedrock node's state.

    Attributes:
        date: ISO8601 UTC timestamp when snapshot was created.
        node_id: Node identifier (from `! id`).
        role: Node role (from `! role`).
        ver: Firmware version (from `! ver`).
        meta: All metadata key-value pairs.
        defs: List of define commands (full `define : name ... ;` lines).
        notes: Additional notes (e.g., "safe-save ok").
    """

    date: str
    node_id: str | None = None
    role: str | None = None
    ver: str | None = None
    meta: dict[str, str] = field(default_factory=dict)
    defs: list[str] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Snapshot":
        """Load a snapshot from a .brsnap file.

        Args:
            path: Path to the snapshot file.

        Returns:
            Parsed Snapshot instance.

        Raises:
            ValueError: If the file format is invalid.
            FileNotFoundError: If the file doesn't exist.
        """
        with open(path, "r", encoding="utf-8") as f:
            return cls._parse(f)

    @classmethod
    def _parse(cls, f: TextIO) -> "Snapshot":
        """Parse snapshot from file handle."""
        saw_header = False
        saw_section = False
        date = ""
        node_id: str | None = None
        role: str | None = None
        ver: str | None = None
        meta: dict[str, str] = {}
        defs: list[str] = []
        notes: dict[str, str] = {}

        current_section: str | None = None

        for line in f:
            line = line.rstrip("\n\r")

            # Header comments
            if re.match(r"^#\s+.*\bSnapshot\b", line):
                saw_header = True
                continue

            if line.startswith("# date:"):
                date = line[7:].strip()
                continue

            if line.startswith("# node:"):
                # Parse "id=node1 role=gateway ver=thesis-0.1"
                node_info = line[7:].strip()
                for part in node_info.split():
                    if "=" in part:
                        key, val = part.split("=", 1)
                        if key == "id":
                            node_id = val
                        elif key == "role":
                            role = val
                        elif key == "ver":
                            ver = val
                continue

            # Skip other comments in header
            if line.startswith("#"):
                continue

            # Section headers
            if line == "[meta]":
                saw_section = True
                current_section = "meta"
                continue
            if line == "[defs]":
                saw_section = True
                current_section = "defs"
                continue
            if line == "[notes]":
                saw_section = True
                current_section = "notes"
                continue

            # Skip empty lines
            if not line.strip():
                continue

            # Parse section content
            if current_section == "meta":
                parts = line.split(None, 1)
                if len(parts) >= 1:
                    key = parts[0]
                    value = parts[1] if len(parts) > 1 else ""
                    meta[key] = value

            elif current_section == "defs":
                # Each line is a full define command
                if line.strip():
                    defs.append(line.strip())

            elif current_section == "notes":
                parts = line.split(None, 1)
                if len(parts) >= 1:
                    key = parts[0]
                    value = parts[1] if len(parts) > 1 else ""
                    notes[key] = value

        if not saw_header:
            raise ValueError("Missing snapshot header (expected '# ... Snapshot ...')")
        if not date:
            raise ValueError("Missing snapshot date header: '# date: ...'")
        if not saw_section:
            raise ValueError("Missing snapshot sections (expected [meta]/[defs]/[notes])")

        return cls(
            date=date,
            node_id=node_id,
            role=role,
            ver=ver,
            meta=meta,
            defs=defs,
            notes=notes,
        )

    def save(self, path: Path) -> None:
        """Save snapshot to a .brsnap file.

        Args:
            path: Destination path for the snapshot file.
        """
        with open(path, "w", encoding="utf-8") as f:
            self._write(f)

    def _write(self, f: TextIO) -> None:
        """Write snapshot to file handle."""
        # Header
        f.write("# Bedrock Snapshot v1\n")
        f.write(f"# date: {self.date}\n")

        # Node info line
        node_parts = []
        if self.node_id:
            node_parts.append(f"id={self.node_id}")
        if self.role:
            node_parts.append(f"role={self.role}")
        if self.ver:
            node_parts.append(f"ver={self.ver}")
        if node_parts:
            f.write(f"# node: {' '.join(node_parts)}\n")

        f.write("\n")

        # Meta section
        f.write("[meta]\n")
        for key, value in sorted(self.meta.items()):
            f.write(f"{key} {value}\n")
        f.write("\n")

        # Defs section
        f.write("[defs]\n")
        for defn in self.defs:
            f.write(f"{defn}\n")
        f.write("\n")

        # Notes section
        f.write("[notes]\n")
        for key, value in sorted(self.notes.items()):
            f.write(f"{key} {value}\n")

    @classmethod
    def create_now(
        cls,
        node_id: str | None = None,
        role: str | None = None,
        ver: str | None = None,
        meta: dict[str, str] | None = None,
        defs: list[str] | None = None,
        notes: dict[str, str] | None = None,
    ) -> "Snapshot":
        """Create a new snapshot with current timestamp.

        Args:
            node_id: Node identifier.
            role: Node role.
            ver: Firmware version.
            meta: Metadata key-value pairs.
            defs: List of define commands.
            notes: Additional notes.

        Returns:
            New Snapshot instance with current UTC timestamp.
        """
        return cls(
            date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            node_id=node_id,
            role=role,
            ver=ver,
            meta=meta or {},
            defs=defs or [],
            notes=notes or {},
        )


def extract_def_name(define_line: str) -> str | None:
    """Extract the word name from a define command.

    Args:
        define_line: A line like "define : foo 123 ;" or ": foo 123 ;"

    Returns:
        The word name (e.g., "foo") or None if parsing fails.
    """
    # Handle both "define : name" and ": name" formats
    line = define_line.strip()
    if line.startswith("define"):
        line = line[6:].strip()

    # Now we should have ": name ... ;"
    match = re.match(r":\s*(\S+)", line)
    if match:
        return match.group(1)
    return None


def load_baseline_defs(firmware_path: Path) -> set[str]:
    """Extract word names defined in the Bedrock firmware source.

    "Baseline/core" here means words shipped by Bedrock (our firmware sources,
    typically `firmware/esp32/bedrock.fs`), not ESP32forth's built-in kernel
    words. The CLI uses this set to suppress diff noise so `snapshot diff`
    focuses on user-defined words.

    Parses lines starting with `: name` (Forth word definitions) to build
    a set of baseline/core word names that should be excluded from diffs.

    Args:
        firmware_path: Path to bedrock.fs or similar Forth source file.

    Returns:
        Set of word names defined in the firmware.
    """
    def strip_inline_comment(s: str) -> str:
        # Forth `\` comments out the rest of the line.
        return s.split("\\", 1)[0].strip()

    def parse_file(path: Path, seen: set[Path]) -> set[str]:
        if path in seen:
            return set()
        seen.add(path)
        if not path.exists():
            return set()

        defs: set[str] = set()
        try:
            with open(path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = strip_inline_comment(raw_line)
                    if not line:
                        continue

                    # Best-effort support for modular firmware layouts:
                    # follow `include <path>` lines relative to the current file.
                    lowered = line.lower()
                    if lowered.startswith("include ") or lowered.startswith("included "):
                        _, rest = line.split(None, 1)
                        include_rel = rest.strip().strip("\"'")  # tolerate quotes
                        if include_rel:
                            defs |= parse_file((path.parent / include_rel), seen)
                        continue

                    match = re.match(r":\s+(\S+)", line)
                    if match:
                        defs.add(match.group(1))
        except Exception:
            return set()

        return defs

    return parse_file(firmware_path, set())


@dataclass
class SnapshotDiff:
    """Difference between live node state and a snapshot.

    Attributes:
        meta_added: Keys present in live but not snapshot.
        meta_removed: Keys present in snapshot but not live.
        meta_changed: Keys present in both but with different values.
        def_collisions: Define names that exist in both (potential conflicts).
        live_only_defs: Define names only in live state.
        snapshot_only_defs: Define names only in snapshot.
    """

    meta_added: dict[str, str] = field(default_factory=dict)
    meta_removed: dict[str, str] = field(default_factory=dict)
    meta_changed: dict[str, tuple[str, str]] = field(default_factory=dict)  # (snap, live)
    def_collisions: list[str] = field(default_factory=list)
    live_only_defs: list[str] = field(default_factory=list)
    snapshot_only_defs: list[str] = field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        """Check if there are any differences."""
        return bool(
            self.meta_added
            or self.meta_removed
            or self.meta_changed
            or self.def_collisions
            or self.live_only_defs
            or self.snapshot_only_defs
        )


def compute_diff(
    snapshot: Snapshot,
    live_meta: dict[str, str],
    live_defs: list[str],
) -> SnapshotDiff:
    """Compare a snapshot against live node state.

    Args:
        snapshot: The snapshot to compare against.
        live_meta: Current metadata from the live node.
        live_defs: Current define names from the live node.

    Returns:
        SnapshotDiff describing all differences.
    """
    diff = SnapshotDiff()

    # Compare meta
    snap_keys = set(snapshot.meta.keys())
    live_keys = set(live_meta.keys())

    for key in live_keys - snap_keys:
        diff.meta_added[key] = live_meta[key]

    for key in snap_keys - live_keys:
        diff.meta_removed[key] = snapshot.meta[key]

    for key in snap_keys & live_keys:
        if snapshot.meta[key] != live_meta[key]:
            diff.meta_changed[key] = (snapshot.meta[key], live_meta[key])

    # Compare defs
    snap_def_names = {extract_def_name(d) for d in snapshot.defs}
    snap_def_names.discard(None)
    live_def_names = set(live_defs)

    diff.def_collisions = sorted(snap_def_names & live_def_names)
    diff.live_only_defs = sorted(live_def_names - snap_def_names)
    diff.snapshot_only_defs = sorted(snap_def_names - live_def_names)

    return diff


def format_diff(diff: SnapshotDiff) -> str:
    """Format a SnapshotDiff for human-readable output.

    Args:
        diff: The diff to format.

    Returns:
        Multi-line string describing the differences.
    """
    lines: list[str] = []

    if not diff.has_differences:
        lines.append("No differences found.")
        return "\n".join(lines)

    if diff.meta_added:
        lines.append("Meta keys added (live only):")
        for key, value in sorted(diff.meta_added.items()):
            lines.append(f"  + {key} = {value}")

    if diff.meta_removed:
        lines.append("Meta keys removed (snapshot only):")
        for key, value in sorted(diff.meta_removed.items()):
            lines.append(f"  - {key} = {value}")

    if diff.meta_changed:
        lines.append("Meta keys changed:")
        for key, (snap_val, live_val) in sorted(diff.meta_changed.items()):
            lines.append(f"  ~ {key}: {snap_val!r} -> {live_val!r}")

    if diff.def_collisions:
        lines.append("Define name collisions (exist in both):")
        for name in diff.def_collisions:
            lines.append(f"  ! {name}")

    if diff.live_only_defs:
        lines.append("Defines only on live node:")
        for name in diff.live_only_defs:
            lines.append(f"  + {name}")

    if diff.snapshot_only_defs:
        lines.append("Defines only in snapshot:")
        for name in diff.snapshot_only_defs:
            lines.append(f"  - {name}")

    return "\n".join(lines)
