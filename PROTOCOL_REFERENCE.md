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
| `explain` | — | Identity + command list | Describe capabilities |
| `source` | — | Forth listing | Show all code |
| `history` | — | Modification log | Who changed what |
| `meta` | `[key] [value]` | Key/value | Read or set persisted metadata |
| `diff` | `N` | Diff output | Show change N *(planned on-node; use terminal-side diff for now)* |
| `rollback` | `N` | `! ok` | Revert to state N |
| `scan` | — | Pin analysis | What's connected *(planned)* |
| `trace` | `on/off` | — | Enable tracing *(planned)* |
| `define` | `: word ... ;` | `! ok` | Compile Forth (single-line: `define : foo 123 ;`) |
| `save` | — | `! ok` | Persist to flash |
| `restart` | — | `! rebooting` | Reboot node |
| `repl` | — | `! ok` | Exit protocol mode to REPL (dev) |
| `pins` | — | Pin dump | List GPIO states (Milestone E) |
| `pin-status` | `<pin>` | Pin line | One GPIO state line (Milestone E) |
| `pin-claim` | `<pin> <owner>` | `! ok` | Claim ownership label (Milestone E) |
| `pin-release` | `<pin>` | `! ok` | Release ownership (Milestone E) |
| `pin-mode` | `<pin> in\|out [pull=up\|down\|none]` | `! ok` | Configure GPIO (Milestone E) |
| `pin-read` | `<pin>` | `! value <0\|1>` | Read GPIO level (Milestone E) |
| `pin-write` | `<pin> 0\|1` | `! ok` | Write GPIO level (Milestone E) |

### Safety Commands (All Nodes)

| Command | Arguments | Response | Description |
|---------|-----------|----------|-------------|
| `validate` | — | `! ok` or `! fail <reason>` | Check system sanity |
| `safe-save` | — | `! ok` or `! fail` | Validate then save |
| `recover` | — | `! ok` | Factory reset (erase saved image) |

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
! role <role>
! mcu <chip>
! ver <version>         ← from `meta ver` (default: `codignity-0.1`)
! board <board-id>      ← optional (if set via `meta board`)
! fifo <size>
! units <units>         ← optional (if set via `meta`)
! pins <pins>           ← optional (if set via `meta`)
! children <count>
! end
```

Child descriptors (`! child ...`) are planned for Milestone D routing; currently only `children` is reported.

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
! id <name>
! role <role>
! mcu <chip>
! ver <version>         ← from `meta ver` (default: `codignity-0.1`)
! board <board-id>      ← optional
! units <units>         ← optional
! pins <pins>           ← optional
! children <count>
! fifo <size>
! core <cmd> <cmd> ...
! extended <cmd> <cmd> ...
! end
```

### Pins Response (`pins`)

```
! board <board-id>      ← optional
! pin gpio=<n> mode=<mode> level=<0|1|-> pull=<none|up|down> owner=<token|-> flags=<csv|->
! ...
! end
```

Pin tokens accepted by pin commands: `<n>`, `D<n>`, `GPIO<n>`.

### Pin Read Response (`pin-read`)

```
! value <0|1>
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
! <ts> <event> [args...]
! <ts> <event> [args...]
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
