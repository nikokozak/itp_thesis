# Repository Guidelines

Thesis repo for **Computational Dignity**: self-describing embedded nodes (ESP32 + ATtiny) over UART.

## Project Structure & Module Organization

Start here:
- `PROJECT_SPEC.md`: thesis vision + architecture
- `PROTOCOL_REFERENCE.md`: protocol syntax + examples
- `CONTEXT_TRANSFER.md`: “paste into a new chat” project summary
- `ROADMAP.md`: prioritized implementation milestones
- `MILESTONE_B_PLAN.md`: Milestone B2 implementation plan

Implementation and tooling:
- `firmware/esp32/`: ESP32forth baseline + `codignity.fs`
- `firmware/attiny/`: ATtiny C firmware (planned/ongoing)
- `tools/terminal/`: serial tooling + transcripts

## Build, Test, and Development Commands

- Host deps: `python -m venv .venv && . .venv/bin/activate && pip install -r tools/terminal/requirements.txt`
- Flash ESP32forth (Arduino core pinned in `tools/arduino/arduino-cli.yaml`): `arduino-cli --config-file tools/arduino/arduino-cli.yaml compile --fqbn esp32:esp32:esp32doit-devkit-v1 --build-path .arduino/build/esp32forth --upload -p /dev/cu.usbserial-0001 firmware/esp32/esp32forth/ESP32forth-7.0.6.19/ESP32forth`
- Load protocol words: `. .venv/bin/activate && python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until prompt --file firmware/esp32/codignity.fs`
- Protocol auto-start: run `safe-save` to persist and enable auto-start (`cd-boot`).
- SAFE mode: hold GPIO4 to GND at boot for `--> ` REPL.
- Prompt missing: run `also internals 1 arrow ! only forth`.
- Smoke-test: `. .venv/bin/activate && python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until end --line "?"`

## Coding Style & Naming Conventions

- Markdown: use ATX headings (`##`), fenced code blocks for transcripts, and keep lines ~100 chars.
- Protocol literals: wrap commands, pins, and tokens in backticks (e.g., `@name cmd`, `! end`, `# error`).
- Files: keep high-level docs in `UPPER_SNAKE.md`; use `kebab-case.md` for working notes if added.
- Code (when added): prefer small files, explicit names, and stable interfaces; no “magic” generators.

## Testing Guidelines

No automated tests yet; for protocol changes, include real request/response transcripts in PRs.

## Planning & TODO Discipline

- For any non-trivial change, write a short, checkable plan (in the PR description, or in a tracking issue).
- If you stub/skip work, add a `TODO(thesis): ...` with a concrete next action (and link/ID if available).
  Find them with: `rg "TODO\\(thesis\\)"`

## Version Control & PR Guidelines

- Branches: keep `main` releasable; use short-lived branches like `feat/<area>-<topic>`, `docs/<topic>`,
  `fix/<topic>`, `chore/<topic>`.
- Workflow: commit in small steps; merge via PR; avoid rewriting shared history.
- Commits: Conventional Commits (`chore:`, `docs:`, `feat:`, `fix:`).
- PRs: include rationale, linked context, and at least one request/response transcript for protocol changes.

## Agent-Specific Notes (Codex CLI)

- Use a skill only when explicitly requested or clearly applicable; available: `skill-creator`, `skill-installer`.
- Prefer small, targeted file reads and `rg` searches over bulk-loading entire documents.
