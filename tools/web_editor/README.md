# Bedrock Web Editor (Prototype)

Implementation of the thesis spec in `forth-editor-spec.md`, evolving toward a Bedrock-friendly workflow.

This prototype includes:
- TypeScript Forth engine with data/return stacks, memory, dictionary, colon compiler, control-flow compilation, instrumentation events, and snapshot/restore.
- React + CodeMirror 6 UI with code pane, REPL, timeline, dictionary browser, word inspector, dataflow/annotation views, and memory inspector.
- Analysis pipeline for stack-effect inference, branch diagnostics, semantic label propagation, and cross-reference tracking.
- Runtime undo/redo (snapshot-based) separated from CodeMirror text undo.
- REPL pre-execution preview and REPL inline assertions: `TEST{ ... -> ... }TEST`.
- Multi-file workspace (p5.js-style): file tabs, Project panel, Problems list, Outline, and export/import.
- External word stubs for dialect/device words (helps analysis stay useful when targeting ESP32forth/Bedrock).

## Quick Start

```bash
npm install
npm run dev
```

Open the Vite URL printed in the terminal.

## Build & Lint

```bash
npm run lint
npm run build
npm run test:run
```

Fuzz intensity is tunable:

```bash
FORTH_FUZZ_RUNS=500 FORTH_SNAPSHOT_RUNS=300 npm run test
```

Note: Vite 7 prints a Node engine warning on Node `21.x`. Recommended versions are `20.19+` or `22.12+`.

## Keyboard Highlights

- `Mod+Enter`: execute selection/current line from code pane
- `Mod+Shift+Enter`: execute project buffer (all files, in order)
- `Run Project` button: runs the project buffer with stack reset + timeline reset
- `Clear Timeline` button: clears only the timeline history
- REPL `Enter`: run line
- REPL `Up/Down`: history
- REPL `Ctrl/Cmd+Z`: runtime undo
- REPL `Ctrl/Cmd+Shift+Z`: runtime redo
- `Ctrl/Cmd+\``: focus REPL input
- `Ctrl/Cmd+A`: toggle code annotations
- `Ctrl/Cmd+D`: toggle dictionary panel
- `Ctrl/Cmd+P`: open Project panel

## Implemented vs Deferred

Implemented MVP behavior for all core subsystems. Deferred items include:
- Full ANS-accurate semantics for advanced dynamic features (`CREATE...DOES>`, fully analyzable `EXECUTE`/metaprogramming paths)
- Arrow-drawing token-to-token overlay (current implementation uses token highlights + step views)
- Advanced docking/rearrangeable panel system

## Usability Notes

- Workspace state is persisted in local storage (files/docs/external stubs). Use the Project panel to export/import.
- Dictionary Browser defaults to discovery mode and only shows full lists when requested.
- Timeline has slider scrubbing, per-step word context, and source labels (`repl`/`selection:*`/`project`).
- Timeline supports explicit filter modes: `Focused` (execute/error checkpoints) and `Full Trace` (all runtime events), including a hidden-event count when focused mode is active.
- Debug transport controls live in the top toolbar, and stepping shortcuts work globally while timeline data exists.
- Stack HUD stays visible above the editor; timeline and memory panels provide drill-down instead of duplicating the primary stack view.
- Bottom timeline is compact (scrubber + chips); detailed event metadata lives in the sidebar `Timeline` tab.
- Both editor/dock (vertical) and main/sidebar (horizontal) splits are draggable for layout resizing.
- Memory inspector supports `Selected Step` vs `Live Runtime` views so stack/register state can follow timeline scrubbing without losing current runtime state.
- Memory inspector includes int/hex/byte/ASCII views plus variable-address tags and explanatory hints for repeated zeros.

## Test Harness

- Scenario-driven conformance harness for deterministic multi-step language behavior (`src/testing/engine-harness.ts`).
- Deterministic stack-safe program generators for fuzz/property testing (`src/testing/generators.ts`).
- Property/metamorphic tests:
  - interpreted vs compiled equivalence
  - snapshot-restore behavioral equivalence
- Parser edge-case tests and analysis pipeline tests for labels/xref/effects.
