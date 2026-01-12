# Thesis Repository (Codignity)

This repo contains the Codignity firmware and tooling for ESP32-based sensor nodes.

## Current Work

Active branch: `feat/milestone-c-cli`
Implementation spec: `MILESTONE_C_CLI_PLAN.md`
Protocol reference: `PROTOCOL_REFERENCE.md`

## Directory Structure

- `firmware/esp32/` — Forth source for Codignity (`codignity.fs`)
- `tools/terminal/` — Python CLI/TUI tooling (Milestone C target)
- `docs/` — Design documents and transcripts

## Development

### Python Environment

```bash
cd tools/terminal
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run from repo root:
```bash
.venv/bin/python tools/terminal/codignity_cli.py <subcommand>
```

### Key Constraints (ESP32 Serial)

1. **Port open resets ESP32** — Plan for boot window; use quiet settle (4s default).
2. **Two modes exist** — REPL (`-->`, ` ok`) vs Protocol (`! end` terminator).
3. **SAFE pin (GPIO4→GND)** — Unbrickable escape hatch; guide user when needed.

### Code Style

- Small, focused commits: `feat(cli): add probe command`
- Mark stubs with `TODO(thesis): <concrete next action>`
- Fail-fast error handling; no silent failures
- Plain-text artifacts (transcripts, snapshots) readable with `cat`

### CRITICAL: Do Not Modify Working Code

**DO NOT, UNDER ANY CIRCUMSTANCES, CHANGE OR REFACTOR EXISTING CODE.**

Existing code (e.g., `codignity_serial.py`) works perfectly. If something doesn't work, it is likely being used incorrectly. Add new code alongside existing code; do not refactor or "improve" what already works.

## Testing

Hardware-in-loop testing with actual ESP32 nodes. Transcripts in `tools/terminal/transcripts/` serve as regression artifacts.
