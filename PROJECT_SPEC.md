# Computational Dignity: Self-Describing Embedded Systems

## Project Production Document
**Version:** 1.0  
**Date:** December 2024  
**Author:** Nikolai Kozak  
**Program:** NYU ITP Thesis

---

## Part I: Vision & Thesis

### The Core Argument

Modern embedded systems have lost their autonomy. An MCU today is a dumb peripheral—programmed by a heavyweight IDE, dependent on cloud services, opaque to inspection, abandoned when the company that made it goes out of business.

This project demonstrates an alternative: **embedded systems that contain everything they need to be understood, modified, and maintained—forever.**

A node in this system:
- Explains what it is and what it does
- Shows its own source code
- Records its own history
- Can be programmed with nothing but a keyboard and screen
- Requires no internet, no cloud, no company to keep existing
- Speaks a human-readable protocol over simple wires

### The Thesis Statement

> "The computational power of small embedded systems can and should be taken seriously. By returning to interactive, introspectable computing—embodied in the Forth tradition—we can build devices that maintain 'computational dignity': the ability to be fully understood, modified, and owned by their users, independent of any external infrastructure."

### What This Is NOT

- Not a product. Not optimized for market adoption.
- Not a Forth tutorial. Forth is a means, not an end.
- Not competing with Arduino/CircuitPython on ease-of-use.
- Not IoT. Explicitly, deliberately, anti-cloud.

### What This IS

- A working critique of contemporary embedded development
- A resurrection of the 1970s Forth vision, updated for 2025
- A demonstration that small computers deserve full citizenship
- A provocation: "What did we give up, and should we take it back?"

---

## Part I-B: The Deeper Argument

### The Trap of the Big Computer

Since the advent of digital computation, we've been trapped by a persistent idea: computation belongs to *the big computer*. Complex, centralized, inaccessible black boxes that exist elsewhere, controlled by someone else.

As hardware miniaturized, we treated small devices as derivatives of this larger whole—stunted fragments, not complete systems. We learned to develop them as:
- **Disposable elements** — single-purpose, never to be reused
- **Little black boxes** — operating on a more limited set of possibility than their hardware actually permits

### The Coming Flood

As AI advances and miniaturization continues, we face a proliferation of embedded devices unlike anything before. Our world will be flooded with sensors, microcontrollers, and embedded hardware—each one deployed as a black box with no reusability in sight.

This is not merely a sustainability problem (though it is that). It's deeper.

### The Instability Assumption

We've constructed an entire paradigm of embedded computation built on an assumption of permanent global stability—stable supply chains, stable infrastructure, stable corporate existence. Every microcontroller deployed is a bet that the systems surrounding it will persist indefinitely.

But we are witnessing geopolitical moves that point to an unstable future. In a highly globalized world, that instability translates into disruptions of supply chains, manufacturing capability, and the infrastructure that makes our current development model possible.

What happens when:
- The company that made your device goes bankrupt?
- The cloud service it depends on shuts down?
- The toolchain required to modify it becomes unavailable?
- Supply chains break and replacement isn't an option?

Currently: the device becomes an inert artifact. Computational capacity we can never reclaim.

### The Civilizational Question

What happens 100 years from now? 200 years? If we face societal disruption—environmental, political, economic—and future generations encounter these devices, they will find them useless. Not because the hardware failed, but because we designed them to be illegible, unmodifiable, dependent on external systems that no longer exist.

We can read cuneiform tablets from 5000 years ago. We cannot read most software from 30 years ago. This is a civilizational failure.

### The Cyberpunk Observation

There's a reason cyberpunk visions of the future feel utopian despite their dystopian aesthetics. In those futures, computation is *fungible*—a universal substrate. A hacker plugs into a motorcycle and it's just... a computer. The vending machine, the security system, the prosthetic arm—they're all accessible as computation if you have the skills.

This is the hidden utopia: not the neon or the implants, but the assumption that any device with a processor is, at some level, just "a computer" you can interact with.

**We built the opposite.**

We have exponentially more processing power than any cyberpunk author imagined. Your smart toothbrush has more compute than the decks in Neuromancer. But none of it is accessible *as computation*. Every device is:
- A proprietary island
- Locked to a single purpose
- Incompatible with everything else
- Illegible by design

We built the processors. We abandoned the universality.

### The Theoretical Betrayal

Computation *is* theoretically fungible—that's what Turing completeness means. Any processor can compute anything any other processor can compute. This is the foundation of computer science.

But we've buried this universality under so many layers of proprietary lock-in that it's practically inaccessible. The substrate is universal; the implementation is entirely fragmented.

Forth is interesting precisely because it restores this fungibility. A Forth environment is the same whether it's on a 1970s minicomputer or an ESP32. It returns computation to its universal substrate.

### The Reframing

This project proposes an ideological shift: from *devices as nodes in a system* to *devices as self-contained computational environments*. Each one complete, legible, modifiable with nothing but itself.

**One sentence:**
> "Every device should survive the system that created it."

**One paragraph:**
> We deploy billions of microcontrollers assuming the world that made them will persist—the companies, the cloud services, the toolchains, the supply chains. History suggests otherwise. Codignity is a firmware foundation that makes embedded devices self-sufficient: able to identify themselves, explain their state, be reprogrammed, and recover from failure—requiring nothing beyond the device itself. Not because we expect collapse, but because computation shouldn't depend on the permanence of any external system.

**The cyberpunk framing:**
> We were promised that any computer could be *a computer*. We got billions of processors we can't use. Codignity returns embedded devices to the universal computational substrate they always were.

---

## Part II: Architecture

### System Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                        DUMB TERMINAL                            │
│        (RPi Zero + screen + keyboard, or any serial terminal)   │
│        Renders. Inputs. Has no intelligence.                    │
└───────────────────────────────┬─────────────────────────────────┘
                                │ UART (text protocol)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         SMART NODE                              │
│                    (ESP32 + ESP32forth)                         │
│   Full REPL. Self-explaining. Routes to children.               │
└──────┬─────────────────┬─────────────────┬──────────────────────┘
       │ UART            │ UART            │ UART
       ▼                 ▼                 ▼
┌────────────┐    ┌────────────┐    ┌────────────┐
│ DUMB NODE  │    │ DUMB NODE  │    │  SENSOR    │
│ ATmega328P │    │ ATtiny1614 │    │  ADAPTER   │
│  (Forth)   │    │  (Forth/C) │    │ ATtiny1614 │
└────────────┘    └────────────┘    └────────────┘
                                          │
                                          │ SPI/I2C (internal)
                                          ▼
                                    ┌───────────┐
                                    │ Raw Sensor│
                                    └───────────┘
```

### The Protocol

Text-based. Line-oriented. Human-readable. Debuggable with any terminal emulator.

**Core Commands:**

| Command | Response | Function |
|---------|----------|----------|
| `?` | Identity block | Who are you? |
| `s` | Sample + timestamp | Take a reading now |
| `n` | Integer | How many samples buffered? |
| `d [N]` | Data lines | Dump last N samples |
| `c` | Ack | Clear buffer |
| `@name cmd` | Routed response | Send command to child node |

**Extended Commands (the remarkable features):**

| Command | Response | Function |
|---------|----------|----------|
| `explain` | Natural language description | What are you and why? |
| `source` | Full Forth source listing | Show your code |
| `history` | Modification log | Who changed what, when? |
| `scan` | Pin analysis | What's connected to you? |
| `trace on/off` | — | Enable execution tracing |
| `define : word ... ;` | Ack | Compile new Forth word |
| `save` | Ack | Persist to flash |
| `rollback N` | Ack | Revert to previous state |

**Response Format:**

```
! key value           ← data line
! key value           ← data line
# error message       ← error line
! end                 ← terminator (required)
```

### Physical Layer

**Unified 6-Pin Connector:**

| Pin | Name | Function |
|-----|------|----------|
| 1 | VCC | 3.3V power |
| 2 | GND | Ground |
| 3 | DATA+ | TX (TTL) or A (RS-485) |
| 4 | DATA- | RX (TTL) or B (RS-485) |
| 5 | MODE | GND=TTL, VCC=RS-485 |
| 6 | SAFE | GND during boot = safe mode (skip user code) |

**Connector Type:** JST-PH 6-pin (or equivalent)

**Cable Variants:**
- TTL Cable: MODE tied to GND. Short range, educational use.
- RS-485 Cable: MODE tied to VCC. Long range, industrial use.
- Recovery Cable: SAFE tied to GND. Forces safe mode on connect.

### MCU Targets

| Role | Primary MCU | Fallback | Language |
|------|-------------|----------|----------|
| Smart Node | ESP32 (DevKit) | RP2040 | ESP32forth |
| Dumb Node | ATmega328P | ATmega32U4 | FlashForth |
| Sensor Adapter | ATtiny1614 | ATtiny3216 | Forth or C |

**Minimum floor:** ATtiny1614 (hardware UART required)

**Why ESP32 over STM32:**
- Ubiquity: "I built this on hardware you already own"
- Cost: ~$5 vs ~$12
- Resources: 520KB RAM, 4MB flash (room for history, traces, recovery)
- ESP32forth is actively maintained with good documentation
- USB-Serial built into most dev boards
- Optional: WiFi enables wireless terminal connection (same protocol, different transport)

---

## Part III: The Remarkable Features

These are what transform competent infrastructure into a memorable thesis.

### Feature 1: The Node That Explains Itself

Every node responds to `explain` with a complete natural-language account:

```
explain
! I am a humidity sensor node.
! I sample a DHT22 connected to pin 3.
! I take a reading every 100 milliseconds.
! I store the last 256 readings in a circular buffer.
! My current reading is 67% RH.
! I was created on December 12, 2024.
! I was last modified 3 days ago by terminal@10.0.0.3.
! The last change was: "increased sample rate from 1s to 100ms"
! My source code is 47 lines of Forth. Say SOURCE to see it.
! end
```

**Implementation:** The node stores structured metadata alongside code. `explain` formats it.

**Why it matters:** The device is its own documentation. No external database. No README. The truth lives in the thing itself.

### Feature 2: Observable Computation

Execution is visible. Not after-the-fact logging—live observation.

```
trace on
sample

! TRACE sample
!   ( -- )
!   call dht22-read
!     ( -- 67 )
!   call fifo-push
!     ( 67 -- )
!     [fifo: 255 → 256, wrapped]
!   exit
! end
```

**Implementation:** Mecrisp-Stellaris has hooks for this. FlashForth needs modification or a wrapper.

**Why it matters:** Students watch the stack transform. Debuggers see state flow. Computation becomes tangible.

**Terminal visualization:** The dumb terminal can render this graphically—stack bars, call trees, memory maps. ASCII art is sufficient.

### Feature 3: Development Without a Computer

The killer demo: No laptop. Just terminal + keyboard + node.

```
┌─────────────────────────────────────────────────┐
│  RPi Zero W                                     │
│  + 3.5" LCD                                     │
│  + USB keyboard                                 │
│  + Serial connection to node                    │
│                                                 │
│  Total BOM: ~$25                                │
│  Runs: any terminal emulator (minicom, screen)  │
└─────────────────────────────────────────────────┘
```

The entire development cycle:
1. Connect to blank node
2. Type Forth definitions
3. Test interactively
4. Save to flash
5. Disconnect; node runs autonomously

**Why it matters:** Proves the heavyweight toolchain is a choice, not a necessity. In 1970 this was normal. We can have it again.

### Feature 4: Code Over the Bus

Nodes can program other nodes through the text protocol.

```
@humid source
! : sample dht22-read fifo-push ;
! : main begin sample 1000 ms again ;
! end

@humid define : sample dht22-read dup . fifo-push ;
! ok

@humid save
! ok

@humid restart
! HELLO humid attiny1614 v1
```

**Implementation:** The `define` command invokes the Forth compiler on the target node. Because Forth is homoiconic (code and data are the same), there's no special "upload" mechanism.

**Why it matters:** Network-level metaprogramming. Code flows over the same wires as data. The boundary between "using" and "programming" dissolves.

### Feature 5: Nodes That Know Their History

Every modification is logged. Every node has version control.

```
history
! 2024-12-30 10:23:14 terminal@10.0.0.3
!   defined: sample
! 2024-12-30 10:24:02 terminal@10.0.0.3
!   redefined: sample
! 2024-12-27 14:15:00 terminal@10.0.0.5
!   created node
! end

diff 1
! - : sample dht22-read fifo-push ;
! + : sample dht22-read dup . fifo-push ;
! end

rollback 1
! rolled back to 2024-12-30 10:23:14
! ok
```

**Implementation:** Store previous word definitions before overwriting. Timestamp and tag with source identifier. Simple append-only log in flash.

**Why it matters:** No node is ever a mystery. You can always reconstruct how it got to its current state. Auditability without external systems.

### Feature 6: Physical Introspection

The node understands what's connected to its pins.

```
scan
! PIN 0: INPUT HIGH stable 10m pull-up:~10k guess:button
! PIN 1: OUTPUT LOW changed:500ms-ago
! PIN 2: INPUT floating noise guess:unconnected
! PIN 3: OUTPUT PWM:1kHz:50% draw:~20mA guess:LED
! PIN 4: ANALOG 2.3V drift:slow guess:thermistor
! PIN 5: UART-TX active
! PIN 6: UART-RX active
! end
```

**Implementation:**
1. Read pin state (easy)
2. Measure with ADC (moderate)
3. Briefly toggle pin mode, observe response (advanced)
4. Infer device type from electrical signature (heuristics)

**Why it matters:** The node knows its own body. Not just "pin 3 is high" but "pin 3 has a button." Reduces the gap between physical and digital.

---

## Part IV: Safety Architecture

The system must be unbrickable. A thesis about "computational dignity" fails if users can accidentally destroy their nodes.

### Design Principle

> "You cannot permanently brick a node. At worst, you lose your code—but even then, the terminal probably has a backup. And if all else fails, hold the safe mode button and start fresh."

### Failure Modes

| Failure | Cause | Symptom |
|---------|-------|---------|
| Hung loop | `begin ... again` with no exit | Node unresponsive |
| Corrupt dictionary | Bad pointer, overwritten header | Forth crashes on boot |
| Broken UART | Reconfigured pins wrong | Can't communicate |
| Bad interrupt | Crashed ISR | System freeze |
| Full flash | Too much history/code | Can't save |

### Node-Side Protection

**1. Immutable Bootloader Region**

The core Forth interpreter lives in protected flash. User code cannot overwrite it.

```
┌─────────────────────┐ 0x00000
│  Bootloader         │ ← Protected, never touched
│  (Forth core)       │
├─────────────────────┤ 0x10000
│  User dictionary    │ ← This is what save/erase affects
│  (your code)        │
├─────────────────────┤
│  User data          │ ← FIFO, history, metadata
│  (variables, etc)   │
└─────────────────────┘
```

Worst case: lose user definitions, not Forth itself.

**2. Safe Mode Entry**

SAFE pin (connector pin 6) held to GND during power-on boots directly to Forth prompt, skipping all user code.

```forth
: safe-mode? ( -- flag )
  SAFE_PIN gpio@ 0= ;

: boot
  safe-mode? if
    ." SAFE MODE - user code skipped" cr
  else
    ['] main catch if
      ." MAIN CRASHED - entering recovery" cr
    then
  then
  quit ;
```

**3. Watchdog Timer**

If user code hangs, hardware watchdog reboots into safe mode.

```forth
: arm-watchdog ( -- )
  5000 WDT_TIMEOUT !       \ 5 second timeout
  WDT_ENABLE ! ;

: pet-watchdog ( -- )
  WDT_FEED ! ;             \ Must call regularly

: main
  arm-watchdog
  begin
    sample
    pet-watchdog           \ Reset watchdog
    100 ms
  again ;
```

Hang without petting → automatic reboot → safe mode check.

**4. Pre-Save Validation**

Sanity check before committing to flash:

```forth
: validate ( -- flag )
  ['] ? catch 0= and       \ Can we run basic commands?
  ['] s catch 0= and
  depth 0= and ;           \ Stack balanced?

: safe-save ( -- )
  validate if
    save ." Saved." cr
  else
    ." VALIDATION FAILED. Not saved." cr
  then ;
```

**5. Nuclear Recovery**

The `recover` command erases all user code:

```forth
: recover ( -- )
  ." Erasing user dictionary..." cr
  erase-user-flash
  ." Rebooting..." cr
  reset ;
```

```
recover
! Erasing user dictionary...
! Rebooting...
! HELLO blank esp32 v1
```

### Terminal-Side Protection

The terminal is the safety net for everything node-side protection misses.

**1. Snapshot on Connect**

Every connection triggers automatic backup:

```python
class NodeConnection:
    def connect(self, port):
        self.serial = serial.Serial(port, 115200)
        self.snapshot = {
            'source': self.query('source'),
            'history': self.query('history'),
            'timestamp': datetime.now()
        }
        self.save_snapshot(f"snapshots/{self.node_id}_{timestamp}.json")
```

**2. Confirm Before Modify**

Terminal intercepts `define` commands, shows diff, requires confirmation:

```
> @sensor define : sample dht22-read dup . fifo-push ;

WARNING: About to modify node 'sensor'
Current definition of 'sample':
  : sample dht22-read fifo-push ;
New definition:
  : sample dht22-read dup . fifo-push ;

Proceed? [y/N]
```

**3. Local Restore**

Replay saved definitions to recover a node:

```
> restore sensor

Available snapshots for 'sensor':
  1. 2024-12-30 10:15:00 (current session)
  2. 2024-12-30 09:45:00
  3. 2024-12-29 14:20:00

Select: 2

Restoring 3 words: sample main init
@sensor define : sample dht22-read fifo-push ;
@sensor define : main begin sample 100 ms again ;
@sensor define : init dht22-init ;
@sensor save

Restored.
```

**4. Automatic Versioning**

Terminal keeps rolling snapshots in `~/.nodehist/<node-id>/`:
- On every connect
- Before every `define`
- Before every `save`

Prune after 30 days.

### Safety Model Summary

| Layer | Protection | Recovers From |
|-------|------------|---------------|
| Node: Bootloader | Core Forth always intact | Everything except hardware damage |
| Node: Safe mode | Skip user code on boot | Hung main, bad init |
| Node: Watchdog | Auto-reboot on hang | Infinite loops |
| Node: Validation | Sanity check before save | Obviously broken code |
| Node: `recover` | Erase user code | Corrupt dictionary |
| Terminal: Snapshot | Backup on connect | Any bad modification |
| Terminal: Confirm | Diff before commit | Accidents |
| Terminal: Restore | Replay saved state | Any bad modification |

### Protocol Additions for Safety

| Command | Response | Function |
|---------|----------|----------|
| `recover` | Reboot message | Erase all user code, factory reset |
| `validate` | `! ok` or `! fail <reason>` | Check system sanity |
| `safe-save` | `! ok` or `! fail` | Validate then save |

---

## Part V: Development Schedule

### Phase 0: Foundation (Weeks 1-2)

**Goal:** Prove core technical feasibility.

**Tasks:**
- [ ] Flash ESP32forth on ESP32 DevKit
- [ ] Flash FlashForth on ATmega328P (Arduino Uno or bare chip)
- [ ] Establish serial communication between them
- [ ] Implement basic protocol (`?`, `s`, `n`, `d`, `c`) on both
- [ ] Test terminal → smart node → dumb node routing
- [ ] Implement basic safe mode (SAFE pin check on boot)

**Deliverable:** Two nodes talking, basic protocol working, commands route correctly.

**Risk checkpoint:** If ESP32forth is limiting, evaluate Mecrisp-Stellaris on RP2040 as fallback.

### Phase 1: Self-Description (Weeks 3-4)

**Goal:** Nodes that explain themselves.

**Tasks:**
- [ ] Design metadata storage format (flash layout)
- [ ] Implement `source` command (list all user-defined words)
- [ ] Implement `explain` command (generate natural language from metadata)
- [ ] Implement `history` command (modification log)
- [ ] Implement `diff` and `rollback` commands
- [ ] Test: modify a word, verify history updates, rollback works

**Deliverable:** Connect to any node, understand its complete state and history.

### Phase 2: Safety Architecture (Weeks 5-6)

**Goal:** Unbrickable nodes.

**Tasks:**
- [ ] Implement watchdog timer integration
- [ ] Implement `validate` and `safe-save` commands
- [ ] Implement `recover` command (factory reset)
- [ ] Test safe mode boot (SAFE pin held low)
- [ ] Build terminal-side snapshot system (Python)
- [ ] Build terminal-side restore capability
- [ ] Build confirmation prompts for `define` commands
- [ ] Test recovery from various failure modes

**Deliverable:** Intentionally break a node in every way possible, recover every time.

### Phase 3: Observable Computation (Weeks 7-8)

**Goal:** Watch Forth execute.

**Tasks:**
- [ ] Research ESP32forth tracing capabilities
- [ ] Implement `trace on/off` command
- [ ] Design trace output format (stack state, calls, memory)
- [ ] Build terminal-side visualization (ASCII art stack display)
- [ ] Test with non-trivial Forth programs

**Deliverable:** Type a word, watch the stack transform step by step.

**Risk checkpoint:** If tracing is too invasive (performance, code size), fall back to "trace last N operations" buffer approach.

### Phase 4: Physical Introspection (Weeks 9-10)

**Goal:** Nodes that understand their pins.

**Tasks:**
- [ ] Implement basic `scan` (read all pin states)
- [ ] Add ADC-based impedance estimation
- [ ] Add toggle-and-observe for device detection
- [ ] Build heuristic library (button, LED, potentiometer, common sensors)
- [ ] Test with real components, tune heuristics

**Deliverable:** Connect unknown components, node guesses what they are.

### Phase 5: Cross-Node Programming (Weeks 11-12)

**Goal:** Program one node from another.

**Tasks:**
- [ ] Implement `define : word ... ;` over serial
- [ ] Handle multi-line definitions
- [ ] Implement `save` (commit to flash)
- [ ] Implement `restart` (reboot node)
- [ ] Test: smart node programs dumb node remotely
- [ ] Test: terminal programs dumb node through smart node

**Deliverable:** Full network-level code deployment without any external tools.

### Phase 6: Hardware Polish (Weeks 13-14)

**Goal:** Unified connector, clean hardware.

**Tasks:**
- [ ] Design PCB for smart node breakout
- [ ] Design PCB for dumb node breakout
- [ ] Design PCB for sensor adapter
- [ ] Order PCBs (allow 2-week lead time)
- [ ] Design and order custom cables (JST-PH 6-pin)
- [ ] Assemble and test complete hardware stack

**Deliverable:** Professional-looking hardware, not breadboard prototypes.

### Phase 7: Dumb Terminal (Weeks 15-16)

**Goal:** The computerless development environment.

**Tasks:**
- [ ] Configure RPi Zero W with minimal OS
- [ ] Select/build terminal emulator (minicom, custom?)
- [ ] Add trace visualization support
- [ ] Add scan visualization support
- [ ] Build enclosure (3D printed)
- [ ] Test complete workflow: blank node → programmed node → autonomous operation

**Deliverable:** The demo hardware. Self-contained, portable, striking.

### Phase 8: Documentation & Thesis (Weeks 17-20)

**Goal:** Write it up.

**Tasks:**
- [ ] Document protocol specification formally
- [ ] Document hardware specification
- [ ] Write thesis: framing, argument, evidence, reflection
- [ ] Create demo video
- [ ] Prepare presentation
- [ ] Practice demo until bulletproof

**Deliverable:** Thesis document, demo materials, presentation.

### Phase 9: Buffer (Weeks 21-22)

**Goal:** Handle the unexpected.

**Tasks:**
- [ ] Fix bugs discovered during documentation
- [ ] Polish rough edges
- [ ] Rehearse demo
- [ ] Prepare for questions

---

## Part VI: Key Questions to Resolve

### Technical Questions

1. **ESP32forth capabilities:** Does ESP32forth support the tracing hooks we need? How does its multitasking interact with our watchdog?

2. **Flash wear:** How many history entries before flash wears out? Mitigation strategies (FRAM, wear leveling)?

3. **Trace performance:** How much does tracing slow execution? Is selective tracing (specific words only) necessary?

4. **Scan accuracy:** How reliably can we identify connected components? What's the false positive/negative rate? Is 70% accuracy acceptable?

5. **RS-485 collision:** With multiple nodes on RS-485, how do we handle simultaneous responses to broadcast queries?

6. **Code size on ATtiny1614:** Can we fit protocol + safety features on 16KB? What's the minimum viable feature set for dumb nodes?

7. **WiFi as transport:** Should we support terminal-over-WiFi as optional feature? Same protocol, different physical layer. Demo value vs scope creep.

### Conceptual Questions

1. **How much Forth is too much?** Do we require users to learn Forth, or provide escape hatches? (Current answer: require it, don't apologize.)

2. **What's the canonical demo?** The 10-minute narrative that makes the argument. Rehearse until natural.

3. **Who is the audience?** Academic committee? Industry contacts? Educators? Different framings for each.

4. **What's the one-sentence pitch?** Current draft: "Embedded systems that explain themselves and last forever."

5. **What's the provocative claim?** Current draft: "The cloud is a design failure. This is what we should have built."

### Strategic Questions

1. **Open source when?** Before thesis defense? After? How does this affect positioning?

2. **Conference targets:** Where does this belong? UIST? CHI? TEI? Strange Loop? Forth-specific venues?

3. **Industry contacts:** Who would care? Teenage Engineering? Adafruit? Framework? Research labs?

4. **Follow-on work:** What's the next project after thesis? Productization? Research? Teaching?

---

## Part VII: Bill of Materials (Initial Prototype)

### Smart Node

| Item | Part Number | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
| ESP32 DevKit | ESP32-DEVKIT-C | 2 | $6.00 | $12.00 |
| JST-PH 6-pin connector | — | 4 | $0.20 | $0.80 |
| Misc headers/wires | — | 1 | $5.00 | $5.00 |
| **Subtotal** | | | | **$17.80** |

### Dumb Node

| Item | Part Number | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
| ATmega328P-PU | — | 2 | $3.00 | $6.00 |
| 16MHz crystal | — | 2 | $0.50 | $1.00 |
| Capacitors, resistors | — | 1 | $2.00 | $2.00 |
| JST-PH 6-pin connector | — | 2 | $0.20 | $0.40 |
| **Subtotal** | | | | **$9.40** |

### Sensor Adapter

| Item | Part Number | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
| ATtiny1614 | — | 3 | $0.80 | $2.40 |
| JST-PH 6-pin connector | — | 3 | $0.20 | $0.60 |
| Assorted sensors | — | 1 | $20.00 | $20.00 |
| **Subtotal** | | | | **$23.00** |

### Dumb Terminal

| Item | Part Number | Quantity | Unit Cost | Total |
|------|-------------|----------|-----------|-------|
| RPi Zero 2 W | — | 1 | $15.00 | $15.00 |
| 3.5" LCD (SPI) | — | 1 | $15.00 | $15.00 |
| USB OTG hub | — | 1 | $5.00 | $5.00 |
| USB keyboard (small) | — | 1 | $10.00 | $10.00 |
| USB-Serial adapter | — | 1 | $3.00 | $3.00 |
| SD card | — | 1 | $8.00 | $8.00 |
| Enclosure (3D printed) | — | 1 | $5.00 | $5.00 |
| **Subtotal** | | | | **$61.00** |

### Cables and Misc

| Item | Quantity | Unit Cost | Total |
|------|----------|-----------|-------|
| JST-PH 6-pin cables | 10 | $1.00 | $10.00 |
| PCB prototypes (when ready) | 1 lot | $50.00 | $50.00 |
| **Subtotal** | | | **$60.00** |

### **Total Initial BOM: ~$175**

---

## Part VIII: Success Criteria

### Minimum Viable Thesis (must achieve)

- [ ] Smart node runs Forth, responds to all protocol commands
- [ ] Dumb node runs Forth or C, responds to basic commands
- [ ] `source` command works (show node's code)
- [ ] `explain` command works (natural language description)
- [ ] Cross-node programming works (define word remotely)
- [ ] Safe mode boot works (SAFE pin recovery)
- [ ] Terminal snapshots and restore work
- [ ] Dumb terminal can program a node without a laptop present
- [ ] Thesis document articulates the argument clearly
- [ ] Demo runs reliably

### Strong Thesis (aim for)

All of the above, plus:

- [ ] `history` and `rollback` work
- [ ] `trace` mode visualizes execution
- [ ] `scan` mode identifies connected components
- [ ] Full safety suite (watchdog, validate, recover)
- [ ] Terminal confirmation prompts for modifications
- [ ] Custom PCBs (not breadboards)
- [ ] 3+ sensor adapters demonstrating different sensor types
- [ ] RS-485 multi-drop demonstrated
- [ ] Demo is polished and compelling

### Exceptional Thesis (stretch)

All of the above, plus:

- [ ] Published paper or accepted conference presentation
- [ ] External adoption (someone else uses the system)
- [ ] Industry interest / meetings with target companies
- [ ] Open source release with documentation good enough for others to replicate

---

## Part VIII-B: Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| ESP32forth limitations | Missing features for tracing/safety | Fall back to Mecrisp on RP2040 |
| FlashForth not maintained | No Forth on AVR dumb nodes | Fork, or accept C for dumb nodes |
| ATtiny1614 supply issues | Can't build sensor adapters | Design also supports ATmega328P |
| RS-485 adds cost/complexity | Educational adoption suffers | TTL mode requires no transceivers |
| Protocol too limited | Power users frustrated | Forth escape hatch always available |
| Text protocol too slow | Can't capture fast signals | Local buffering + DMA on capable nodes |
| Safety features insufficient | Users brick nodes anyway | Terminal-side backup is last resort |
| Scope creep | Project never finishes | Strict phase gates, MVP first |

---

## Part IX: The Demo Script

### Setup

**On table:**
- Dumb terminal (RPi Zero + screen + keyboard) — powered on, showing cursor
- One "blank" smart node — powered, connected to terminal
- One sensor adapter with DHT22 — powered, connected to smart node
- Keyboard for terminal
- No laptop visible anywhere

### Script (10 minutes)

**[0:00] Opening**

"What you see here is a complete embedded development environment. There's no computer. No IDE. No cloud. Just a $25 terminal and some microcontrollers."

**[0:30] Identity**

Type: `?`

"Every node in this system can explain what it is."

*Node responds with identity block.*

**[1:00] Explain**

Type: `explain`

"Not just metadata. A complete description of what it does, how it's configured, and its history."

*Node responds with natural language explanation.*

**[1:30] Source**

Type: `source`

"Including its own source code. The device contains everything needed to understand it."

*Node lists its Forth definitions.*

**[2:00] Scan**

Type: `scan`

"The node can introspect its own hardware. It knows what's connected to its pins."

*Node reports pin states with guesses.*

**[2:30] Query child**

Type: `@sensor ?`

"This smart node has a sensor attached. I can query it through the network."

*Sensor responds with its identity.*

**[3:00] Sample**

Type: `@sensor s`

"Take a reading."

*Sensor returns humidity value.*

**[3:30] Live programming**

"Now I'll modify the sensor's behavior. No upload. No compile cycle. Just typing."

Type: `@sensor define : sample dht22-read dup dup . fifo-push ;`

Type: `@sensor save`

"That change is now permanent. The sensor will keep running that code even if I disconnect."

**[4:30] Trace mode**

Type: `trace on`

Type: `sample`

"I can watch computation happen. See the stack transform, the calls nest."

*Trace output displays, terminal visualizes stack.*

Type: `trace off`

**[5:30] History**

Type: `@sensor history`

"Every change is logged. I can see who modified this node, when, and what they changed."

*History displays.*

**[6:00] Rollback**

Type: `@sensor rollback 1`

"And I can undo it."

*Confirms rollback.*

**[6:30] Disconnect**

*Physically unplug the sensor node.*

"The sensor keeps running. It doesn't need the network. It doesn't need the terminal. It just works."

*Reconnect.*

Type: `@sensor n`

"See? It's been collecting data the whole time."

**[7:00] The point**

"This is what embedded computing looked like in 1970. Interactive. Transparent. Self-contained. We gave it up for heavyweight toolchains and cloud dependencies.

This project is a proof that we can have it back.

Every node in this system will work in 50 years. No server to shut down. No company to go bankrupt. No subscription to expire. Just power it on and talk to it.

The cloud is a design failure. This is what we should have built."

**[8:00] Questions**

---

## Part X: Appendices

### Appendix A: Forth Resources

**ESP32forth:**
- Source: https://esp32forth.appspot.com/ESP32forth.html
- Documentation: https://github.com/flagxor/eforth
- Target: ESP32 (primary choice for smart nodes)
- Features: WiFi words, multitasking, blocks, good documentation

**Mecrisp-Stellaris (fallback):**
- Source: https://mecrisp.sourceforge.net/
- Documentation: included in distribution
- Target: ARM Cortex-M (RP2040, STM32)

**FlashForth:**
- Source: https://flashforth.com/
- Documentation: https://flashforth.com/doc.html
- Target: ATmega, PIC (dumb nodes)

**Learning Forth:**
- "Starting Forth" by Leo Brodie (free online)
- "Thinking Forth" by Leo Brodie (free online)

### Appendix B: Reference Designs

**Qwiic/STEMMA (I2C ecosystem):**
- SparkFun Qwiic: https://www.sparkfun.com/qwiic
- Adafruit STEMMA QT: https://learn.adafruit.com/introducing-adafruit-stemma-qt

Note: These are I2C only. Our system differs by using UART and supporting code upload, not just data.

**Grove (multi-protocol):**
- Seeed Grove: https://wiki.seeedstudio.com/Grove_System/

Note: Grove has multiple connector types for different protocols. Our system unifies them.

### Appendix C: Previous Conversation Summary

[Include the summary block from our earlier conversation for context transfer to collaborators or future sessions.]

---

## Part XI: Contact & Revision History

**Project Lead:** Nikolai Kozak  
**Program:** NYU ITP  
**Expected Completion:** Spring 2025

**Revision History:**

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-12-30 | Initial document |

---

*"The past contains unrealized futures. I build them."*
