# Context Transfer: Embedded Node Architecture

**Copy this into a new conversation to resume context.**

---

## Project: Computational Dignity

Self-describing embedded systems that contain everything needed to be understood, modified, and maintained forever. No cloud, no IDE, no external dependencies.

**Thesis:** "The computational power of small embedded systems can and should be taken seriously. By returning to interactive, introspectable computing—embodied in the Forth tradition—we can build devices that maintain 'computational dignity.'"

**One-liner:** "Embedded systems that explain themselves and last forever."

**Provocation:** "The cloud is a design failure. This is what we should have built."

## Architecture

```
Dumb Terminal (RPi Zero + screen + keyboard)
       │ UART
       ▼
Smart Node (ESP32, ESP32forth)
       │ UART
       ▼
Dumb Node (ATmega328P FlashForth, or ATtiny1614 C)
       │ internal SPI/I2C
       ▼
Raw Sensors
```

## Key Decisions Made

1. **UART as primary bus protocol.** I2C only internal to sensor adapters. SPI never on main bus.
2. **ATtiny1614 as minimum MCU** (hardware UART required). ATtiny85 rejected.
3. **Text protocol** — human-readable, line-oriented, trivially parseable in Forth.
4. **Unified 6-pin connector:** VCC, GND, DATA+, DATA-, MODE, SAFE. Supports TTL and RS-485.
5. **No command language layer.** Users learn Forth. Don't apologize for the thesis.
6. **ESP32 over STM32** — ubiquity wins. "I built this on hardware you already own."
7. **Safety architecture** — nodes are unbrickable. Terminal keeps snapshots. SAFE pin for recovery.

## Remarkable Features (What Makes It Thesis-Worthy)

1. **Self-explaining nodes:** `explain` returns natural language description of what node is and does.
2. **Source on device:** `source` lists all Forth code. Device is its own documentation.
3. **History/rollback:** Every modification logged. Version control built into each node.
4. **Observable computation:** `trace on` shows stack transformations, call trees live.
5. **Physical introspection:** `scan` analyzes pins, guesses what's connected (button, LED, etc.).
6. **Cross-node programming:** `define : word ... ;` compiles Forth on remote nodes over the bus.
7. **Computerless development:** Entire dev cycle on RPi Zero terminal. No laptop ever.

## Protocol Summary

| Command | Function |
|---------|----------|
| `?` | Identity |
| `s` | Sample |
| `n` | Buffer count |
| `d [N]` | Dump |
| `c` | Clear |
| `explain` | Natural language description |
| `source` | Show code |
| `history` | Modification log |
| `scan` | Pin analysis |
| `trace on/off` | Execution visibility |
| `define : word ;` | Remote compilation |
| `validate` | Sanity check before save |
| `safe-save` | Validate then save |
| `recover` | Factory reset (erase user code) |
| `@name cmd` | Route to child |

Response format: `! key value` lines, terminated by `! end`. Errors: `# message`.

## MCU Targets

| Role | MCU | Language |
|------|-----|----------|
| Smart Node | ESP32 (DevKit) | ESP32forth |
| Dumb Node | ATmega328P | FlashForth |
| Sensor Adapter | ATtiny1614 | Forth or C |

## Safety Architecture

**Node-side:**
- Immutable bootloader (Forth core always intact)
- SAFE pin: hold to GND on boot → skip user code
- Watchdog: auto-reboot on hang
- `validate`: sanity check before save
- `recover`: factory reset (erase user code)

**Terminal-side:**
- Snapshot on connect (automatic backup)
- Confirm before modify (diff + prompt)
- Local restore (replay saved definitions)
- Automatic versioning (~/.nodehist/)

## Open Questions

- ESP32forth tracing capability? Multitasking interaction with watchdog?
- Flash wear for history storage (FRAM alternative?)
- RS-485 collision handling for broadcast queries
- Scan heuristic accuracy—acceptable false positive rate?
- WiFi as optional transport? (same protocol, wireless delivery)

## Timeline

- Weeks 1-2: Foundation (basic protocol working)
- Weeks 3-4: Self-description (explain, source, history)
- Weeks 5-6: Safety architecture (watchdog, validate, recover, terminal snapshots)
- Weeks 7-8: Observable computation (trace)
- Weeks 9-10: Physical introspection (scan)
- Weeks 11-12: Cross-node programming
- Weeks 13-14: Hardware polish (PCBs, cables)
- Weeks 15-16: Dumb terminal build
- Weeks 17-20: Documentation & thesis writing
- Weeks 21-22: Buffer

## The Demo (10 min)

Setup: RPi terminal, smart node, sensor adapter. No laptop.

1. `?` and `explain` — node describes itself
2. `source` — shows its own code
3. `scan` — identifies connected hardware
4. `@sensor s` — query through network
5. Remote `define` — modify sensor code live
6. `trace on` — watch computation
7. `history` / `rollback` — show version control
8. Unplug sensor, reconnect, show it kept running

Closing: "This is what embedded computing looked like in 1970. We gave it up. This project proves we can have it back."

---

**Project Lead:** Nikolai Kozak, NYU ITP Thesis  
**Document Date:** December 2024
