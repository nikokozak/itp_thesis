"""Board manifests for Bedrock terminal tooling.

Board manifests define the physical layout of development boards,
mapping GPIO numbers to physical positions and labels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class PinDef:
    """Definition of a single pin on a board."""

    pos: str  # e.g., "L1", "R15"
    label: str  # e.g., "3V3", "D4", "GND"
    gpio: int | None  # None for power/ground/control pins
    kind: Literal["power", "gnd", "signal", "control"]
    notes: str = ""


@dataclass
class BoardManifest:
    """Complete board manifest."""

    board_id: str
    display_name: str
    pins: list[PinDef] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "BoardManifest":
        """Load a board manifest from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pins = [
            PinDef(
                pos=p["pos"],
                label=p["label"],
                gpio=p.get("gpio"),
                kind=p.get("kind", "signal"),
                notes=p.get("notes", ""),
            )
            for p in data.get("pins", [])
        ]

        return cls(
            board_id=data["board_id"],
            display_name=data.get("display_name", data["board_id"]),
            pins=pins,
        )

    def gpio_to_label(self, gpio: int) -> str | None:
        """Get the label for a GPIO number."""
        for pin in self.pins:
            if pin.gpio == gpio:
                return pin.label
        return None

    def label_to_gpio(self, label: str) -> int | None:
        """Get the GPIO number for a label."""
        label_upper = label.upper()
        for pin in self.pins:
            if pin.label.upper() == label_upper and pin.gpio is not None:
                return pin.gpio
        return None

    def left_column(self) -> list[PinDef]:
        """Get pins in left column (L1, L2, ...)."""
        return sorted(
            [p for p in self.pins if p.pos.startswith("L")],
            key=lambda p: int(p.pos[1:]),
        )

    def right_column(self) -> list[PinDef]:
        """Get pins in right column (R1, R2, ...)."""
        return sorted(
            [p for p in self.pins if p.pos.startswith("R")],
            key=lambda p: int(p.pos[1:]),
        )


# Cache of loaded manifests
_manifest_cache: dict[str, BoardManifest] = {}


def get_manifest(board_id: str) -> BoardManifest | None:
    """Get a board manifest by ID.

    Args:
        board_id: The board identifier (e.g., "doit-esp32-devkit-v1").

    Returns:
        The BoardManifest, or None if not found.
    """
    if board_id in _manifest_cache:
        return _manifest_cache[board_id]

    boards_dir = Path(__file__).parent
    manifest_path = boards_dir / f"{board_id}.json"

    if not manifest_path.exists():
        return None

    manifest = BoardManifest.load(manifest_path)
    _manifest_cache[board_id] = manifest
    return manifest


def list_boards() -> list[str]:
    """List available board IDs."""
    boards_dir = Path(__file__).parent
    return [p.stem for p in boards_dir.glob("*.json")]
