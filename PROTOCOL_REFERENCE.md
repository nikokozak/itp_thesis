# Protocol Quick Reference

## Command Summary

### Basic Commands (All Nodes)

| Command | Arguments | Response | Description |
|---------|-----------|----------|-------------|
| `?` | — | Identity block | Node identification |
| `s` | — | `! <value> <timestamp>` | Take sample now |
| `n` | — | `! <count>` | Buffer count |
| `d` | `[N]` | Data lines | Dump buffer (last N) |
| `c` | — | `! ok` | Clear buffer |

### Extended Commands (Smart Nodes)

| Command | Arguments | Response | Description |
|---------|-----------|----------|-------------|
| `explain` | — | Natural language | Full description |
| `source` | — | Forth listing | Show all code |
| `history` | — | Modification log | Who changed what |
| `diff` | `N` | Diff output | Show change N |
| `rollback` | `N` | `! ok` | Revert to state N |
| `scan` | — | Pin analysis | What's connected |
| `trace` | `on/off` | — | Enable tracing |
| `define` | `: word ... ;` | `! ok` | Compile Forth |
| `save` | — | `! ok` | Persist to flash |
| `restart` | — | — | Reboot node |

### Safety Commands (All Nodes)

| Command | Arguments | Response | Description |
|---------|-----------|----------|-------------|
| `validate` | — | `! ok` or `! fail <reason>` | Check system sanity |
| `safe-save` | — | `! ok` or `! fail` | Validate then save |
| `recover` | — | Reboot message | Factory reset (erase user code) |

### Routing

| Syntax | Meaning |
|--------|---------|
| `@name cmd` | Send `cmd` to child named `name` |
| `@name @sub cmd` | Route through `name` to `sub` |
| `*cmd` | Broadcast to all (RS-485) |

## Response Format

```
! key value           ← data line
! key value           ← data line (can repeat)
# error message       ← error (optional)
! end                 ← terminator (required)
```

### Identity Response (`?`)

```
! id <name>
! mcu <chip>
! ver <version>
! fifo <size>
! pins <list>
! children <count>      ← smart nodes only
! child <n> <bus> <name> <mcu>
! end
```

### Sample Response (`s`)

```
! <value> <timestamp>
! end
```

### Dump Response (`d`)

```
! <value> <timestamp>
! <value> <timestamp>
! ...
! end
```

### Explain Response (`explain`)

```
! I am a <type> sensor node.
! I sample a <device> on pin <n>.
! I take a reading every <interval>.
! ... (natural language continues)
! end
```

### Source Response (`source`)

```
! : word1 ... ;
! : word2 ... ;
! : main ... ;
! end
```

### History Response (`history`)

```
! <timestamp> <source>
!   <action>: <details>
! <timestamp> <source>
!   <action>: <details>
! end
```

### Scan Response (`scan`)

```
! PIN <n>: <mode> <state> <details> guess:<type>
! PIN <n>: <mode> <state> <details> guess:<type>
! end
```

### Trace Output

```
! TRACE <word>
!   ( <stack-before> )
!   call <subword>
!     ( <stack-after> )
!   exit
! end
```

### Error Response

```
# err <code>
# <details>
! end
```

## Connector Pinout

```
┌─────────────────────────────┐
│  1  VCC    (3.3V)           │
│  2  GND                     │
│  3  DATA+  (TX / RS-485 A)  │
│  4  DATA-  (RX / RS-485 B)  │
│  5  MODE   (GND=TTL, VCC=485)│
│  6  SAFE   (GND=boot safe)  │
└─────────────────────────────┘
```

## Serial Settings

| Parameter | Value |
|-----------|-------|
| Baud rate | 115200 (default) |
| Data bits | 8 |
| Parity | None |
| Stop bits | 1 |
| Flow control | None |

## Forth Parsing Pattern

```forth
\ Parse response line
: parse-response ( -- )
  parse-name              \ get first token
  s" !" compare 0= if     \ data line
    parse-name            \ key
    parse-name            \ value
    process-kv
  else
    s" #" compare 0= if   \ error line
      parse-name handle-error
    then
  then ;
```
