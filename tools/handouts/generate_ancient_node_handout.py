#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import shutil
import subprocess
import sys
from pathlib import Path


PAGE_W = 612  # 8.5in * 72pt
PAGE_H = 792  # 11in * 72pt
M = 36

HEADER_H = 74
COL_GAP = 20
LEFT_W = 230
RIGHT_W = (PAGE_W - 2 * M) - COL_GAP - LEFT_W

LEFT_X = M
RIGHT_X = M + LEFT_W + COL_GAP


def _e(text: str) -> str:
    return html.escape(text, quote=True)


def _t(x: float, y: float, text: str, *, size: float = 9.0, bold: bool = False, fill: str = "#000") -> str:
    weight = "700" if bold else "400"
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Courier New, Courier, monospace" '
        f'font-size="{size:.2f}" font-weight="{weight}" fill="{fill}" xml:space="preserve">{_e(text)}</text>'
    )


def _rect(x: float, y: float, w: float, h: float, *, stroke: str = "#000", fill: str = "none", sw: float = 1.0) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" stroke="{stroke}" stroke-width="{sw:.1f}" fill="{fill}"/>'


def _line(x1: float, y1: float, x2: float, y2: float, *, stroke: str = "#000", sw: float = 1.0) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{sw:.1f}"/>'


def build_svg(code_path: Path) -> str:
    code_lines = code_path.read_text(encoding="utf-8").splitlines()
    numbered = [f"! {i:02d} {line}" for i, line in enumerate(code_lines, start=1)]

    led_gpio = None
    radio_gpio = None
    for line in code_lines:
        m = re.match(r"^\s*:\s*led\.gpio\b.*\b(\d+)\s*;\s*$", line)
        if m:
            led_gpio = int(m.group(1))
            continue
        m = re.match(r"^\s*:\s*radio\.gpio\b.*\b(\d+)\s*;\s*$", line)
        if m:
            radio_gpio = int(m.group(1))

    if led_gpio is None:
        led_gpio = 23
    if radio_gpio is None:
        radio_gpio = 34

    content_w = PAGE_W - 2 * M
    content_h = PAGE_H - 2 * M

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}pt" height="{PAGE_H}pt" viewBox="0 0 {PAGE_W} {PAGE_H}">'
    )

    # Outer border + header bar
    parts.append(_rect(M, M, content_w, content_h, sw=2.0))
    parts.append(_rect(M, M, content_w, HEADER_H, sw=1.0, fill="#f2f2f2"))
    parts.append(_line(M, M + HEADER_H, M + content_w, M + HEADER_H, sw=1.5))

    # Watermark / stamp
    parts.append(
        '<g opacity="0.08" transform="translate(120 420) rotate(-18)">'
        + _t(0, 0, "RECOVERED", size=84, bold=True)
        + "</g>"
    )

    # Header text
    parts.append(_t(M + 10, M + 24, "BEDROCK FIELD MANUAL", size=18, bold=True))
    parts.append(_t(M + 10, M + 46, "RECOVERED NODE CHECKOUT (5-8 MINUTES)", size=10.5, bold=True))
    parts.append(_t(M + 10, M + 62, "Form: BRK-AN-001    Medium: UART    Status: Serviceable", size=9.0))

    # Header right box
    box_w = 182
    box_h = HEADER_H - 14
    box_x = M + content_w - box_w - 10
    box_y = M + 7
    parts.append(_rect(box_x, box_y, box_w, box_h, sw=1.0, fill="none"))
    parts.append(_t(box_x + 8, box_y + 18, "NODE: ESP32 (DOIT DEVKIT V1)", size=8.8, bold=True))
    parts.append(_t(box_x + 8, box_y + 34, f"LAMP:  GPIO{led_gpio}  (D{led_gpio})", size=8.8))
    parts.append(_t(box_x + 8, box_y + 48, f"RADIO: GPIO{radio_gpio}  (D{radio_gpio})", size=8.8))
    parts.append(_t(box_x + 8, box_y + 62, "HOME: p probe  s src  g pins", size=8.8))

    # Body layout guides
    body_top = M + HEADER_H + 16
    body_bottom = M + content_h - 14
    parts.append(_line(RIGHT_X - (COL_GAP / 2), body_top - 10, RIGHT_X - (COL_GAP / 2), body_bottom, stroke="#000", sw=1.0))

    # Left column content
    y = body_top
    x = LEFT_X + 6

    def sec(title: str) -> None:
        nonlocal y
        parts.append(_t(x, y, title, size=10.0, bold=True))
        y += 6
        parts.append(_line(x, y, LEFT_X + LEFT_W - 6, y, stroke="#000", sw=1.0))
        y += 14

    def line(text: str, *, size: float = 9.0, indent: int = 0, fill: str = "#000") -> None:
        nonlocal y
        parts.append(_t(x + indent, y, text, size=size, fill=fill))
        y += 12

    sec("MISSION")
    line(f"[ ] Verify lamp toggles (GPIO{led_gpio})")
    line(f"[ ] Verify radio pulses exist (GPIO{radio_gpio})")
    line("[ ] Capture a short trace (pins: s)")
    line("[ ] Optional: mirror radio -> lamp")

    y += 6
    sec("QUICK START")
    line("1) Plug in USB. Wait ~4s (autoexec).")
    line("2) Run: ./run_tui.sh")
    line("3) Press p (probe).")
    line("   Enter: explain. Then press s (source).", indent=14)
    line("4) Press g (pins).")
    line(f"   GPIO{led_gpio}: o then t.  GPIO{radio_gpio}: i then s.", indent=14)

    y += 6
    sec("PINS INSPECTOR KEYS")
    line("j/k   move selection")
    line("i/o   set input/output")
    line("t     toggle output pin")
    line("s     sample (CSV -> .bedrock/traces)")
    line("r     refresh pins")

    y += 6
    sec("NOTES / SAFETY")
    line("Keep all GPIO <= 3.3V.", fill="#000")
    line("Share GND between ESP32 and 555.", fill="#000")
    line("Avoid strapping pins: 2, 5, 12, 15.", fill="#000")
    line("Expected RADIO: edges>0; pot changes rate.", fill="#000")
    line("If connect fails: close Serial Monitor.", fill="#000")

    # Small wiring diagram (left column bottom)
    diag_w = LEFT_W - 12
    diag_h = 140
    diag_x = LEFT_X + 6
    diag_y = min(y + 10, body_bottom - diag_h - 4)
    parts.append(_rect(diag_x, diag_y, diag_w, diag_h, sw=1.0, fill="none"))
    parts.append(_t(diag_x + 8, diag_y + 16, "FIELD WIRING (ABSTRACT)", size=9.0, bold=True))
    parts.append(_line(diag_x + 8, diag_y + 22, diag_x + diag_w - 8, diag_y + 22, sw=1.0))

    node_x = diag_x + 12
    node_y = diag_y + 34
    node_w = 120
    node_h = 64
    parts.append(_rect(node_x, node_y, node_w, node_h, sw=1.0, fill="#fafafa"))
    parts.append(_t(node_x + 8, node_y + 18, "ANCIENT NODE", size=9.0, bold=True))
    parts.append(_t(node_x + 8, node_y + 34, f"GPIO{led_gpio} -> LAMP", size=8.4))
    parts.append(_t(node_x + 8, node_y + 48, f"GPIO{radio_gpio} <- RADIO", size=8.4))

    lamp_x = node_x + node_w + 32
    lamp_y = node_y + 14
    parts.append(_rect(lamp_x, lamp_y, 56, 22, sw=1.0, fill="none"))
    parts.append(_t(lamp_x + 8, lamp_y + 15, "LAMP", size=8.4, bold=True))
    parts.append(_line(node_x + node_w, node_y + 26, lamp_x, lamp_y + 11, sw=1.0))
    parts.append(_t(lamp_x + 2, lamp_y + 36, "LED+R", size=7.8))

    osc_x = lamp_x
    osc_y = node_y + 40
    parts.append(_rect(osc_x, osc_y, 56, 22, sw=1.0, fill="none"))
    parts.append(_t(osc_x + 8, osc_y + 15, "555", size=8.4, bold=True))
    parts.append(_line(osc_x, osc_y + 11, node_x + node_w, node_y + 48, sw=1.0))
    parts.append(_t(osc_x - 2, osc_y + 36, "0..3.3V", size=7.8))

    # Right column: recovered code listing
    rx = RIGHT_X + 6
    ry = body_top
    parts.append(_t(rx, ry, "RECOVERED PROGRAM LISTING (USER CODE)", size=10.0, bold=True))
    ry += 6
    parts.append(_line(rx, ry, RIGHT_X + RIGHT_W - 6, ry, sw=1.0))
    ry += 14

    code_size = 8.0
    code_lh = 10.0
    for ln in numbered:
        parts.append(_t(rx, ry, ln, size=code_size))
        ry += code_lh
        if ry > body_bottom - 4:
            break

    # Serial fallback box (uses protocol mode line commands)
    fb_w = RIGHT_W - 12
    fb_h = 112
    fb_x = RIGHT_X + 6
    fb_y = body_bottom - fb_h - 6
    parts.append(_rect(fb_x, fb_y, fb_w, fb_h, sw=1.0, fill="none"))
    parts.append(_t(fb_x + 8, fb_y + 16, "SERIAL FALLBACK (NO TUI)", size=9.0, bold=True))
    parts.append(_line(fb_x + 8, fb_y + 22, fb_x + fb_w - 8, fb_y + 22, sw=1.0))

    fy = fb_y + 36
    fs = 8.4
    gap = 12
    parts.append(_t(fb_x + 10, fy, "explain", size=fs)); fy += gap
    parts.append(_t(fb_x + 10, fy, "source", size=fs)); fy += gap
    parts.append(_t(fb_x + 10, fy, "pins", size=fs)); fy += gap
    parts.append(_t(fb_x + 10, fy, f"pin-mode {led_gpio} out", size=fs)); fy += gap
    parts.append(_t(fb_x + 10, fy, f"pin-write {led_gpio} 1   /   pin-write {led_gpio} 0", size=fs)); fy += gap
    parts.append(_t(fb_x + 10, fy, f"pin-mode {radio_gpio} in pull=none   /   pin-read {radio_gpio}", size=fs))

    # Footer
    footer = "END OF SHEET // DO NOT DISCARD // PRINT: 1 PAGE"
    parts.append(_t(M + 10, M + content_h - 10, footer, size=8.5, bold=True))

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    code_path = repo_root / "docs" / "demo" / "ancient_node_usercode.fs"

    if not code_path.exists():
        print(f"Error: Missing {code_path}", file=sys.stderr)
        return 2

    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        print("Error: rsvg-convert not found. Install librsvg (brew install librsvg).", file=sys.stderr)
        return 2

    tmp_dir = repo_root / "tmp" / "pdfs"
    out_dir = repo_root / "output" / "pdf"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    svg_path = tmp_dir / "bedrock_demo_ancient_node_quickref.svg"
    pdf_path = out_dir / "bedrock_demo_ancient_node_quickref.pdf"

    svg = build_svg(code_path)
    svg_path.write_text(svg, encoding="utf-8")

    subprocess.run(
        [rsvg, "-f", "pdf", "-o", str(pdf_path), str(svg_path)],
        check=True,
    )

    print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
