# Roadmap (Prioritized)

This is a working implementation plan for the thesis “Computational Dignity”. The goal is to reach a **reliable
demo** first, then deepen capability without adding bloat.

## Milestone A — Unbrickable Prototype (highest priority)

**Goal:** A smart node that cannot be accidentally “lost”, even with bad `define`s.

1. **Boot + mode control**
   - Implement SAFE boot pin check (hold low on power-up → skip auto-start, drop to `--> ` prompt).
   - Add explicit `restart` command for protocol mode (reboot deterministically).
   - Add a clean escape hatch from protocol mode (e.g., reserved command that returns to interactive prompt).
2. **Recovery**
   - Implement `recover` (factory reset): delete the saved image and reboot.
   - Implement `rollback N` (start with `N=1`): restore last-known-good snapshot.
3. **Safer persistence**
   - Upgrade `safe-save` to create a “last-known-good” snapshot before updating the primary image.
   - Ensure `validate` checks stack hygiene and that core protocol words are callable.

**Acceptance:** A transcript demonstrates `recover` and `rollback 1` restoring a working node after intentionally
breaking it with `define`.

## Milestone B — Self-Describing Node (core thesis)

**Goal:** The node explains itself from its own stored state, not from hardcoded strings.

Implementation plan: `MILESTONE_B_PLAN.md`

1. **Metadata model**
   - Minimal, explicit fields (e.g., `node-id`, `role`, `pins`, `sample-units`, `children`).
   - `?` and `explain` derive output from this model.
2. **Complete `source`**
   - Make `source` enumerate all relevant words (protocol + user-defined), not a fixed list.
   - Prefer a dedicated vocabulary/wordlist for user code to keep enumeration stable.
3. **Durable `history`**
   - Persist history to flash as append-only text (human-readable), with minimal timestamps.
   - Add `diff N` only if it remains simple; otherwise keep diff terminal-side (see Milestone C).

**Acceptance:** Power-cycle the node; `source`, `explain`, and `history` still describe the current configuration.

## Milestone C — Terminal Tooling (safety net + demo)

**Goal:** A “dumb terminal” workflow that can program/restore nodes without an IDE.

1. `tools/terminal/` CLI with subcommands: `probe`, `send`, `snapshot`, `restore`, `define` (with diff + confirm).
2. Transcript recording (`docs/` or `tools/terminal/transcripts/`) used as regression tests for protocol changes.
3. Minimal packaging instructions for running on a Raspberry Pi (no cloud, no GUI required).

**Acceptance:** Connect → automatic snapshot; modify via `define` → diff shown; restore from snapshot works.

## Milestone D — Multi-Node Routing + Dumb Node

**Goal:** Demonstrate `@name cmd` routing and a minimal ATtiny “sensor adapter” node.

1. Implement child registry on the smart node (`?` includes children; routing errors are explicit).
2. Hardware: pick TTL vs RS-485 for the demo, document the wiring, and implement a working route for one child.
3. Add `firmware/attiny/` C baseline implementing `? s n d c validate` over UART with a ring buffer.

**Acceptance:** From the terminal, `@sensor s` returns the dumb node’s sample and terminates with `! end`.

## Working rules (for implementation)

- Each milestone gets its own branch (`feat/<milestone>-<topic>`), with small commits and real transcripts.
- Any stubbed work must be marked `TODO(thesis): ...` with a concrete next action.
