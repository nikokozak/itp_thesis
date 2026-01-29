# Milestone E Plan — Hardware Affordances (Pins + Introspection + “No Forth Required” UI)
**Branch:** `feat/milestone-e-affordances` (recommended)  
**Goal:** Make the system *useful without writing Forth*, by exposing stable, inspectable MCU affordances (pin map,
pin status, ownership, safe manipulation) and rendering them in the CLI/TUI as first‑class workflows.

This document is an implementation spec intended to be executed by another engineer/model (Claude).

---

## 0) Core Outcomes (“done” looks like)

### A. Pin introspection without programming
1. User can run **`pins`** (CLI/TUI) and see:
   - A **board footprint view** (two header columns for DOIT ESP32 DEVKIT V1) with pins listed in a stable order.
   - Live pin **state** (mode/level/pull/owner) for the GPIO pins that exist on the footprint.
2. User can run **`pin-status D4`** (or `GPIO4`, or `4`) and get a single structured response.

### B. Pin ownership model (“is this pin used by Bedrock?”)
3. Firmware exposes a **pin registry** that tracks *Bedrock-level ownership* (not raw ESP32forth kernel usage):
   - `owner` is a single-token label (e.g., `button`, `i2c`, `user`).
   - Registry is updated by Bedrock pin helper commands (and by any higher-level Bedrock modules we write).

### C. Safe pin manipulation helpers
4. Firmware provides minimal safe helpers:
   - `pin-mode <pin> in|out [pull=up|down|none]`
   - `pin-read <pin>`
   - `pin-write <pin> 0|1`
   - `pin-claim <pin> <owner>` / `pin-release <pin>`
5. CLI/TUI provides interactive flows for these operations (no Forth required).

### Acceptance transcript (required)
A single transcript proves:
1. `probe` succeeds.
2. `pins` shows a footprint.
3. Button on GPIO4 shows up as `D4`/`GPIO4` with `level=0/1` when pressed/released.
4. `pin-claim D4 button` marks owner.
5. `pin-status D4` returns structured state and owner.

---

## 1) Design Decisions (non-negotiables for long-term legibility)

### 1.1 Physical layout lives in the terminal, not the MCU
The MCU cannot infer “clockwise header order” reliably across dev boards. Therefore:
- Firmware reports **GPIO states** and **board identity**.
- Terminal tooling contains **board manifests** that define:
  - Physical header geometry (left/right columns, order, labels).
  - Label → GPIO mapping (e.g., `D4` → `gpio=4`).
  - Non-GPIO pins (3V3, VIN, GND, EN) for display only.

### 1.2 Protocol output must be parseable and extensible
Use a stable, future-proof format:
- Multi-line blocks start with `!`, end with `! end`.
- Per-pin lines use **key=value tokens** so new fields can be added without breaking parsers.

Example:
```
pins
! board doit-esp32-devkit-v1
! pin gpio=4 label=D4 mode=in level=1 pull=up owner=button flags=safe
! end
```

### 1.3 “Ownership” is Bedrock-scoped
The registry indicates what *Bedrock* (and Bedrock-wrapped code) claims, not what the ESP32 kernel happens to do.
This is the only honest definition unless we fork/replace ESP32forth’s GPIO words.

---

## 2) Firmware Work (ESP32forth / `firmware/esp32/bedrock.fs`)

### 2.1 Add a `board` meta key (single token)
- Add `meta board <board-id>` support (already handled by generic `meta`).
- Update `?` and `explain` to emit optional:
  - `! board <board-id>` if set.
- Default is omitted (terminal falls back to “unknown board” and prints a warning).

### 2.2 Pin registry (RAM only v1)
Implement fixed-size arrays for GPIO 0..39:
- `br-pin-mode[40]` → enum: `unknown/in/out/adc/i2c/uart/pwm/reserved`
- `br-pin-pull[40]` → enum: `none/up/down`
- `br-pin-owner[40]` → fixed-length string entry (e.g., 16 bytes + length byte)
- `br-pin-flags[40]` → bitmask (safe, strapping, input-only, flash, etc)

Notes:
- Populate `flags` table statically for known ESP32 constraints:
  - GPIOs used for flash/PSRAM, strapping pins, and input-only pins.
  - Mark `GPIO4` with `flags=safe` (SAFE boot).
- v1 can keep registry **non-persistent**; later we can persist owners/modes if needed (not required to make it useful).

### 2.3 Pin token parsing (`D4` / `GPIO4` / `4`)
Add a helper:
- `br-parse-gpio ( a n -- gpio f )`
  - Accept decimal `0..39`
  - Accept `D<n>` (case-insensitive)
  - Accept `GPIO<n>` (case-insensitive)
  - Return `f=0` on parse failure

### 2.4 New protocol commands
Implement these as protocol commands near the existing `? s n d c` block.

#### `pins` (bulk dump)
- Output:
  - optional `! board <board-id>` (from `meta board`)
  - For each GPIO 0..39: one `! pin ...` line
  - `! end`
- Each `! pin` line must include at least:
  - `gpio=<n>`
  - `mode=<token>` (from registry; `unknown` if never set)
  - `level=<0|1|->` (use `digitalRead` when safe; otherwise `-`)
  - `pull=<none|up|down|->` (from registry)
  - `owner=<token|->`
  - `flags=<comma,list>` (single token; commas only)

#### `pin-status <pin>`
- Output:
  - `! pin ...` (same shape as pins line)
  - `! end`
- Errors:
  - `# err pin_syntax` (missing pin)
  - `# err pin_range` (out of range)

#### `pin-claim <pin> <owner>`
- Behavior:
  - If unowned: set owner.
  - If already owned by same owner: ok (idempotent).
  - If owned by different owner: `# err pin_owned`.
- Output: `! ok`, `! end`

#### `pin-release <pin>`
- Clears owner; output `! ok`, `! end` (idempotent).

#### `pin-mode <pin> in|out [pull=up|down|none]`
- Uses `pinMode` and `gpio_pullup_en/gpio_pulldown_en` (available in ESP32forth).
- Updates registry.
- Safety rule: refuse to set mode on pins with `flags` indicating flash/PSRAM unless a future `--force` exists.

#### `pin-read <pin>`
- Uses `digitalRead`.
- Output:
  - `! value <0|1>`
  - `! end`

#### `pin-write <pin> 0|1`
- Ensures `mode=out` (sets if unknown, or errors if `mode=in` and owned by someone else).
- Uses `digitalWrite`.
- Output: `! ok`, `! end`

### 2.5 Update `validate` (optional)
Add checks that the SAFE GPIO is still configured as input with pull-up when in protocol mode (warning only).

---

## 3) Terminal Tooling (Python)

### 3.1 Board manifests (new module)
Add a new package:
- `tools/terminal/bedrock/boards/`
  - `__init__.py`
  - `doit-esp32-devkit-v1.json` (or `.toml`)

Manifest fields:
- `board_id`: `doit-esp32-devkit-v1`
- `display_name`
- `pins`: list of entries in physical order (clockwise)
  - `pos`: e.g. `L1..L15`, `R1..R15`
  - `label`: e.g. `3V3`, `GND`, `EN`, `D4`
  - `gpio`: integer or null
  - `kind`: `power|gnd|signal|control`
  - `notes`: optional

**DOIT ESP32 DEVKIT V1 (30‑pin) starter mapping (verify against silkscreen):**

Assume the board is oriented with **USB at the bottom** and the antenna at the top. Define positions as:
- `L1..L15`: left header **top → bottom**
- `R1..R15`: right header **top → bottom**

Left header (top → bottom):
- `L1` `3V3` (power)
- `L2` `GND` (ground)
- `L3` `D15` `gpio=15`
- `L4` `D2` `gpio=2`
- `L5` `D4` `gpio=4` *(SAFE pin in this thesis build)*
- `L6` `RX2` `gpio=16`
- `L7` `TX2` `gpio=17`
- `L8` `D5` `gpio=5`
- `L9` `D18` `gpio=18`
- `L10` `D19` `gpio=19`
- `L11` `D21` `gpio=21`
- `L12` `RX0` `gpio=3`
- `L13` `TX0` `gpio=1`
- `L14` `D22` `gpio=22`
- `L15` `D23` `gpio=23`

Right header (top → bottom):
- `R1` `VIN` (power)
- `R2` `GND` (ground)
- `R3` `D13` `gpio=13`
- `R4` `D12` `gpio=12`
- `R5` `D14` `gpio=14`
- `R6` `D27` `gpio=27`
- `R7` `D26` `gpio=26`
- `R8` `D25` `gpio=25`
- `R9` `D33` `gpio=33`
- `R10` `D32` `gpio=32`
- `R11` `D35` `gpio=35` *(input‑only)*
- `R12` `D34` `gpio=34` *(input‑only)*
- `R13` `VN` `gpio=39` *(input‑only; ADC)*
- `R14` `VP` `gpio=36` *(input‑only; ADC)*
- `R15` `EN` (control / reset enable; not a GPIO)

### 3.2 Protocol parsing helpers
Add `bedrock/pins.py`:
- `PinState` dataclass: gpio, label?, mode, level, pull, owner, flags(set)
- `parse_pin_kv(line: str) -> PinState`
- `parse_pins_response(text: str) -> tuple[board_id|None, dict[int, PinState]]`

### 3.3 CLI additions (`tools/terminal/bedrock_cli.py`)
Add subcommands:
- `pins`:
  - Calls protocol `pins`
  - Loads board manifest via `meta board` (or from probe result if `?` includes `board`)
  - Renders footprint ASCII with per-pin state (owner/mode/level)
- `pin status <pin>`
- `pin claim <pin> <owner>`
- `pin release <pin>`
- `pin read <pin>`
- `pin write <pin> <0|1>`
- `pin mode <pin> <in|out> [--pull up|down|none]`

Keep output:
- Human readable by default; add `--json` where useful (PinState list).

### 3.4 TUI additions (`tools/terminal/bedrock/ui/screens.py`)
Add a new screen/state:
- `Screen.PINS` and `Action.PINS`

UI behavior:
- From HOME: key `g` opens Pins Inspector (or `P` submenu).
- Pins Inspector renders:
  - Footprint (two columns) using manifest + latest PinState table.
  - A details box for the selected pin.
  - Key actions (context-aware):
    - arrows/jk: move selection
    - `r`: refresh pins (calls `pins`)
    - `c`: claim (prompts for owner)
    - `u`: unclaim/release
    - `t`: toggle (only if safe)
    - `i`: set input (optional pull)
    - `o`: set output
    - `Esc`: back to home

Safety UX:
- Highlight strapping/flash pins in warning color.
- Require confirm before changing mode/value on “danger” pins.

Performance:
- Use the existing persistent SerialSession; pins refresh should be a single protocol round-trip.

---

## 4) Documentation + Training (minimal, Bedrock-specific)

Create `docs/FORTH_FOR_BEDROCK.md` (short, practical):
- Stack effect notation, `dup drop swap over rot -rot`
- Defining words via Bedrock `define`
- Using Bedrock helpers (`pin-*`, `meta`, `history`)
- How to inspect (`see`, `words`, `depth`) safely
- 10-minute “make something” exercises

This is not a full Forth book; it’s a runway into *Bedrock’s* dialect and workflow.

---

## 5) Implementation Phases (recommended order)

1. Firmware: `board` meta emission + `pin-status` (single pin)
2. Firmware: registry + `pins` bulk dump
3. CLI: `pins` + `pin-status` parsing and output
4. TUI: Pins Inspector screen (read-only refresh first)
5. Firmware: `pin-claim/release`, `pin-mode/read/write`
6. TUI: interactive pin actions + safety confirmations
7. Docs: `docs/FORTH_FOR_BEDROCK.md`

Each phase must ship with at least one new transcript artifact.
