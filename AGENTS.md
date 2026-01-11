# Repository Guidelines

Computational Dignity thesis: self-describing embedded nodes (ESP32 smart node + ATtiny dumb nodes) speaking a
line-oriented UART protocol designed to be readable and maintainable “offline”.

## Project Structure

- Specs/docs: `PROJECT_SPEC.md`, `ROADMAP.md`, `PROTOCOL_REFERENCE.md`
- ESP32 smart-node (ESP32forth): `firmware/esp32/codignity.fs`
- Terminal tooling (Python/pyserial): `tools/terminal/`
- ATtiny dumb-node (C): `firmware/attiny/` (in progress)

## Dev Workflow (ESP32)

- Install Python deps (no activation required): `python3 -m venv .venv && .venv/bin/python -m pip install -r tools/terminal/requirements.txt`
  - Note: `.venv/bin/activate` must be sourced (`source ...`) to affect your shell; executing it won’t persist env changes.
- Flash ESP32forth (once): `arduino-cli --config-file tools/arduino/arduino-cli.yaml compile --fqbn esp32:esp32:esp32doit-devkit-v1 --build-path .arduino/build/esp32forth --upload -p /dev/cu.usbserial-0001 firmware/esp32/esp32forth/ESP32forth-7.0.6.19/ESP32forth`
- Load/reload `codignity.fs`: `.venv/bin/python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until prompt --preline repl --file firmware/esp32/codignity.fs`
  - Reload-safe: `codignity.fs` begins with a `cd-dev` + `forget` anchor to avoid dictionary-growth crashes.
- Smoke tests: `.venv/bin/python tools/terminal/codignity_serial.py --port /dev/cu.usbserial-0001 --until end --line "?"` and `--line "history"`
- Persist + auto-start: run `safe-save`; SAFE boot pin (GPIO4→GND) forces interactive `--> ` REPL.
- Avoid `--esp32-reset` unless the board is stuck (it can require a manual reset).

## Conventions

- Protocol: one request per line; responses may include `# err ...` but must always end with `! end`.
- TODOs: `TODO(thesis): <concrete next action>`; search with `rg "TODO\\(thesis\\)"`
- Git: small commits; branches `feat/...`, `fix/...`, `docs/...`; PRs include at least one real transcript for protocol changes.

## Forth References & Research

- Default reference: `FORTH_REFERENCE.pdf` for stack effects and core words.
- If unclear, run a tiny on-device probe (`depth .`, `see <word>`) or request network approval to consult
  Forth-2012 / ESP32forth docs.
- Document dialect gotchas here (or in `PROTOCOL_REFERENCE.md`) as soon as they’re discovered.
