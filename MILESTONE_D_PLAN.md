# Milestone D: Multi-Node Routing + ATtiny Dumb Node

## Overview

Extend Codignity to support multi-node topologies:
- Gateway (ESP32) routes commands to child nodes via `@name cmd`
- "Dumb node" (ATtiny) implements minimal protocol: `? s n d c validate`
- CLI/TUI can probe and sample from any node in the tree

## Scope

### In Scope
- Gateway-side routing: parse `@name`, forward to bus, relay response
- ATtiny firmware: minimal C implementing core protocol subset
- CLI: `@node` prefix for all commands (e.g., `send "@sensor1 s"`)
- Probe displays child list with bus/name/mcu

### Out of Scope (Milestone E+)
- Broadcast (`*cmd`)
- Multi-hop routing (`@a @b cmd`)
- RS-485 addressing/collision handling
- OTA updates for child nodes

## Protocol Subset for Dumb Nodes

ATtiny nodes implement only:

| Command | Response |
|---------|----------|
| `?` | `! id <name>` `! mcu attiny<model>` `! fifo <size>` `! end` |
| `s` | `! <value> <timestamp>` `! end` |
| `n` | `! <count>` `! end` |
| `d [N]` | `! <ts> <val>` (repeated) `! end` |
| `c` | `! ok` `! end` |
| `validate` | `! ok` `! end` |

No `define`, `meta`, `save`, `history`, `source`, `explain`, `repl`.

## Gateway Routing

When gateway receives `@name cmd`:
1. Look up `name` in child table (populated via `meta children`)
2. Forward `cmd` to appropriate bus (UART/I2C/RS-485)
3. Read response until `! end`
4. Relay response back (prefix with routing context if needed)

Error handling:
- `# err notfound` if `name` not in child table
- `# err timeout` if child doesn't respond
- `# err bus` if bus communication fails

## ATtiny Implementation

### Minimal Hardware
- ATtiny84/85 or ATtiny1614/1616 (modern series)
- Single ADC input (sensor)
- UART (software or hardware) to gateway
- Optional: level shifter if 5V logic

### Firmware Structure
```c
// Core state
uint16_t fifo[FIFO_SIZE];
uint8_t fifo_head, fifo_count;
char node_id[8];

// Protocol handlers
void cmd_identity(void);   // ?
void cmd_sample(void);     // s
void cmd_count(void);      // n
void cmd_dump(void);       // d
void cmd_clear(void);      // c
void cmd_validate(void);   // validate
```

### Memory Budget
- ~256 bytes FIFO (128 samples @ 16-bit)
- ~64 bytes for command parsing
- ~2KB flash for protocol handling

## CLI Changes

Add `@name` prefix support:
```bash
codignity_cli.py send "@sensor1 ?" --port /dev/cu.usbserial-0001
codignity_cli.py send "@sensor1 s" --port /dev/cu.usbserial-0001
```

Probe shows children:
```
Node ID: gateway
Role: gateway
Children: 2
  [0] uart1: sensor1 (attiny84)
  [1] uart2: sensor2 (attiny1614)
```

## Acceptance Transcript Target

```
# Milestone D Acceptance
# Setup: ESP32 gateway + 1 ATtiny child on UART1

## 1. Probe gateway (shows child)
$ codignity_cli.py probe
Node ID: gateway
Children: 1
  [0] uart1: sensor1 (attiny84)

## 2. Probe child via routing
$ codignity_cli.py send "@sensor1 ?"
! id sensor1
! mcu attiny84
! fifo 64
! end

## 3. Sample from child
$ codignity_cli.py send "@sensor1 s"
! 12345 512
! end

## 4. Dump child FIFO
$ codignity_cli.py send "@sensor1 d 5"
! 12340 510
! 12341 511
! 12342 512
! 12343 513
! 12344 514
! end
```

---

## Hardware Questions for Niko

Before implementation, please clarify:

1. **ATtiny model**: Which ATtiny variant?
   - Classic (ATtiny84/85): 8-bit, software UART, limited flash
   - Modern (ATtiny1614/1616/3216): Hardware UART, more flash, easier

2. **Bus type**: How does gateway talk to child?
   - UART (point-to-point, simplest)
   - I2C (multi-drop, but limited cable length)
   - RS-485 (multi-drop, long cables, needs addressing)

3. **Level shifting**: Do we need 3.3V↔5V conversion?
   - ESP32 is 3.3V logic
   - Classic ATtiny is typically 5V
   - Modern ATtiny can run at 3.3V

4. **Child count**: How many children per gateway?
   - 1-2: Simple UART per child
   - 3+: Need I2C or RS-485 bus

5. **Addressing scheme**: How is `@name` resolved?
   - Fixed at compile time (node_id in ATtiny flash)
   - Dynamic via handshake (more complex)

6. **Sensor type**: What ADC input?
   - Analog voltage (0-3.3V or 0-5V)
   - Specific sensor (thermistor, LDR, etc.)

---

## Implementation Phases

### Phase 1: Gateway Routing (Forth)
- Add `@name` parser to `codignity.fs`
- Child table in meta (`children`, `child 0 uart1 sensor1 attiny84`)
- Forward logic for UART bus

### Phase 2: ATtiny Firmware (C)
- Bootstrap with Arduino or bare-metal
- Implement `? s n d c validate`
- Test with USB-serial adapter first

### Phase 3: Integration
- Wire ATtiny to ESP32 UART
- End-to-end routing test
- CLI `@name` support

### Phase 4: Polish
- Timeout handling
- Error propagation
- Multiple children
