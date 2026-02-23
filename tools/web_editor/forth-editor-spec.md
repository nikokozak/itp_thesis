# Augmented Forth: A Specification for a Cognitively-Aware Programming Environment

## Document Purpose

This document is a complete specification for building a web-based Forth programming environment designed to address the fundamental cognitive difficulties of stack-based programming. It is intended to be handed to a frontier coding LLM (or a human developer) and contain everything necessary to build the system from scratch.

The environment is not a toy or a tutorial. It is a prototype of what programming environments should look like when designed around Intelligence Augmentation principles — making the programmer smarter rather than hiding complexity from them.

---

## Part 1: The Problem Space

### 1.1 Why Forth Is Cognitively Difficult

Forth is a stack-based, concatenative, postfix language with an interactive development model. Its core difficulty is not intellectual complexity — Forth is one of the simplest languages in existence. The difficulty is **cognitive load**: the programmer must maintain and manipulate mental models of invisible state while simultaneously making creative decisions.

The specific cognitive loads are enumerated below. Every feature in this specification maps to one or more of these loads.

#### 1.1.1 Stack Prediction (Forward Simulation)

When writing a word definition, the programmer must mentally simulate the stack state at every point. This is a working memory task limited to ~4 items (Cowan's number). Stacks deeper than 3-4 items exceed human cognitive capacity. The simulation is sequential and non-resumable: losing track at step 4 of 8 requires restarting from step 1.

**Design target:** Make stack state visible at every point without requiring mental simulation.

#### 1.1.2 Phantom Parameters (Implicit Argument Binding)

In `3 4 HYPOTENUSE`, the values `3` and `4` are not syntactically connected to `HYPOTENUSE`. The programmer must mentally track which values on the stack are "intended for" which consuming words. In long definitions, producers and consumers may be separated by many lines.

**Design target:** Make the connection between data producers and data consumers visible.

#### 1.1.3 Positional Anonymity

Stack items have no names — only positions. After every `SWAP`, `ROT`, `OVER`, or other stack manipulation, the programmer must mentally remap position→meaning for every item. This is a continuous re-indexing cost.

**Design target:** Assign and track semantic labels for stack positions through transformations.

#### 1.1.4 Composition Opacity

When words are composed (`: PROCESS CLEAN TRANSFORM VALIDATE STORE ;`), the intermediate stack states between words are invisible. The programmer cannot verify correctness without looking up every component word's stack effect, and stack-effect comments are unenforced metadata that can drift from implementation.

**Design target:** Show intermediate stack states in composed words; check that declared stack effects chain correctly.

#### 1.1.5 Dictionary Destructiveness

The Forth dictionary is append-only with destructive truncation. `FORGET` removes a word and everything defined after it. Redefining a word shadows the old definition but doesn't remove it. There is no edit-in-place.

**Design target:** Provide undo/redo and safe redefinition.

#### 1.1.6 Inadequate Namespacing and Metadata

Traditional Forth has a flat dictionary with no modules, no documentation infrastructure, no search by stack effect, no cross-referencing. `WORDS` dumps everything unsorted.

**Design target:** Provide word inspection, documentation, cross-referencing, and search.

#### 1.1.7 Error Opacity

Stack underflow may crash the system. Type errors (using an address as a number) produce garbage silently. The causal distance between a mistake and its observable effect can be enormous.

**Design target:** Catch errors early through static checking; provide rich error context when runtime errors occur.

#### 1.1.8 The Return Stack and Floating-Point Stack

The return stack is used for loop control and temporary storage, but is even less visible than the data stack. ANS Forth adds a separate floating-point stack. The programmer may be maintaining two or three invisible mutable data structures simultaneously.

**Design target:** Visualize all active stacks, not just the data stack.

#### 1.1.9 Raw Memory Model

Forth's memory model is raw addresses with no structure enforcement. `ALLOT`, `@`, `!` operate on untyped cells. Buffer overruns and misaligned access are undetected.

**Design target:** Out of scope for the editor (this is dialect territory), but the editor should at minimum show memory contents in an inspector.

#### 1.1.10 Control Flow Entangled with Data

`IF` consumes a flag from the stack. Loop indices live on the return stack. Control flow and data flow share the same workspace, so mistakes in one domain corrupt the other.

**Design target:** Visualize which stack items are consumed by control flow vs. data operations; verify that branches leave consistent stack states.

#### 1.1.11 String Handling Complexity

Forth strings are typically `addr len` pairs — two stack items representing one logical value. This doubles the cognitive load for string operations, because the programmer must track compound values across the stack.

**Design target:** The annotation engine must understand compound stack values (two cells = one string) and label them as a unit.

### 1.2 Paradigm-Shift Barriers (for programmers from conventional languages)

These are additional difficulties specific to programmers transitioning from languages like Python, JavaScript, C, etc.

#### 1.2.1 Postfix Notation
Postfix reverses the reading order that programmers have trained pattern recognition for. This is a perceptual retraining problem, not an intellectual one. It takes months to develop fluent postfix reading.

**Design implication:** The editor cannot fix this, but dataflow visualization (showing connections between producers and consumers) can reduce the perceptual cost.

#### 1.2.2 Loss of Named Bindings
Programmers from `let x = ...` languages experience the loss of variable names as a loss of cognitive anchoring. Intermediate results cannot be "set aside" under a meaningful name.

**Design implication:** The semantic annotation system directly addresses this by providing names as an overlay.

#### 1.2.3 Absence of Type Safety
The language never tells you you're confused. A number, an address, and a character code are all the same thing (a cell). The entire error-detection burden shifts to the programmer.

**Design implication:** Stack-effect arity checking is the editor's primary safety intervention.

#### 1.2.4 Flat Visual Structure
Most languages provide visible nesting through indentation and syntax. Forth code is visually flat — a sequence of words separated by spaces. Compositional hierarchy exists but is not visible in the text.

**Design implication:** The editor can provide indentation hints for control structures and visual grouping for word definitions.

#### 1.2.5 Interactive Development Model Disorientation
Forth blurs the line between writing and running code. There is no separate compile step. This is disorienting for programmers accustomed to a clear boundary between editing and execution.

**Design implication:** The editor should make the transition between "defining" and "executing" explicit and visible, while preserving Forth's interactive nature.

#### 1.2.6 Refactoring Anxiety
Redefining a word shadows but doesn't update existing compiled references. There's no tooling to find callers. Factoring a large word requires getting stack effects exactly right for each piece. Programmers stop refactoring because the cost is too high.

**Design implication:** Cross-reference database and arity checking together make refactoring tractable.

#### 1.2.7 Documentation Culture Gap
Forth's documentation tradition is terse stack-effect comments: `( n addr -- flag )`. No equivalent of docstrings, no conventions for explaining intent or usage.

**Design implication:** The editor should support rich documentation attached to words and make it immediately accessible.

#### 1.2.8 The "Feel" of Forth

Beyond specific loads, Forth has experiential qualities the editor must address:

- **The tightrope sensation:** everything works with perfect concentration, everything collapses when focus is lost. No safety net.
- **Illegibility of one's own code:** Forth code written weeks ago is often incomprehensible to its own author because the meaning was encoded in a mental model, not the text.
- **Irreversibility:** once you execute something at the interactive prompt, it's done. Mistakes feel risky rather than cheap.
- **The gratification cliff:** the first hour is amazing (define a word, it runs!), then the next hundred hours are a wall. No gradual ramp — a cliff after the plateau.
- **The silence of execution:** either it works silently or it fails with minimal information.

---

## Part 2: Architecture and Technology Decisions

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────┐
│                  Web Frontend                    │
│  (Code Editor + Visualizations + Inspectors)     │
│                                                  │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │  Code Pane   │  │   Visualization Pane     │  │
│  │  (CodeMirror │  │   - Stack Timeline       │  │
│  │   6 based)   │  │   - Dataflow Diagram     │  │
│  │              │  │   - Annotations Overlay   │  │
│  │              │  │   - Word Inspector        │  │
│  └──────┬───────┘  └────────────┬─────────────┘  │
│         │                       │                │
│  ┌──────┴───────────────────────┴─────────────┐  │
│  │         Orchestration Layer (JS/TS)         │  │
│  │  - Parses Forth source for annotations      │  │
│  │  - Manages execution history/snapshots      │  │
│  │  - Runs static analysis (arity checking)    │  │
│  │  - Maintains cross-reference database       │  │
│  │  - Manages semantic label propagation       │  │
│  └──────────────────┬─────────────────────────┘  │
│                     │                            │
│  ┌──────────────────┴─────────────────────────┐  │
│  │         Forth Engine (JS or WASM)           │  │
│  │  - Executes Forth code                      │  │
│  │  - Exposes dictionary, stacks, memory       │  │
│  │  - Supports state snapshots                 │  │
│  │  - Reports stack changes per operation      │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 2.2 Technology Stack Decision

#### Option A: JavaScript-Based Forth (Recommended)

**Use a Forth interpreter written in JavaScript.**

Rationale:
- Full control over the engine internals. You can instrument every stack operation, expose dictionary structure, serialize state for snapshots.
- No WASM compilation toolchain complexity.
- Easier to add hooks for the orchestration layer (stack-change callbacks, dictionary-change events, execution tracing).
- Acceptable performance for an educational/augmentation environment.

Recommended starting point: write a minimal Forth from scratch in TypeScript (~500-800 lines for a core interpreter) or adapt an existing JS Forth.

Existing JS Forths to evaluate:
- **pForth / hrForth** — various small implementations on GitHub. Most are incomplete or idiosyncratic. Evaluate before adopting.
- Writing from scratch is viable and may be faster than adapting something that doesn't expose the internals you need.

The engine must expose:
- Data stack contents (read)
- Return stack contents (read)
- Dictionary entries (name, code field, link field, flags)
- Memory array (raw access for inspection)
- Per-operation stack delta events (callback: "word X consumed N items, produced M items, here are the before/after stacks")
- State serialization (snapshot the entire engine state to a JS object)
- State restoration (restore from a snapshot)

#### Option B: gforth compiled to WASM

Rationale:
- Battle-tested, standards-compliant Forth.
- Excellent standard library.
- Much harder to instrument at the level needed. gforth's internals are C and assembly. Getting per-operation stack callbacks requires modifying the gforth source.
- WASM compilation adds toolchain complexity (Emscripten).
- State serialization is possible (snapshot the WASM linear memory) but coarse-grained.

**Verdict: Option A unless you specifically need gforth compatibility. The instrumentation requirements favor a JS-native engine.**

#### Frontend Framework

**React + TypeScript.** Rationale:
- Component model maps naturally to the panes/panels architecture.
- Rich ecosystem for code editors (CodeMirror 6 has excellent React integration).
- TypeScript provides type safety for the orchestration layer, which will be complex.

Key libraries:
- **CodeMirror 6** — code editor component. Supports custom syntax highlighting, inline decorations (for annotations), gutter markers (for stack states), and tooltips. This is the backbone of the code pane.
- **D3.js or SVG-based custom rendering** — for the dataflow diagrams and stack timeline visualization. Avoid heavy charting libraries; the visualizations here are custom enough that a generic chart library will fight you.
- **Zustand or Jotai** — lightweight state management. The orchestration layer has complex state (execution history, annotation state, cross-reference database) that needs to be shared across components. Avoid Redux — too much boilerplate for a prototype.

#### Build Tool

**Vite.** Fast, minimal configuration, good TypeScript support. Don't overthink this.

### 2.3 Project Structure

```
forth-augmented/
├── src/
│   ├── engine/                  # The Forth interpreter
│   │   ├── forth.ts             # Core interpreter (outer/inner interpreter, dictionary)
│   │   ├── primitives.ts        # Built-in words (arithmetic, stack ops, memory, I/O)
│   │   ├── compiler.ts          # Colon definitions, IMMEDIATE, compile-time behavior
│   │   ├── snapshot.ts          # State serialization/deserialization
│   │   └── types.ts             # TypeScript types for engine state
│   │
│   ├── analysis/                # Static analysis and annotation
│   │   ├── stack-effect.ts      # Stack-effect inference and arity checking
│   │   ├── annotations.ts       # Semantic label propagation engine
│   │   ├── xref.ts              # Cross-reference database (who calls whom)
│   │   └── control-flow.ts      # Branch analysis (IF/ELSE/THEN stack consistency)
│   │
│   ├── components/              # React UI components
│   │   ├── App.tsx              # Root layout
│   │   ├── CodePane.tsx         # CodeMirror-based editor
│   │   ├── StackTimeline.tsx    # Timeline scrubber for stack states
│   │   ├── DataflowDiagram.tsx  # Visual connections between producers/consumers
│   │   ├── AnnotationOverlay.tsx # Semantic labels displayed inline
│   │   ├── WordInspector.tsx    # Documentation, callers, callees, stack effect
│   │   ├── DictionaryBrowser.tsx # Searchable, categorized word list
│   │   ├── MemoryInspector.tsx  # Raw memory view
│   │   └── REPL.tsx             # Interactive prompt with history
│   │
│   ├── store/                   # State management
│   │   ├── engine-store.ts      # Forth engine state, execution history
│   │   ├── analysis-store.ts    # Annotation state, xref database
│   │   └── ui-store.ts          # Panel visibility, layout preferences
│   │
│   └── utils/
│       ├── forth-parser.ts      # Lightweight Forth tokenizer for editor features
│       └── label-propagation.ts # Algorithm for propagating semantic labels through ops
│
├── public/
│   └── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

---

## Part 3: The Forth Engine

### 3.1 Core Requirements

The engine must be an indirect-threaded (or token-threaded) Forth with these properties:

1. **Standard data stack and return stack** as JavaScript arrays (not a fixed-size buffer — arrays are easier to inspect and serialize).
2. **Dictionary as a linked list of entries**, each containing: name, link to previous entry, immediate flag, code field (either a JS function for primitives or an array of execution tokens for compiled words).
3. **Memory** as a typed array (`Int32Array` or similar) for `ALLOT`, `@`, `!`, etc.

**Number representation decision:** Forth cells are traditionally fixed-width integers (32-bit or 64-bit). JavaScript numbers are 64-bit IEEE 754 floats, which can exactly represent integers up to 2^53. Two approaches:
- **Use JS numbers directly** on the stacks, and `Int32Array` for memory. This is simpler but means stack values and memory values have different representations (you must truncate to 32-bit when storing to memory and sign-extend when loading). This is the recommended approach for the prototype.
- **Use `Int32Array` for everything** including the stacks. More faithful to Forth semantics but more cumbersome in JS.

The engine must also implement `BASE` (the current number base for input parsing and output). Default is 10 (decimal). `HEX` sets base to 16, `DECIMAL` sets it to 10. The parser and `.` output must respect the current base.
4. **Input buffer** and **parser** for processing Forth source text.
5. **State machine** for interpret/compile modes.

### 3.2 Instrumentation Hooks

The engine must emit events that the orchestration layer can subscribe to. These events are the raw material for all visualizations.

```typescript
interface ForthEvent {
  type: 'execute' | 'push' | 'pop' | 'define' | 'forget' | 'error' | 'input';
  sequenceNumber: number;  // Monotonically increasing counter, NOT wall-clock time
  // For 'execute': which word was executed
  word?: string;
  // For 'push'/'pop': which stack, what value
  stack?: 'data' | 'return' | 'float';
  value?: number;
  // For all: complete stack state AFTER this event
  dataStack: number[];
  returnStack: number[];
  // For 'define': the word just defined
  definition?: { name: string; body: string[]; stackEffect?: string };
  // For 'error': what went wrong
  error?: { message: string; word?: string; stackBefore: number[] };
}
```

**Critical: every primitive and every compiled word execution must emit an event.** This is the cost of instrumentation. For a JS-based engine, the performance impact is acceptable.

### 3.3 State Snapshots

The engine must support full state serialization:

```typescript
interface ForthSnapshot {
  dataStack: number[];
  returnStack: number[];
  floatStack: number[];
  memory: ArrayBuffer;           // Raw memory
  dictionary: DictionaryEntry[]; // All defined words
  inputBuffer: string;
  compileMode: boolean;
  // Enough to restore the engine to this exact state
}
```

Snapshot/restore is used for:
- Undo (restore to previous snapshot)
- Execution timeline (record snapshot at each step, enable scrubbing)
- Error recovery (restore to last good state after a crash)

**Dictionary serialization note:** The dictionary is a linked list. In a JS implementation, dictionary entries are likely JS objects with references to each other. Snapshot serialization must deep-clone these objects, not just copy references — otherwise restoring a snapshot won't actually revert the dictionary. The simplest approach: maintain the dictionary as an array (append-only, with a "latest entry index" pointer). Snapshot = copy the array and the pointer. Restore = replace. This avoids linked-list cloning entirely and is the recommended implementation.

**Performance note:** For execution timeline, snapshotting the full memory on every step is expensive. Optimization: snapshot only the stacks on every step, and take full memory snapshots at checkpoints (every N steps or on explicit user request). For undo, full snapshots at each user-initiated action are sufficient.

### 3.4 Minimum Word Set

The engine must implement at least these ANS Forth words to be useful:

**Stack operations:** `DUP DROP SWAP OVER ROT -ROT NIP TUCK PICK ROLL 2DUP 2DROP 2SWAP 2OVER DEPTH`

**Arithmetic:** `+ - * / MOD /MOD NEGATE ABS MIN MAX`

**Comparison:** `= <> < > <= >= 0= 0< 0>`

**Logic:** `AND OR XOR INVERT`

**Memory:** `@ ! +! C@ C! ALLOT HERE CELLS CELL+`

**Control flow:** `IF ELSE THEN DO LOOP +LOOP I J LEAVE BEGIN UNTIL WHILE REPEAT RECURSE EXIT`

**Defining words:** `: ; CONSTANT VARIABLE VALUE TO CREATE DOES> IMMEDIATE`

**I/O:** `. .S CR SPACE SPACES EMIT TYPE ." S"`

**Dictionary:** `' FIND WORDS SEE`

**Return stack:** `>R R> R@`

**String:** `COUNT`

Additional words can be added incrementally. The priority is getting the core set right and fully instrumented.

---

## Part 4: The Analysis Layer

### 4.1 Stack-Effect Inference and Arity Checking

This is the most complex analysis component. It performs abstract interpretation over word definitions to determine how many items each word consumes and produces.

**Critical design property: incremental analysis.** When a word is defined, its stack effect is immediately inferred and stored. When a subsequent word references it, the stored effect is used. This means:
- `: SQUARE DUP * ;` → infer effect `( n -- n² )`, store it.
- `: HYPOTENUSE SQUARE SWAP SQUARE + SQRT ;` → look up SQUARE's stored effect during analysis.
- If SQUARE is later redefined with a different effect, all words that depend on it should be re-analyzed and their annotations updated. (For the prototype, flagging stale analyses is sufficient; automatic re-analysis is a nice-to-have.)

**Multi-definition files:** When the code pane contains multiple word definitions, the annotation engine analyzes each `: ... ;` block independently (the stack resets at each colon definition). However, the stack-effect database is cumulative — later definitions can reference earlier ones. Annotations are displayed per-definition, with each definition showing its own stack trace from its declared or inferred inputs.

#### Algorithm

For each word definition:

1. Start with a symbolic stack (empty, or populated with declared input labels).
2. Walk through each word in the definition body.
3. For each word, look up its known stack effect (either from the built-in database for primitives, or from a previous analysis of user-defined words).
4. Apply the stack effect: remove N items (consumed), add M items (produced).
5. Track the minimum stack depth reached (this is the number of inputs consumed from outside the definition).
6. The final stack depth minus the minimum depth is the number of outputs produced.

#### Handling Branches

For `IF...ELSE...THEN`:

1. At `IF`, pop the flag. Fork the analysis into two paths.
2. Analyze the `IF` branch and the `ELSE` branch independently.
3. At `THEN`, both branches must leave the stack at the same depth. If they don't, flag an error.
4. Merge the two paths.

For `DO...LOOP`: The loop body executes an unknown number of times. A net zero stack effect per iteration is the expected case. A non-zero net effect (stack grows or shrinks each iteration) should be flagged as a **warning, not an error** — there are rare legitimate cases where a programmer intentionally accumulates values in a loop, but these are almost always bugs in practice.

For `BEGIN...UNTIL` and `BEGIN...WHILE...REPEAT`: Similar to DO...LOOP — the body should have a net zero effect, plus the consumption of the flag for `UNTIL`/`WHILE`.

**Special control flow words:** `LEAVE` (exits a DO...LOOP early) and `EXIT` (returns from the current word) create additional analysis paths. At a `LEAVE` or `EXIT`, the stack state at that point must be consistent with the expected state at normal exit. `RECURSE` is analyzable — it's a self-call with the same stack effect as the word being defined, but introduces the risk of infinite recursion in the analysis engine. Guard against this by limiting recursion depth in the analyzer (e.g., analyze one level of recursion, then treat further recursion as opaque).

#### Handling the Unknown

Some words cannot be statically analyzed:

- `IMMEDIATE` words that execute at compile time may have arbitrary effects.
- `CREATE...DOES>` words have runtime behavior that depends on `DOES>`.
- `EXECUTE` invokes an arbitrary execution token from the stack.
- `POSTPONE` defers compilation of a word, altering the compile-time behavior of the enclosing definition.
- `[']` and `LITERAL` inject compile-time values, which the analyzer must handle as constants.
- Words that manipulate the return stack for non-standard purposes (using `>R`/`R>` for temporary storage outside of a single word).
- `EVALUATE` — takes a string and interprets it as Forth. Completely opaque to static analysis.

Strategy: **mark these as "opaque" and allow the user to manually annotate their stack effects.** The editor should flag them with a warning: "Stack effect cannot be inferred; please declare it."

```typescript
interface StackEffect {
  inputs: number;        // Number of items consumed
  outputs: number;       // Number of items produced
  inputLabels?: string[];  // Optional semantic labels
  outputLabels?: string[];
  verified: boolean;     // true if machine-checked, false if user-declared
  opaque: boolean;       // true if the word contains un-analyzable constructs
}
```

### 4.2 Semantic Label Propagation

This is the engine that generates the inline annotations (e.g., showing that after `DUP *`, the top of stack is `x²`).

#### Algorithm

1. The user provides initial labels for the word's inputs via the stack-effect declaration (e.g., `{ x y -- result }`).
2. The propagation engine walks through the definition, applying transformation rules for each word:

```
DUP:    [ ...a ]         → [ ...a a ]          (duplicate the label)
DROP:   [ ...a ]         → [ ... ]             (discard the label)
SWAP:   [ ...a b ]       → [ ...b a ]          (swap labels)
OVER:   [ ...a b ]       → [ ...a b a ]        (copy second label)
ROT:    [ ...a b c ]     → [ ...b c a ]        (rotate labels)
+:      [ ...a b ]       → [ ...(a+b) ]        (combine labels)
*:      [ ...a b ]       → [ ...(a*b) ]        (combine labels)
DUP *:  [ ...a ]         → [ ...a a ] → [ ...(a*a) ] → display as "a²"
```

3. Label combination rules can be simplified:
   - `a + a` → `2a`
   - `a * a` → `a²`
   - `a + b` → `a+b`
   - For unknown operations: `f(a, b)` or just `?`

4. Labels are stored per-definition-step and displayed as annotations in the code editor.

#### Compound Value Tracking

For string operations where `addr len` represents a single string:

- The propagation engine supports **grouping**: two adjacent stack items can be tagged as "parts of the same logical value."
- Grouped items are displayed as a single labeled entity in the visualization.
- The user can manually group items, or the engine can infer grouping from known string words (e.g., `S"` always pushes `addr len`).

### 4.3 Cross-Reference Database

Maintained incrementally as words are defined.

```typescript
interface XRefEntry {
  word: string;
  callers: string[];      // Words that reference this word
  callees: string[];      // Words referenced by this word
  definedAt: number;      // Timestamp or sequence number
  documentation?: string; // User-provided doc string
  stackEffect?: StackEffect;
  source?: string;        // Source text of the definition
}
```

Updated on every `: ... ;` definition. When a word is redefined, the old entry is kept in history (for undo) and the new entry replaces it.

### 4.4 Branch Stack-Depth Verification

For every control structure, verify that all branches produce the same net stack effect.

The output should be an inline diagnostic:

- Green: all branches consistent.
- Red: branches leave stack at different depths, with specific annotation showing which branch is wrong and by how much.

---

## Part 5: The User Interface

### 5.1 Layout

The interface is a **multi-pane layout** with the following panels. All panels are resizable and can be shown/hidden via keyboard shortcuts.

```
┌─────────────────────────┬──────────────────────────┐
│                         │                          │
│      Code Pane          │   Stack Timeline         │
│   (CodeMirror editor)   │   (scrubbing view of     │
│                         │    stack states over      │
│                         │    execution time)        │
│                         │                          │
├─────────────────────────┼──────────────────────────┤
│                         │                          │
│      REPL               │   Word Inspector /       │
│   (interactive prompt)  │   Dictionary Browser     │
│                         │                          │
└─────────────────────────┴──────────────────────────┘
```

This is a default layout. The user should be able to rearrange panels.

### 5.2 Code Pane (CodeMirror 6)

**Execution model:** The code pane is a **source editor**, not a live REPL. Text typed in the code pane is NOT automatically executed. The user writes or edits Forth source in the code pane, then explicitly executes it via:
- **Ctrl+Enter** (execute the current selection, or the current line if nothing is selected)
- **Ctrl+Shift+Enter** (execute the entire buffer from top to bottom)

This separation is intentional — it gives the user a safe space to write and edit code before committing it to the engine. The REPL remains available for immediate, one-off execution. The code pane is for building up definitions that the user can review, annotate, and execute when ready.

When code from the code pane is executed, it flows through the same engine as REPL input, with the same instrumentation and snapshotting. The annotations and analysis update in real-time as definitions are added to the dictionary.

#### Syntax Highlighting

Forth syntax highlighting is minimal (the language has almost no syntax), but should cover:

- **Defining words** (`: ; CONSTANT VARIABLE VALUE CREATE DOES>`): bold/distinct color
- **Stack manipulation** (`DUP SWAP OVER ROT DROP`): one color family
- **Control flow** (`IF ELSE THEN DO LOOP BEGIN UNTIL WHILE REPEAT`): another color family
- **Comments** (`\ ...` and `( ... )`): dimmed
- **Numbers**: distinct color
- **Strings** (`." ..."` and `S" ..."`): distinct color

#### Inline Annotations

Using CodeMirror's decoration system, display stack-state annotations as faint text above or below each line of a colon definition. These annotations show the stack state at that point, using semantic labels when available.

Example rendering in the editor:

```
: hypotenuse                        ← stack: [ x y ]
  DUP *                             ← stack: [ x y² ]
  SWAP                              ← stack: [ y² x ]
  DUP *                             ← stack: [ y² x² ]
  +                                 ← stack: [ y²+x² ]
  SQRT ;                            ← stack: [ √(y²+x²) ]
```

The annotations are computed by the label propagation engine and displayed as CodeMirror line decorations. They update in real-time as the user edits the definition.

#### Dataflow Highlighting

When the cursor is on a word, the editor highlights:

- The stack items that word **consumes** (with lines/arrows from those items to the word).
- The stack items that word **produces** (with lines/arrows from the word to subsequent consumers).

Implementation: use CodeMirror's `Decoration.mark` to apply CSS classes to the relevant tokens, and render SVG arrows in an overlay layer.

#### Arity Error Markers

When the analysis layer detects a stack-depth inconsistency (e.g., mismatched branches, or a composed word chain with incompatible effects), display:

- Red underline on the offending word or region.
- Gutter marker (red dot) on the affected line.
- Tooltip on hover explaining the error: "This branch leaves 2 items on the stack, but the other branch leaves 1."

### 5.3 Stack Timeline

A horizontal timeline visualization that shows stack state across execution steps.

#### Display

- X-axis: execution steps (one per word executed).
- Y-axis: stack depth.
- Each cell in the grid represents a stack item at a given step.
- Cells are colored by semantic label (all items labeled "x" get one color, "y" gets another).
- A vertical cursor (scrubber) can be dragged left/right to "time travel" through execution.
- Moving the scrubber updates the code pane to highlight the currently-executing word.

#### Interaction

- Click on any cell to see: the value, its semantic label, its provenance (which word produced it).
- Provenance click-through: clicking provenance highlights the producing word in the code pane.
- The timeline supports both the REPL (showing the stack across a sequence of interactive commands) and word definitions (showing the stack through the body of a definition with sample inputs).

#### Multi-Stack Display

Toggle between viewing:
- Data stack only (default)
- Data stack + return stack (side by side or stacked)
- Data stack + float stack (if floating-point words are used)

### 5.4 REPL

An interactive Forth prompt at the bottom-left of the interface, with an **output area** directly above it (or integrated as a scrolling log) that captures all Forth output (from `.`, `CR`, `TYPE`, `EMIT`, `."`, and any other I/O words). The output area is distinct from the stack visualization — it shows what the program *prints*, not what is on the stack.

#### Features

- Standard Forth interactive behavior: type a line, press Enter, it executes.
- Command history (up/down arrows).
- **Pre-execution preview:** before pressing Enter, the editor shows a dimmed/ghosted preview of what the stack will look like after execution (computed by running the analysis engine on the input line against the current stack state). This makes the REPL feel predictive rather than opaque. **Limitation:** the preview can only work for words whose stack effects are known (primitives and words with inferred/declared effects). For opaque words, the preview shows a `?` for unknown resulting items. This is acceptable — partial preview is still far better than no preview.
- **Auto-snapshot:** every REPL execution creates a state snapshot. The user can undo any REPL action with Ctrl+Z.
- **Error recovery:** if execution causes an error, the engine automatically restores to the pre-execution snapshot and displays the error with full context (what was on the stack, which word failed, why).
- **Inline assertions:** The environment supports a lightweight testing syntax in the REPL: `TEST{ 3 4 + -> 7 }TEST`. This pushes `3 4`, executes `+`, then compares the resulting stack against `7`. If they match, it prints "ok". If not, it shows expected vs. actual. This makes the REPL feel safe for experimentation — you can verify your understanding of any word instantly. Implementation: `TEST{` snapshots the stack and begins recording. `->` marks the boundary between code-to-test and expected result. `}TEST` compares. This is a REPL-only feature (not needed in the compiler).

### 5.5 Word Inspector

A panel that displays detailed information about any word. Activated by:

- Clicking a word in the code pane while holding a modifier key (Ctrl+click or Cmd+click).
- Typing `INSPECT word` in the REPL.
- Selecting a word in the Dictionary Browser.

#### Contents

- **Name** and **type** (primitive, compiled, immediate, does>, constant, variable).
- **Stack effect** (inferred or declared, with verification status).
- **Documentation** (user-provided, via a `DOC"` mechanism or an editor-side annotation).
- **Source** (the full definition body, or "primitive" for built-in words).
- **Callers** (words that use this word — from the cross-reference database).
- **Callees** (words this word uses).
- **Execution history** (how many times this word has been called in this session, last call's stack state).

### 5.6 Dictionary Browser

A searchable, filterable list of all defined words.

#### Features

- **Search by name** (substring match).
- **Filter by type** (primitives, user-defined, constants, variables).
- **Filter by stack effect** (e.g., "show me words that take 2 items and leave 1").
- **Sort by** definition order, alphabetical, or frequency of use.
- **Grouping:** if the user has defined module-like groupings (via a naming convention like `date.parse`, `date.format`), the browser should detect and display these as collapsible groups.

### 5.7 Keyboard Shortcuts

Every feature must be keyboard-accessible. Suggested defaults:

| Action | Shortcut |
|--------|----------|
| Focus REPL | Ctrl+` |
| Focus Code Pane | Ctrl+1 |
| Focus Stack Timeline | Ctrl+2 |
| Inspect word under cursor | Ctrl+I |
| Toggle annotations | Ctrl+A |
| Undo last REPL action | Ctrl+Z (when REPL focused) |
| Redo REPL action | Ctrl+Shift+Z (when REPL focused) |
| Execute selection | Ctrl+Enter |
| Toggle Dictionary Browser | Ctrl+D |
| Search dictionary | Ctrl+K |
| Scrub timeline left | Left Arrow (when timeline focused) |
| Scrub timeline right | Right Arrow (when timeline focused) |

### 5.8 Undo Scope Clarification

There are **two independent undo systems** in this environment, and they must not interfere:

- **Code Pane undo** (Ctrl+Z when the editor is focused): This is standard text undo, handled entirely by CodeMirror. It undoes text edits. It does NOT affect the Forth engine state.
- **REPL undo** (Ctrl+Z when the REPL is focused): This restores the Forth engine to its previous snapshot. It undoes execution — definitions are removed, stack state is restored, dictionary is rolled back. It does NOT affect text in the code pane.

These must be clearly distinguished in the UI. When the user undoes a REPL action, the stack display and dictionary should visibly revert (with a brief flash or animation indicating state restoration).

### 5.9 File and Session Management

The environment should support:

- **Save session:** Serialize the current state (code in the editor, dictionary, execution history) to a downloadable JSON file or to browser localStorage.
- **Load session:** Restore a previously saved session.
- **Export as Forth:** Save the code pane contents as a standard `.fs` or `.fth` file (plain text, compatible with any Forth system).
- **Load Forth source:** Load a `.fs` file into the code pane and optionally execute it line-by-line (with snapshot at each step, so the entire load is undoable).

For the prototype, localStorage persistence is sufficient. Full file management is a post-month concern.

### 5.10 Compound Value Grouping UI

When two stack items represent one logical value (e.g., `addr len` for a string), the user needs a way to tell the annotation engine to treat them as a unit. Two mechanisms:

- **Automatic:** The engine recognizes known compound-producing words (e.g., `S"` produces `addr len`) and automatically groups the result. This covers the common cases.
- **Manual:** The user can select two adjacent items in the stack visualization and group them via right-click → "Group as compound value" or a keyboard shortcut. The user provides a label (e.g., "my-string"). The grouping propagates forward through subsequent operations.

In the visualization, grouped items are displayed as a single cell with a subtle bracket or background color spanning both positions.

---

## Part 6: Implementation Roadmap

### Week 1: Foundation (Days 1-7)

**Goal:** A working Forth interpreter in the browser with basic REPL and stack display.

#### Days 1-3: Forth Engine
- Implement core interpreter: outer interpreter (parser), inner interpreter (execution), dictionary structure.
- Implement primitives: arithmetic, stack ops, comparison, logic.
- Implement compiler: `: ; IMMEDIATE POSTPONE`.
- Implement control flow: `IF ELSE THEN DO LOOP BEGIN UNTIL WHILE REPEAT`.
- Implement memory: `@ ! ALLOT HERE CELLS`.
- Implement I/O: `. .S CR TYPE S" ."`.
- All primitives emit instrumentation events.
- State snapshot/restore working.

**Test:** Can define and execute `: SQUARE DUP * ;` and see the stack update.

#### Days 4-5: Basic UI
- Set up React + Vite + TypeScript project.
- CodeMirror 6 editor with Forth syntax highlighting.
- REPL component connected to the Forth engine.
- Live stack display (current state, not yet timeline).
- Basic split-pane layout.

**Test:** Can type Forth interactively and see the stack update in real time.

#### Days 6-7: Snapshot and Undo
- Auto-snapshot on every REPL execution.
- Ctrl+Z restores previous snapshot.
- Error recovery: auto-restore on engine error, display error message with context.
- Execution history stored as array of snapshots (capped at N entries).

**Test:** Can undo a bad definition. Can recover from stack underflow without losing state.

### Week 2: Semantic Overlays (Days 8-14)

**Goal:** Annotations and dataflow visualization working for word definitions.

#### Days 8-10: Stack-Effect Analysis
- Build the stack-effect inference engine.
- Handle linear code (no branches).
- Handle `IF...ELSE...THEN` branching.
- Handle `DO...LOOP` (verify net zero per iteration).
- Display inferred stack effects in the Word Inspector.
- Display arity mismatch errors as inline diagnostics.

**Test:** Define a word with mismatched branches, see the error flagged inline.

#### Days 11-12: Semantic Label Propagation
- Implement label propagation algorithm.
- Support user-declared input labels via stack-effect comments parsed by the editor: `( x y -- result )`.
- Propagate labels through DUP, SWAP, OVER, ROT, DROP, arithmetic, comparison.
- Display labels as CodeMirror line decorations (inline annotations showing stack state with labels at each line).
- Handle compound values (addr+len pairs for strings).

**Test:** Define `: hypotenuse ( x y -- dist ) DUP * SWAP DUP * + SQRT ;` and see labeled annotations at every step.

#### Days 13-14: Dataflow Highlighting
- On cursor placement on a word, highlight its consumed and produced items.
- Render connections as SVG overlays or CSS highlights.
- Click-to-trace: click a highlighted item to jump to its producer or consumer.

**Test:** Click on `+` in a definition, see the two items it consumes highlighted and traced back to their origins.

### Week 3: Safety and Discovery (Days 15-21)

**Goal:** Cross-reference database, word inspector, dictionary browser, and pre-execution preview.

#### Days 15-17: Cross-Reference Database and Word Inspector
- Build XRef database, updated on every word definition.
- Implement Word Inspector panel: name, stack effect, source, callers, callees, documentation.
- Implement `DOC"` as an editor-side annotation (stored in the analysis layer, not in the Forth dictionary — this avoids modifying the Forth engine).
- Ctrl+click on any word opens inspector.

**Test:** Define several words that call each other. Inspect one, see its callers and callees.

#### Days 18-19: Dictionary Browser
- Searchable word list.
- Filter by type, stack effect arity.
- Sort by name, definition order.
- Click to inspect.

**Test:** Search for all words that take 2 items and produce 1.

#### Days 20-21: REPL Pre-Execution Preview and Timeline
- Before the user presses Enter, the REPL shows a ghosted preview of the resulting stack state.
- Implementation: run the analysis engine (not actual execution) on the input line against current stack state. Display result as dimmed text below the input.
- Build the Stack Timeline visualization: horizontal grid, scrubber, cell coloring by semantic label.
- Timeline records state on each REPL execution and within word definitions (when the user asks to "trace" a word with sample inputs).

**Test:** Type `3 4 +` in the REPL without pressing Enter, see `[ 7 ]` as a preview. Press Enter, see it in the timeline.

### Week 4: Polish and Integration (Days 22-28)

**Goal:** Refinement, edge cases, documentation, and demo-readiness.

#### Days 22-24: Refinement
- Handle edge cases in analysis: IMMEDIATE words, CREATE...DOES>, EXECUTE (mark as opaque with user-annotatable effects).
- Handle return stack visualization (at minimum: show R> and >R effects in annotations).
- Improve error messages: when the engine errors, show the last N stack states leading up to the error.
- Ensure all keyboard shortcuts work.
- Performance optimization: batch annotation updates, throttle timeline rendering.

#### Days 25-26: Guided Input Mode
- When the user starts a new `: word` definition, the editor prompts (non-intrusively, in a widget) for the stack effect declaration.
- The declared effect seeds the annotation engine and enables arity checking for the definition.
- If the user skips the prompt, the editor infers what it can and marks gaps.

#### Days 27-28: Testing, Documentation, and Demo Preparation
- Write a set of example Forth programs that exercise all features.
- Create a brief walkthrough/tutorial that demonstrates the environment.
- Fix critical bugs. Defer non-critical ones.
- Ensure the project builds and deploys (e.g., to GitHub Pages or Vercel).

---

## Part 7: Known Pitfalls and Mitigations

### 7.1 Performance of Full Instrumentation

Emitting an event for every word execution will be slow for tight loops (e.g., `1000 0 DO I . LOOP` emits 3000+ events).

**Mitigation:** Event recording is enabled by default in the REPL and for "trace" mode (when the user explicitly asks to trace a word). For normal execution, events can be batched or sampled. The timeline only needs to record states for the current "focus" (the word being traced or the last REPL line).

### 7.2 Memory Snapshot Size

A full memory snapshot (e.g., 64KB of Forth memory) on every step is expensive.

**Mitigation:** Copy-on-write or diff-based snapshots. Only record changed memory regions between steps. For undo (which happens at REPL-action granularity, not per-word), full snapshots are fine — they happen infrequently.

### 7.3 Analysis Accuracy for Dynamic Forth

Forth's `IMMEDIATE` mechanism and `CREATE...DOES>` allow compile-time metaprogramming that can break static analysis assumptions. A word that modifies the stack or dictionary at compile time cannot be analyzed by the stack-effect inference engine.

**Mitigation:** Mark such words as opaque. Allow user annotation. Display a warning icon. Do not claim the analysis is complete — be honest about its limits. The environment should say "I can't verify this word's stack effect — please declare it" rather than silently producing wrong results.

### 7.4 Tokenization Ambiguity

Forth has no formal grammar. A word is any sequence of non-whitespace characters. This means the "parser" for syntax highlighting and analysis is really just a tokenizer — but it needs to handle:

- String literals: `." hello"` and `S" hello"` (the closing `"` is part of the word, not a delimiter).
- Comments: `\ rest of line` and `( ... )`.
- Numbers: Forth tries to convert each word to a number if it's not in the dictionary. The "parser" needs to replicate this logic to syntax-highlight numbers correctly.

**Mitigation:** The syntax highlighting parser should share logic with the engine's parser. Don't duplicate the number-parsing logic.

### 7.5 CodeMirror Integration Complexity

CodeMirror 6's extension system is powerful but has a steep learning curve. Inline decorations (for annotations), overlay layers (for dataflow arrows), and gutter markers all use different APIs.

**Mitigation:** Start with the simplest decoration type (line decorations for annotations) and add complexity incrementally. The CodeMirror 6 documentation and examples at https://codemirror.net/examples/ are the primary resource. Budget extra time for this.

**Specific guidance for dataflow arrows:** CodeMirror 6 does not have a built-in "draw arrows between tokens" feature. Two approaches:
1. **Absolute-positioned SVG overlay:** Render an SVG element on top of the CodeMirror editor, compute pixel positions of tokens using CM6's `coordsAtPos()` API, and draw arrows in SVG. This works but requires recalculating positions on scroll, resize, and any editor change.
2. **Widget decorations:** Use CM6 widget decorations to insert small inline SVG elements at producer/consumer positions. Simpler but limited to markers, not connecting lines.

Recommendation: start with approach 2 (highlight tokens with colored backgrounds to show producer/consumer relationships) and defer arrow-drawing to post-MVP. Colored highlights provide 80% of the value with 20% of the implementation cost.

### 7.6 State Management Complexity

The orchestration layer has many interdependent state concerns: engine state, analysis results, annotation state, UI state, execution history. These can become tangled.

**Mitigation:** Use a clear separation:
- Engine store: owns the Forth engine instance, snapshots, execution history.
- Analysis store: owns stack effects, labels, xref database. Recomputed from engine state.
- UI store: owns panel visibility, layout, cursor position.

Analysis store subscribes to engine store changes and recomputes. UI store subscribes to both. Data flows one direction: engine → analysis → UI.

### 7.7 The "Overly Helpful" Trap

There's a risk of making the environment so helpful that it teaches people to depend on the visualizations rather than developing stack intuition. The annotations and previews become a crutch.

**Mitigation:** Make all overlays togglable. Support a "minimal" mode that hides annotations and shows only the raw code and current stack. Encourage users to periodically work in minimal mode. The environment should augment cognition, not replace it.

---

## Part 8: Future Directions (Post-Month)

These are features to consider after the initial build, listed for completeness.

### 8.1 Dialect Features

The editor provides the natural on-ramp to a Forth dialect:

- **Named locals** (compile-time resolved to stack operations)
- **Machine-enforced stack-effect declarations** (currently editor-side, could move to the language)
- **Module system** (vocabulary-based, with documentation and export control)
- **Journaled dictionary** (REDEFINE with reference patching, UNDO as a language feature)

### 8.2 Bidirectional Editing

Specify desired stack transformation ("I have `x y`, I want `x²+y²`"), and the environment suggests word sequences that achieve it. This is a constraint-solving feature that uses the stack-effect database as a search space.

### 8.3 Collaborative Features

Since this is web-based, multi-user collaboration is architecturally feasible. Shared dictionary, shared execution environment, pair programming on Forth.

### 8.4 Physical/Tangible Interface

A gesture-based or tangible-token-based interface where stack operations are performed physically. The editor translates physical manipulations into Forth code. This connects to the thesis work on hand-based input devices and embodied interaction.

### 8.5 Ambient State Awareness

Audio or haptic feedback that communicates stack state: depth as pitch, type errors as dissonance, underflow risk as vibration. Developing a felt sense of program state.

---

## Appendix A: Stack Effects of Core Words

Reference table for the analysis engine's built-in database.

| Word | Effect | Notes |
|------|--------|-------|
| DUP | ( a -- a a ) | |
| DROP | ( a -- ) | |
| SWAP | ( a b -- b a ) | |
| OVER | ( a b -- a b a ) | |
| ROT | ( a b c -- b c a ) | |
| -ROT | ( a b c -- c a b ) | Not in ANS standard; common extension |
| NIP | ( a b -- b ) | |
| TUCK | ( a b -- b a b ) | |
| PICK | ( ...n -- ...n n ) | Dynamic depth — mark as opaque |
| ROLL | ( ...n -- ... ) | Dynamic depth — mark as opaque |
| 2DUP | ( a b -- a b a b ) | |
| 2DROP | ( a b -- ) | |
| 2SWAP | ( a b c d -- c d a b ) | |
| 2OVER | ( a b c d -- a b c d a b ) | |
| DEPTH | ( -- n ) | |
| + | ( a b -- a+b ) | |
| - | ( a b -- a-b ) | |
| * | ( a b -- a*b ) | |
| / | ( a b -- a/b ) | |
| MOD | ( a b -- a%b ) | |
| /MOD | ( a b -- rem quot ) | |
| NEGATE | ( a -- -a ) | |
| ABS | ( a -- |a| ) | |
| MIN | ( a b -- min ) | |
| MAX | ( a b -- max ) | |
| = | ( a b -- flag ) | |
| < | ( a b -- flag ) | |
| > | ( a b -- flag ) | |
| 0= | ( a -- flag ) | |
| 0< | ( a -- flag ) | |
| AND | ( a b -- a&b ) | |
| OR | ( a b -- a\|b ) | |
| XOR | ( a b -- a^b ) | |
| INVERT | ( a -- ~a ) | |
| @ | ( addr -- n ) | |
| ! | ( n addr -- ) | |
| +! | ( n addr -- ) | |
| C@ | ( addr -- c ) | |
| C! | ( c addr -- ) | |
| >R | ( a -- ) R:( -- a ) | Moves to return stack |
| R> | ( -- a ) R:( a -- ) | Moves from return stack |
| R@ | ( -- a ) R:( a -- a ) | Copies from return stack |
| . | ( n -- ) | Print + drop |
| EMIT | ( c -- ) | |
| TYPE | ( addr len -- ) | Compound: string |
| S" | ( -- addr len ) | Works in both interpret and compile mode; compound output |
| IF | ( flag -- ) | Consumes flag |
| I | ( -- n ) | Loop index from return stack |
| J | ( -- n ) | Outer loop index |
| CELLS | ( n -- n*cellsize ) | |
| CELL+ | ( addr -- addr+cell ) | |
| HERE | ( -- addr ) | |
| ALLOT | ( n -- ) | Modifies dictionary pointer; no stack output |
| CONSTANT | ( n -- ) | Defining word; at runtime: ( -- n ) |
| VARIABLE | ( -- ) | Defining word; at runtime: ( -- addr ) |
| VALUE | ( n -- ) | Defining word; at runtime: ( -- n ) |
| TO | ( n -- ) | Compile-time; stores into a VALUE |
| LEAVE | ( -- ) | Exits DO...LOOP; control flow only |
| EXIT | ( -- ) | Returns from current word; control flow only |
| RECURSE | ( varies ) | Same effect as enclosing word |
| CR | ( -- ) | Output only, no stack effect |
| SPACE | ( -- ) | Output only |
| SPACES | ( n -- ) | |

---

## Appendix B: Label Propagation Rules

Transformation rules for the semantic label propagation engine.

### Notation

Labels are symbolic expressions. They can be:
- Simple names: `x`, `y`, `addr`
- Computed expressions: `x²`, `x+y`, `2*x`
- Unknown: `?`

### Rules

```
Operation       Input Labels      →  Output Labels
─────────────────────────────────────────────────────
DUP             [ a ]             →  [ a  a ]
DROP            [ a ]             →  [ ]
SWAP            [ a  b ]          →  [ b  a ]
OVER            [ a  b ]          →  [ a  b  a ]
ROT             [ a  b  c ]       →  [ b  c  a ]
-ROT            [ a  b  c ]       →  [ c  a  b ]
NIP             [ a  b ]          →  [ b ]
TUCK            [ a  b ]          →  [ b  a  b ]
+               [ a  b ]          →  [ a+b ]
-               [ a  b ]          →  [ a-b ]
*               [ a  b ]          →  [ a*b ]
/               [ a  b ]          →  [ a/b ]
MOD             [ a  b ]          →  [ a%b ]
NEGATE          [ a ]             →  [ -a ]
ABS             [ a ]             →  [ |a| ]
=               [ a  b ]          →  [ a=b? ]
<               [ a  b ]          →  [ a<b? ]
>               [ a  b ]          →  [ a>b? ]
0=              [ a ]             →  [ a=0? ]
@               [ addr ]          →  [ [addr] ]
!               [ val  addr ]     →  [ ]
```

### Simplification Rules

Applied after each propagation step:

```
a * a       →  a²
a + a       →  2a
a - a       →  0
a * 1       →  a
a + 0       →  a
a * 0       →  0
```

Expressions deeper than 3 levels of nesting should be simplified to a generated name (e.g., `_t1`) to avoid unreadable annotations. The user can click the generated name to see the full expression.

---

## Appendix C: Resources and References

### Forth Implementations and Standards

- ANS Forth Standard: https://forth-standard.org/
- gforth (GNU Forth): https://gforth.org/
- Factor (Forth-descendant with stack-effect inference): https://factorcode.org/
- jonesforth: A literate x86 Forth implementation useful for understanding internals: https://github.com/nornagon/jonesforth

### Bret Victor / IA References

- "Learnable Programming" (2012): http://worrydream.com/LearnableProgramming/
- "Inventing on Principle" (2012): https://vimeo.com/36579366
- Engelbart, "Augmenting Human Intellect" (1962): https://www.dougengelbart.org/content/view/138

### CodeMirror 6

- Documentation: https://codemirror.net/
- Extension examples: https://codemirror.net/examples/
- Decoration system: https://codemirror.net/docs/ref/#view.Decoration

### Stack-Effect Inference

- Factor's stack-effect inference implementation is the primary reference for this domain.
- "Stack Effect Inference for Forth" — search Factor's documentation and Slava Pestov's blog posts.

### Existing Forth IDEs / Environments (Prior Art)

- **4tH** (Forth compiler with IDE): http://thebeez.home.xs4all.nl/4tH/
- **SwiftForth IDE** (commercial): https://www.forth.com/swiftforth/
- **Mecrisp** (Forth for microcontrollers, has some visualization tools in the community)
- **Easy Forth** (web-based tutorial Forth): https://skilldrick.github.io/easyforth/ — good reference for minimal web Forth, but no augmentation features.
