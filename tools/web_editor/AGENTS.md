# AGENTS.md

## Purpose
This repository contains the implementation of the **Augmented Forth** web editor prototype described in `forth-editor-spec.md`.
The goal is to build a practical, instrumented Forth environment that reduces stack-language cognitive load through visibility, analysis, and safe iteration.

## Source of Truth
- Primary spec: `forth-editor-spec.md`
- If behavior is unclear, favor the spec's architecture and roadmap over ad-hoc shortcuts.
- Preserve the distinction between:
  - Code editor text state
  - Forth engine runtime state

## Implementation Priorities
1. Keep the Forth engine inspectable and deterministic.
2. Preserve instrumentation fidelity (events per executed word).
3. Make analysis honest: prefer `opaque/unknown` over misleading certainty.
4. Keep UI responsive and keyboard-first.
5. Ship vertically integrated slices (engine -> analysis -> UI) rather than isolated modules.

## Required Architecture
Use this structure unless there is a compelling reason to deviate:
- `src/engine/`: interpreter, primitives, compiler, snapshots, types
- `src/analysis/`: stack-effect inference, label propagation, xref, control-flow checks
- `src/components/`: UI panels
- `src/store/`: Zustand stores for engine/analysis/ui state
- `src/utils/`: tokenizer/parser and analysis helpers

## Non-Negotiable Runtime Behaviors
- One execution event stream with monotonically increasing sequence numbers.
- Every primitive and compiled-word call emits instrumentation.
- Auto-snapshot before each REPL execution.
- Engine errors restore pre-execution snapshot and report context.
- Code-pane undo and REPL undo stay independent.

## Forth Semantics Scope
- Prioritize correctness for core words used by the editor experience.
- If a word is partially implemented or non-standard, mark it clearly in code comments and analysis metadata.
- For static analysis of dynamic constructs (`EXECUTE`, complex `CREATE...DOES>`, etc.), mark as opaque and continue.

## Developer Workflow
- Install dependencies: `npm install`
- Dev server: `npm run dev`
- Typecheck/build: `npm run build`
- Lint: `npm run lint`
- Preview production build: `npm run preview`

## Coding Conventions
- TypeScript strict mode.
- Small, focused modules; avoid monolithic files when possible.
- Prefer pure functions in analysis code.
- No silent catches; surface errors with actionable messages.
- Keep comments high-value and concise.

## Validation Checklist Before Finishing
- `npm run build` passes.
- REPL executes basic Forth (`3 4 + .S`).
- Define and call a word (`: SQUARE DUP * ; 5 SQUARE`).
- Undo restores previous runtime snapshot.
- Analysis populates stack effects and xref for user definitions.
- UI shows stack, dictionary, inspector, and memory panels without runtime exceptions.

## Defer vs. Implement Guidance
- Implement robust MVP behavior now.
- Defer heavy polish (complex arrow rendering, advanced docking, exhaustive ANS coverage) unless explicitly requested.
- When deferring, leave clean extension points and document the gap in code.

## Safety
- Never use destructive git commands.
- Do not overwrite user-authored spec content.
- Keep generated/build artifacts out of source unless explicitly requested.
