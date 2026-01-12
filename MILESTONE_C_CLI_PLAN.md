# Milestone C Plan — Terminal CLI + ncurses TUI (Initial “Beautiful” Version)

**Branch:** `feat/milestone-c-cli`  
**Scope:** a “dumb terminal” safety-net + demo toolchain for Codignity nodes that is pleasant to use, scriptable, and
robust against the ESP32 serial gotchas we’ve already hit.

This document is written as an implementation spec for another model/engineer to execute.

---

## 0) Goals (what “done” looks like)

### Primary user outcomes
1. **Connect + identify node** in a single flow (auto-detect port, show node id/role/firmware, show mode).
2. **Safely load/update Codignity** (`firmware/esp32/codignity.fs`) without “doom spirals” (timeouts, spam, half-loads).
3. **Script & transcript everything**: every session can be recorded as plain text for regression + thesis artifacts.
4. **Snapshot/restore (terminal-side)**: capture a node’s *logical state* (meta + user defs + proof of safe-save) and
   replay it onto a clean node deterministically.
5. **A polished ncurses UI** with ASCII art banner, status bar, key hints, and guided flows (wizard-like).

### Acceptance (Milestone C)
- A transcript exists showing:
  - `probe` → identifies node id + confirms protocol mode
  - `snapshot` created
  - user change via `define` (tool captures the exact line)
  - `diff` displayed (terminal-side; live node vs snapshot)
  - `restore` onto a fresh state succeeds (meta + user defs restored), followed by `safe-save` and `restart`

---

## 1) Non-goals (explicitly deferred)

- Full-feature package distribution (pip/brew). Keep “run from repo” first.
- Terminal-side structural diff of decompiled `source` output (use stored define-lines instead).
- Fancy theming frameworks (`rich`, `textual`) unless we later decide the dependency is worth it.
- Hardware GUI, OTA updates, RS-485 routing (Milestone D).

---

## 2) Known hardware/protocol constraints (must design around)

### Serial-port open tends to reset the ESP32 (DOIT DEVKIT V1)
- Treat **port open as a reset** and plan for a boot window.
- ESP32forth’s `autoexec` waits ~3s for input; **any incoming byte during that window can prevent `revive`**.
  - Tool must support a **“quiet settle”** period (default 4s) where it opens the port and reads, but does not write.

### Two operational modes exist
- **REPL mode**: prompt shows `-->` and responses include ` ok`.
- **Codignity protocol mode**: commands respond with `! end` terminator, and prompt is suppressed.

### SAFE pin (GPIO4→GND) is the unbrickable escape hatch
- Tool must always be able to guide the user: “Hold SAFE + press EN to stay in REPL”.

---

## 3) UX principles (100-year legibility)

- Every operation is *visible*: show what is being sent and why (or clearly indicate when output is muted).
- Never hide irreversible actions behind a single keypress:
  - `recover`, `rollback`, `restart`, overwrite restore must require confirmation.
- Favor **plain-text artifacts**: snapshots and transcripts should be readable with `cat`.
- Prefer a persistent, single serial session for multi-step flows to avoid reset loops.

---

## 4) Repository layout (proposed)

Keep it minimal, but split responsibilities:

```
tools/terminal/
  codignity_serial.py          # low-level transport (line/file send, markers, scripting directives)
  codignity_cli.py             # new: argparse CLI entrypoint (non-interactive)
  codignity_tui.py             # new: curses UI entrypoint
  codignity/
    __init__.py
    session.py                 # new: SerialSession wrapper (open/quiet-settle/send/read)
    protocol.py                # new: detect mode, parse errors, helpers (meta/source/history)
    snapshot.py                # new: snapshot format + restore replay
    transcript.py              # new: transcript writer (headers, timestamps, redaction options)
    ui/
      screens.py               # new: curses screens & state machine
      widgets.py               # new: minimal widgets (menu, log pane, modal confirm)
      theme.py                 # new: color pairs + ASCII banner
```

If that feels too heavy for v1: merge `session.py/protocol.py/transcript.py` into a single `codignity_core.py`.

### Relationship to existing `codignity_serial.py` (avoid duplication)
Pick one approach and commit to it early:

- **Preferred:** move the serial primitives into `codignity/session.py` (importable), and make
  `tools/terminal/codignity_serial.py` a thin wrapper around that library for backwards compatibility.
- **Acceptable (v1):** keep `codignity_serial.py` as a standalone transport tool, but have CLI/TUI import shared
  helpers so marker logic and DTR/RTS behavior do not diverge.

Do **not** maintain two independent serial stacks long-term.

---

## 5) CLI spec (non-interactive)

Entry command (run from repo):
- `.venv/bin/python tools/terminal/codignity_cli.py <subcommand> ...`

### Common flags
- `--port /dev/cu.usbserial-0001` (optional; auto-detect if exactly one candidate)
- `--baud 115200` (default)
- `--settle 4.0` (default; “quiet settle” window)
- `--timeout 3.0` (per command)
- `--transcript <path>` (record session)
- `--yes` (skip confirmations where safe)

### Subcommands (v1)
1. `probe`
   - Opens port, quiet-settles, then:
     - tries protocol probe: `meta id` (expects `! end`)
     - if not in protocol, tries `revive` (expects ` ok`), then probes again
   - Output (human + machine):
     - human: summary lines
     - machine: `--json` option emits `{port, mode, codignity_loaded, node_id, role, ver}`
   - `ver` semantics:
     - `ver` comes from Codignity’s identity output (`! ver ...`), which is derived from `meta ver`.
     - If `meta ver` is missing, Codignity defaults to `codignity-0.1`.
     - If Codignity isn’t loaded, `ver` should be `null`/`unknown`.

2. `send "<line>"`
   - Sends exactly one protocol line (expects `! end`)
   - `--raw` option: REPL send (expects ` ok`)

3. `load`
   - Ensures REPL (if Codignity loaded: send `repl` in protocol; if plain ESP32forth: already in REPL)
   - Sends `firmware/esp32/codignity.fs` line-by-line, waiting for ` ok`
   - Option: `--no-mute` (normally mute file output to avoid transcript bloat)
   - Ends by running `validate` and optionally `safe-save` (`--persist`)

4. `meta get <key>` / `meta set <key> <value>` / `meta dump`
   - Pure protocol surface; always ends with `! end`

5. `define "<: name ... ;>"`
   - Actual wire syntax is **one line**: `define : name ... ;`
   - CLI UX should accept the **definition body** (starting with `:`) and send `define <body>` over the wire.
     - Example: `codignity define ": foo 123 ;"` sends `define : foo 123 ;`
   - Tool must also store the exact define-line in snapshot/transcript metadata (this is the only reliable “source”)
   - **Define capture (cross-invocation; required for snapshots):**
     - After a successful `define`, append the exact wire line (`define : name ... ;`) to a per-node defs log.
     - Path (repo-local, gitignored): `.codignity/defs/<node_id>.defs` (UTF-8, plain text).
     - Format:
       - Comment lines start with `#` (may include ISO8601 UTC timestamp + port).
       - One `define : ... ;` line per definition.
     - `node_id` comes from `meta id` (protocol) at the time of defining; if it cannot be read, fall back to `unknown`.

6. `history` / `source` / `explain`

7. `snapshot create --out <file>`
   - Captures:
     - `probe` info (id/role/ver)
     - `meta dump`
     - `source` (for inspection only)
     - **define-lines**:
       - Default: load from `.codignity/defs/<node_id>.defs` (see “Define capture” above).
       - Optional: merge additional define-lines from `--defs <file>` (one define per line).
       - De-dup by word name; if the same word appears multiple times, prefer the `--defs` version and record a note.
     - a marker that `safe-save` succeeded (tool can run it as part of snapshot)

8. `snapshot restore --in <file>`
   - Requires confirmation unless `--yes`.
   - Expected safe algorithm:
     1) quiet-settle
     2) enter REPL (user may need SAFE+EN if protocol is misbehaving)
     3) `load` Codignity (muted)
     4) apply `meta set ...` lines from snapshot
     5) apply define-lines from snapshot (using `define ...`)
     6) `validate`
     7) `safe-save`
     8) `restart`
     9) re-`probe` and print final id/role

9. `snapshot diff --in <file>`
   - Terminal-side diff of **current live node** vs the snapshot file (preview before restore).
   - Minimal diff rules (v1):
     - `meta`: added/removed/changed keys (string compare)
     - `defs`: compare by word name extracted from `define : <name> ... ;` lines
       - show `will add`, `already present` (collision risk with “new words only”), `missing on node`
   - **Diff noise suppression (choice: suppress core firmware defs by default):**
     - “Core firmware” here means **Codignity’s shipped definitions** (i.e. what lives in `firmware/esp32/codignity.fs`),
       not ESP32forth’s built-in kernel words.
     - When listing live defs, do *not* treat Codignity core words as “user diffs”.
     - Implementation: build a `baseline_defs` set by parsing the local firmware file `firmware/esp32/codignity.fs`
       for `: <name>` definitions; then compute `live_user_defs = live_defs_all - baseline_defs`.
     - Diff output should only include `live_user_defs` vs snapshot defs (and never dump baseline/core words).
     - If `baseline_defs` cannot be computed (missing firmware file or parse yields empty), omit the “live-only defs”
       section entirely and print a one-line warning explaining that core suppression is unavailable.
     - Robustness against version skew:
       - `snapshot create` should record a `# firmware_sha256: ...` header for the firmware file used to derive
         `baseline_defs` (default: `firmware/esp32/codignity.fs`).
       - `snapshot diff` should warn if the snapshot’s `firmware_sha256` does not match the current local firmware file,
         because core suppression may be inaccurate (old core words may appear as “live-only” user defs).

10. `tui` (launch ncurses UI)

### Restore error handling (must be explicit)
Default behavior should be **fail-fast** and **non-persistent**:
- If any `meta set` or `define` step returns `# err ...` (or lacks the expected terminator), **abort immediately**.
- Do **not** run `safe-save` after a failed restore step.
- Print the first failing command + device error payload + suggested next action (`recover`/`rollback 1`/SAFE+EN).

Optional (later): add `--continue-on-error` for debugging, but keep it off by default.

---

## 6) Snapshot & transcript formats (plain text)

### Transcript (`.txt`)
- Keep as human readable, similar to existing `tools/terminal/transcripts/`.
- Header:
  - ISO8601 UTC date, git branch/commit, port, tool version.
- Body:
  - `> <sent line>`
  - then raw device output (already includes `! end` or ` ok`)

### Snapshot (`.cdsnap` text, v1)
Proposed format (simple sections, no JSON required):

```
# Codignity Snapshot v1
# date: 2026-...
# node: id=node1 role=gateway ver=thesis-0.1

[meta]
id node1
role gateway
pins gpio4
units ticks

[defs]
define : foo 123 ;
define : bar foo 1+ ;

[notes]
safe-save ok
```

Restore uses `[meta]` and `[defs]` only; `[notes]` is informational.

---

## 7) TUI (ncurses) spec

### Visual design (v1)
- Top banner: ASCII art “CODIGNITY” + short subtitle (device + port).
- Left pane: “Actions” menu (arrow keys / j-k; Enter to select).
- Right pane: scrollable log/output (tail-like, with search `/` optional later).
- Bottom status bar:
  - connection state, mode (REPL/PROTOCOL), node id, last op status, key hints.

### Core screens / flows
1. **Home / Connect**
   - Port selector (auto-detect list, allow refresh).
   - On connect: quiet-settle countdown + “do not press keys” hint.
   - Then probe result rendered (id/role/ver).

2. **Load Codignity**
   - If already loaded: show “already loaded”.
   - If not loaded: show progress bar (line count), muted output by default.
   - End with “Persist?” prompt (runs `safe-save` and `restart`).

3. **Meta editor**
   - Table view of key/value pairs.
   - “Edit value” modal (single-token constraint for now).

4. **Define**
   - Single-line editor with live character count and “stack effect reminder” area.
   - On success: append define-line to session defs list (used by snapshot).

5. **Inspect**
   - `?`, `explain`, `source`, `history` rendered in log pane with paging.

6. **Snapshot/Restore**
   - Snapshot: choose output path, show included meta + defs count, optionally run `safe-save`.
   - Restore: pick snapshot file, show diff summary (meta changes + defs count), confirm, run restore algorithm.

### Implementation details (curses)
- Use a simple state machine:
  - `AppState = {screen, port, session, mode, node_info, log_lines, session_defs, last_error}`
- Keep serial I/O off the UI loop:
  - A worker thread reads from serial and pushes bytes/lines into `queue.Queue`
  - UI thread renders at ~20–30 FPS and consumes queue updates.
- Provide a global “panic exit” key: `q` always exits cleanly (closing serial).

---

## 8) Implementation sequence (recommended commits)

### Phase 1 — Core library (no UI)
1. Create `tools/terminal/codignity/session.py`:
   - `SerialSession.open(port, baud, settle_s, quiet=True)`
   - `send_line(line)` + `read_until(marker, timeout_s)`
   - helpers: `send_protocol(line)->str`, `send_repl(line)->str`
2. Create `tools/terminal/codignity/protocol.py`:
   - `probe(session)->ProbeResult`
   - `ensure_codignity(session)` (tries `meta id`, `revive`, etc.)
3. Create `tools/terminal/codignity/transcript.py`:
   - context manager that writes `> line` and raw output
4. Implement `tools/terminal/codignity_cli.py` for: `probe`, `send`, `meta`, `history`, `source`, `explain`.

### Phase 2 — Load + persistence
5. Implement `load`:
   - enter REPL if needed (protocol `repl`)
   - send `firmware/esp32/codignity.fs` with muted output
   - verify with protocol probe + `validate`
   - optional `--persist` runs `safe-save` + `restart`

### Phase 3 — Snapshots
6. Implement snapshot parser/writer in `snapshot.py`:
   - `Snapshot.load(path)` / `Snapshot.save(path)`
7. Implement `snapshot create` and `snapshot restore` CLI.
   - Restore must be confirmation-gated.

### Phase 4 — TUI
8. Implement `tools/terminal/codignity_tui.py` and `ui/` screens.
9. Add a small `README` section or `AGENTS.md` note for running `tui`.

### Phase 5 — Polish
10. Add `--json` outputs for scripting.
11. Improve error messages with “next action” suggestions (SAFE+EN, close Serial Monitor, etc.).

---

## 9) Validation (hardware + artifacts)

- Add a `tools/terminal/transcripts/milestone-c-smoke.txt` produced by the CLI:
  - connect/probe → define → snapshot → restore → verify → safe-save
- Keep transcripts short and readable (mute bulk loads; only show high-level steps).

---

## 10) Git workflow expectations (for implementation)

- Work on `feat/milestone-c-cli`.
- Small commits with messages like:
  - `feat(cli): add probe/send commands`
  - `feat(cli): implement load + persist`
  - `feat(cli): snapshot create/restore`
  - `feat(tui): add ncurses home + log panes`
- Any stubbed behavior must be marked `TODO(thesis): <concrete next action>`.
