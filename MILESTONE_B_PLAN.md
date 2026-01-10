# Milestone B2 Plan — Self-Describing Smart Node

**Objective:** make the ESP32 smart node’s `?`, `explain`, `source`, and `history` reflect *its persisted state* after
power-cycling, while keeping the system legible and un-bloated.

## Scope (what we will implement)

1. **User-only programming boundary**
   - Create a dedicated vocabulary (e.g., `cd-user`) for all user-defined words.
   - Change `define` so it compiles into `cd-user` only.
   - Enforce “new words only”: reject a `define` if the target name already exists in `cd-user` or is reserved
     (`?`, `s`, `n`, `d`, `c`, `cd-node`, `save`, `safe-save`, `recover`, `rollback`, `restart`, `repl`, etc.).
   - Keep the rest-of-line behavior (single-line `define`) to stay protocol-simple.

2. **Metadata model + persistence**
   - Store node metadata as a small, append-free, human-readable file on SPIFFS:
     - Proposed path: `/spiffs/codignity.meta`
     - Format: one `key value` per line (single-token values; no quoting v1).
   - Load metadata on boot (or on first use) into RAM variables.
   - Make `?` and `explain` generate output from these fields (with safe defaults if missing).
   - Add a small protocol surface for configuration:
     - `meta` → dump all metadata as `! key value … ! end`
     - `meta <key>` → dump one key
     - `meta <key> <value>` → set and persist (and append to history)

3. **Persistent history**
   - Maintain an append-only history log on SPIFFS:
     - Proposed path: `/spiffs/codignity.history`
     - One line per event (human readable; v1 timestamp can be `ms-ticks`).
   - Events to record: `define`, `save`, `safe-save`, `meta set`, `recover`, `rollback`, `restart`.
   - Implement `history` to stream file contents as `! <line>` … `! end` (no parsing required).

4. **Complete `source`**
   - Keep core protocol words decompiled (fixed list is acceptable).
   - Add enumeration of all words in `cd-user` and emit them via `see-vocabulary` (prefixed with `! `).
   - Ensure `source` remains stable even if user words change.

## Non-goals (explicitly deferred)

- Multi-node routing (`@name cmd`) beyond current stubs.
- Terminal-side diff/confirm tooling (Milestone C).
- Rich metadata schema (nested/JSON) or values with spaces/quoting (v2).
- Real sensor/timestamp integration (separate TODOs already exist).

## Safety + invariants

- Protocol responses always end with `! end`.
- `safe-save` must continue to persist protocol auto-start (`cd-boot`) and remain the recommended persistence action.
- SAFE pin (GPIO4) always overrides auto-start and drops to the interactive `--> ` REPL.
- `repl` must always exit protocol mode cleanly (escape hatch).

## Acceptance tests (required transcripts)

1. **Power-cycle persistence**
   - Set metadata: `meta id node1`
   - `safe-save`
   - `restart` (or power-cycle)
   - Verify: `?` and `explain` reflect `node1` without reloading `codignity.fs`.

2. **User-only define**
   - `define : foo 123 ;`
   - Verify: `source` includes `foo` definition.
   - Verify: `define : foo 456 ;` is rejected with a clear `# err` and `! end`.
   - Verify: attempts to define reserved names are rejected.

3. **History durability**
   - After `define`, `meta set`, `safe-save`, run `history`
   - Verify: events appear after `restart`.

## Implementation order (to keep risk low)

1. Add `cd-user` vocabulary + enforce define boundary (no persistence changes yet).
2. Add history file append + `history` reads from file.
3. Add metadata file + `meta` command + update `?`/`explain`.
4. Extend `source` to enumerate `cd-user` and keep output stable.
5. Update protocol reference and add saved transcripts.
