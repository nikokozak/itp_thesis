"""Pin capture parsing and helpers for Bedrock protocol.

Parses responses for:
  - `pin-capture-cap`
  - `pin-capture`

Designed to be noise-tolerant: ignores non-protocol garbage lines that can
appear on reconnect (ESP32 ROM boot output, partial lines, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CaptureCap:
    """Capabilities reported by `pin-capture-cap`."""

    kind: str = "digital"
    mode: str = "sample"
    dest: str = "stream"
    formats: tuple[str, ...] = ("rle", "list")
    dt_unit: str = "ms"
    min_dt: int = 1
    max_n: int = 0
    default_dt: int = 0
    default_n: int = 0
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptureHeader:
    """Header reported by `pin-capture`."""

    gpio: int
    kind: str = "digital"
    mode: str = "sample"
    dest: str = "stream"
    n: int = 0
    dt: int = 0
    dt_unit: str = "ms"
    fmt: str = "rle"
    raw: dict[str, str] = field(default_factory=dict)


def _parse_kv_tokens(line: str) -> dict[str, str]:
    """Parse key=value tokens from a single protocol line."""
    out: dict[str, str] = {}
    for tok in line.split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        if k:
            out[k] = v
    return out


def parse_capture_cap_response(text: str) -> CaptureCap | None:
    """Parse a `pin-capture-cap` response into a CaptureCap."""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("! cap "):
            continue

        kv = _parse_kv_tokens(line[6:])
        formats = tuple(f for f in kv.get("formats", "").split(",") if f)

        def _int(key: str) -> int:
            try:
                return int(kv[key])
            except Exception:
                return 0

        return CaptureCap(
            kind=kv.get("kind", "digital"),
            mode=kv.get("mode", "sample"),
            dest=kv.get("dest", "stream"),
            formats=formats or ("rle", "list"),
            dt_unit=kv.get("dt_unit", "ms"),
            min_dt=_int("min_dt"),
            max_n=_int("max_n"),
            default_dt=_int("default_dt"),
            default_n=_int("default_n"),
            raw=kv,
        )
    return None


def parse_capture_response(text: str) -> tuple[CaptureHeader, list[int]]:
    """Parse a `pin-capture` response into (header, samples).

    Returns:
        header: CaptureHeader (required; raises ValueError if missing)
        samples: Expanded list of 0/1 samples.
    """
    header: CaptureHeader | None = None
    runs: list[tuple[int, int]] = []
    samples: list[tuple[int, int]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()

        if line.startswith("! capture "):
            kv = _parse_kv_tokens(line[10:])

            def _int(key: str) -> int:
                try:
                    return int(kv[key])
                except Exception:
                    return 0

            header = CaptureHeader(
                gpio=_int("gpio"),
                kind=kv.get("kind", "digital"),
                mode=kv.get("mode", "sample"),
                dest=kv.get("dest", "stream"),
                n=_int("n"),
                dt=_int("dt"),
                dt_unit=kv.get("dt_unit", "ms"),
                fmt=kv.get("format", kv.get("fmt", "rle")),
                raw=kv,
            )
            continue

        if line.startswith("! run "):
            kv = _parse_kv_tokens(line[6:])
            try:
                v = int(kv.get("v", "0"))
                n = int(kv.get("n", "0"))
            except ValueError:
                continue
            if n > 0:
                runs.append((1 if v else 0, n))
            continue

        if line.startswith("! samp "):
            kv = _parse_kv_tokens(line[7:])
            try:
                i = int(kv.get("i", "0"))
                v = int(kv.get("v", "0"))
            except ValueError:
                continue
            samples.append((i, 1 if v else 0))
            continue

    if header is None:
        raise ValueError("Missing capture header ('! capture ...') in response")

    # Prefer explicit samples if present; else expand runs.
    if samples:
        # Order by index; ignore gaps/mismatched indices.
        samples.sort(key=lambda t: t[0])
        expanded = [v for _, v in samples]
        return header, expanded

    expanded = expand_rle(runs)
    return header, expanded


def expand_rle(runs: list[tuple[int, int]]) -> list[int]:
    """Expand run-length encoding to a list of samples."""
    out: list[int] = []
    for v, n in runs:
        if n <= 0:
            continue
        out.extend([1 if v else 0] * n)
    return out


def count_transitions(samples: list[int]) -> int:
    """Count 0<->1 transitions in a sample sequence."""
    if not samples:
        return 0
    last = samples[0]
    transitions = 0
    for v in samples[1:]:
        if v != last:
            transitions += 1
            last = v
    return transitions


def render_digital_preview(samples: list[int], width: int = 60) -> str:
    """Render a compact ASCII preview of digital samples.

    Uses '_' for low and '‾' for high. Downsamples if needed.
    """
    if width <= 0:
        return ""
    if not samples:
        return ""

    if len(samples) <= width:
        return "".join("‾" if v else "_" for v in samples)

    # Downsample by simple bucket majority.
    step = len(samples) / float(width)
    out_chars: list[str] = []
    for col in range(width):
        start = int(col * step)
        end = int((col + 1) * step)
        if end <= start:
            end = min(len(samples), start + 1)
        bucket = samples[start:end]
        ones = sum(bucket)
        out_chars.append("‾" if ones >= (len(bucket) / 2) else "_")
    return "".join(out_chars)

