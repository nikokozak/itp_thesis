"""Per-node defs log management for cross-invocation define capture.

Defs logs are stored in .bedrock/defs/<node_id>.defs (repo-local, gitignored).
Format:
  - Comment lines start with # (may include ISO8601 UTC timestamp + port)
  - One `define : name ... ;` line per definition
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

# Repo-local defs directory (should be gitignored)
DEFS_DIR = Path(".bedrock/defs")


def get_defs_path(node_id: str) -> Path:
    """Get the path to a node's defs log file.

    Args:
        node_id: Node identifier (from meta id).

    Returns:
        Path to the defs log file.
    """
    # Sanitize node_id for filename safety
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in node_id)
    if not safe_id:
        safe_id = "unknown"
    return DEFS_DIR / f"{safe_id}.defs"


def append_define(node_id: str, define_line: str, port: str | None = None) -> Path:
    """Append a define line to the node's defs log.

    Args:
        node_id: Node identifier.
        define_line: The full define command (e.g., "define : foo 123 ;").
        port: Optional port path for the comment.

    Returns:
        Path to the defs log file.
    """
    path = get_defs_path(node_id)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Build comment line
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    comment_parts = [f"# {timestamp}"]
    if port:
        comment_parts.append(f"port={port}")
    comment = " ".join(comment_parts)

    # Ensure define_line is properly formatted
    line = define_line.strip()
    if not line.startswith("define"):
        if line.startswith(":"):
            line = f"define {line}"
        else:
            line = f"define : {line}"

    # Append to file
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{comment}\n")
        f.write(f"{line}\n")

    return path


def load_defs(node_id: str) -> list[str]:
    """Load all define lines from a node's defs log.

    Args:
        node_id: Node identifier.

    Returns:
        List of define lines (without comments).
    """
    path = get_defs_path(node_id)

    if not path.exists():
        return []

    defs: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                defs.append(line)

    return defs


def load_defs_from_file(path: Path) -> list[str]:
    """Load define lines from an arbitrary file.

    Args:
        path: Path to the defs file.

    Returns:
        List of define lines.
    """
    if not path.exists():
        return []

    defs: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                # Normalize to define format
                if line.startswith("define"):
                    defs.append(line)
                elif line.startswith(":"):
                    defs.append(f"define {line}")

    return defs


def merge_defs(base_defs: list[str], override_defs: list[str]) -> tuple[list[str], list[str]]:
    """Merge two lists of define lines, with override taking precedence.

    Args:
        base_defs: Base define lines (from node's defs log).
        override_defs: Override define lines (from --defs file).

    Returns:
        Tuple of (merged_defs, notes about overrides).
    """
    from .snapshot import extract_def_name

    # Build name -> line mapping
    defs_by_name: dict[str, str] = {}
    notes: list[str] = []

    # Add base defs
    for line in base_defs:
        name = extract_def_name(line)
        if name:
            defs_by_name[name] = line

    # Override with provided defs
    for line in override_defs:
        name = extract_def_name(line)
        if name:
            if name in defs_by_name and defs_by_name[name] != line:
                notes.append(f"override {name}")
            defs_by_name[name] = line

    return list(defs_by_name.values()), notes
