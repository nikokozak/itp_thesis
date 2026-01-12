"""Transcript recording for Codignity sessions.

Records all sent commands and received responses to a plain-text file
for debugging, regression testing, and thesis artifacts.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from . import __version__


def _get_git_info() -> tuple[str | None, str | None]:
    """Get current git branch and commit hash."""
    branch = None
    commit = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
    except Exception:
        pass

    return branch, commit


class Transcript:
    """Context manager for recording session transcripts.

    Usage:
        with Transcript(Path("session.txt"), port="/dev/cu.usbserial-0001") as t:
            t.record_sent("?")
            t.record_received("! id node1\\n! end")
    """

    def __init__(
        self,
        path: Path,
        port: str,
        title: str = "Codignity Session Transcript",
    ) -> None:
        """Initialize transcript recorder.

        Args:
            path: Output file path.
            port: Serial port being used.
            title: Optional title for the transcript header.
        """
        self._path = path
        self._port = port
        self._title = title
        self._file: TextIO | None = None

    def __enter__(self) -> "Transcript":
        self._file = open(self._path, "w", encoding="utf-8")
        self._write_header()
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def _write_header(self) -> None:
        """Write the transcript header."""
        if not self._file:
            return

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        branch, commit = _get_git_info()

        self._file.write(f"# {self._title}\n")
        self._file.write(f"# Date: {now}\n")
        if branch:
            self._file.write(f"# Branch: {branch}\n")
        if commit:
            self._file.write(f"# Commit: {commit}\n")
        self._file.write(f"# Port: {self._port}\n")
        self._file.write(f"# Tool: codignity-cli v{__version__}\n")
        self._file.write("\n")

    def record_sent(self, line: str) -> None:
        """Record a command sent to the device.

        Args:
            line: The command line sent.
        """
        if self._file:
            self._file.write(f"> {line}\n")
            self._file.flush()

    def record_received(self, response: str) -> None:
        """Record a response received from the device.

        Args:
            response: The response text.
        """
        if self._file:
            # Write response as-is (may contain multiple lines)
            self._file.write(response)
            # Ensure trailing newline
            if response and not response.endswith("\n"):
                self._file.write("\n")
            self._file.flush()

    def record_comment(self, comment: str) -> None:
        """Record a comment in the transcript.

        Args:
            comment: Comment text (will be prefixed with ##).
        """
        if self._file:
            for line in comment.splitlines():
                self._file.write(f"## {line}\n")
            self._file.flush()

    def record_separator(self, title: str | None = None) -> None:
        """Record a visual separator in the transcript.

        Args:
            title: Optional section title.
        """
        if self._file:
            self._file.write("\n")
            if title:
                self._file.write(f"## {title}\n")
            self._file.write("\n")
            self._file.flush()


class NullTranscript:
    """No-op transcript for when recording is disabled."""

    def __enter__(self) -> "NullTranscript":
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        pass

    def record_sent(self, line: str) -> None:
        pass

    def record_received(self, response: str) -> None:
        pass

    def record_comment(self, comment: str) -> None:
        pass

    def record_separator(self, title: str | None = None) -> None:
        pass
