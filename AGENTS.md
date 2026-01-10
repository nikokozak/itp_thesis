# Repository Guidelines

## Project Structure & Modules

This repository is currently documentation-first. Key files live at the repo root:

- `PROJECT_SPEC.md`: thesis/vision + system architecture (source of truth for intent)
- `PROTOCOL_REFERENCE.md`: command/response tables and wire-format examples (source of truth for syntax)
- `CONTEXT_TRANSFER.md`: short “paste into a new chat” summary to regain context quickly

When adding implementation artifacts, keep them separated and predictable:
- `firmware/esp32/`: smart node (ESP32forth baseline)
- `firmware/attiny/`: dumb node / sensor adapters (C baseline)
- `tools/terminal/`: host/terminal CLI + snapshots/transcripts
- `docs/`: longer-form specs, diagrams, transcripts, decisions

## Build, Test, and Development Commands

- Search across specs: `rg "explain|source|history|! end|validate"`
- Optional PDF export (requires `pandoc`): `pandoc PROJECT_SPEC.md -o PROJECT_SPEC.pdf`
- Build + flash ESP32forth (uses workspace-local Arduino core v1.0.6): `arduino-cli --config-file tools/arduino/arduino-cli.yaml compile --fqbn esp32:esp32:esp32doit-devkit-v1 --build-path .arduino/build/esp32forth --upload -p /dev/cu.usbserial-0001 firmware/esp32/esp32forth/ESP32forth-7.0.6.19/ESP32forth`
- Load MVP protocol words: `. .venv/bin/activate && python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until prompt --file firmware/esp32/codignity.fs`
- Smoke-test protocol: `. .venv/bin/activate && python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until end --line "?"`

## Coding Style & Naming Conventions

- Markdown: use ATX headings (`##`), fenced code blocks for transcripts, and keep lines ~100 chars.
- Protocol literals: wrap commands, pins, and tokens in backticks (e.g., `@name cmd`, `! end`, `# error`).
- Files: keep high-level docs in `UPPER_SNAKE.md`; use `kebab-case.md` for working notes if added.
- Code (when added): prefer small files, explicit names, and stable interfaces; no “magic” generators.

## Testing Guidelines

There are no automated tests yet. For firmware/protocol changes, include a manual test plan in PRs with:
example request/response transcripts and any backward-compatibility notes.

## Planning & TODO Discipline

- For any non-trivial change, write a short, checkable plan (in the PR description, or in a tracking issue).
- If you stub/skip work, add a `TODO(thesis): ...` with a concrete next action (and link/ID if available).
  Find them with: `rg "TODO\\(thesis\\)"`

## Version Control & PR Guidelines

- Branches: keep `main` releasable; use short-lived branches like `feat/<area>-<topic>`, `docs/<topic>`,
  `fix/<topic>`, `chore/<topic>`.
- Commits: use Conventional Commits (e.g., `docs: clarify dump response`, `protocol: add safe-save details`).
- PRs: include a crisp description, linked context, and at least one real transcript for protocol changes.
  Update both `PROJECT_SPEC.md` and `PROTOCOL_REFERENCE.md` when semantics change.

## Agent-Specific Notes (Codex CLI)

- Use a skill only when explicitly requested or clearly applicable; available: `skill-creator`, `skill-installer`.
- Prefer small, targeted file reads and `rg` searches over bulk-loading entire documents.
