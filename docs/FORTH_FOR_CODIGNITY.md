# Forth for Codignity

A practical guide to programming Codignity nodes. This is not a complete Forth tutorial—just enough to be productive with the Codignity protocol and define custom behaviors.

## The Stack Model

Forth uses a data stack. Values are pushed, operations consume and produce values.

```
42        ( push 42 onto stack )
10        ( push 10 )
+         ( pop two values, push their sum: 52 )
.         ( pop and print top value )
```

Stack effect notation shows what a word consumes and produces:

```
+      ( a b -- sum )       \ add two numbers
dup    ( n -- n n )         \ duplicate top
drop   ( n -- )             \ discard top
swap   ( a b -- b a )       \ exchange top two
over   ( a b -- a b a )     \ copy second to top
rot    ( a b c -- b c a )   \ rotate third to top
-rot   ( a b c -- c a b )   \ rotate top to third
```

### Quick Stack Practice

```forth
1 2 3       \ stack: 1 2 3
rot         \ stack: 2 3 1
dup         \ stack: 2 3 1 1
+           \ stack: 2 3 2
swap        \ stack: 2 2 3
drop        \ stack: 2 2
*           \ stack: 4
.           \ prints: 4
```

---

## Defining Words

In raw Forth, you define new words with `: name ... ;`:

```forth
: square   ( n -- n² )   dup * ;
5 square .   \ prints 25
```

In Codignity protocol mode, use the `define` command:

```
define : square dup * ;
```

The word is compiled immediately and available for use.

### Variables and Constants

```forth
variable counter          \ create a variable
0 counter !               \ store 0 in counter
counter @                 \ fetch value (push to stack)
counter @ 1+ counter !    \ increment

123 constant magic        \ create a constant
magic .                   \ prints 123
```

### Control Flow

```forth
: abs   ( n -- |n| )
  dup 0 < if negate then ;

: sign   ( n -- -1|0|1 )
  dup 0 < if drop -1 exit then
  0 > if 1 else 0 then ;

: countdown   ( n -- )
  begin dup . 1- dup 0= until drop ;
```

---

## Codignity Protocol Commands

These commands work in protocol mode (after loading Codignity firmware).

### Identity and Metadata

```
?                  \ show node identity
meta               \ dump all metadata
meta id            \ get node ID
meta role mynode   \ set role to "mynode"
explain            \ describe available commands
source             \ show source code of user definitions
history            \ show command history
```

### Pin Operations

```
pins               \ list all GPIO pins with state
pin-status 4       \ show GPIO4 details

pin-claim 4 led    \ claim GPIO4, owner="led"
pin-release 4      \ release ownership

pin-mode 4 out     \ set GPIO4 as output
pin-mode 4 in pull=up   \ set as input with pull-up

pin-read 4         \ read GPIO4 level (0 or 1)
pin-write 4 1      \ set GPIO4 high
pin-write 4 0      \ set GPIO4 low
```

Pin tokens accept multiple formats: `4`, `D4`, `GPIO4`.

### Safety Flags

- `safe` — GPIO4 is the SAFE pin (grounding enters REPL)
- `strapping` — boot configuration pins (dangerous to change)
- `flash` — used for SPI flash (never modify)
- `input-only` — GPIO34-39 cannot output

The firmware refuses dangerous operations on protected pins.

### Persistence

```
safe-save          \ save current state to flash
restart            \ reboot the node
validate           \ verify firmware integrity
rollback           \ restore from backup (if available)
```

---

## Inspecting the System

Forth has built-in introspection tools:

```forth
words              \ list all defined words
see square         \ decompile a word
depth              \ push current stack depth
.s                 \ print stack non-destructively
```

In Codignity, also use:

```
source             \ show user definitions
history            \ show recent commands
explain            \ describe protocol commands
```

---

## 10-Minute Exercises

### Exercise 1: Blink an LED

Connect an LED to GPIO2 (onboard LED on many boards).

```
pin-claim 2 led
pin-mode 2 out
define : blink 2 pin-read 1 xor 2 swap pin-write ;
define : blink-loop 10 0 do blink 500 ms loop ;
blink-loop
```

### Exercise 2: Read a Button

Connect a button between GPIO4 (SAFE) and GND.

```
pin-mode 4 in pull=up
define : button? 4 pin-read 0 = ;
define : wait-press begin button? until ;
define : wait-release begin button? 0= until ;
```

### Exercise 3: Simple Counter

Count button presses and display on serial.

```
variable presses
0 presses !

define : bump presses @ 1+ dup presses ! . cr ;
define : counter-loop begin wait-press bump wait-release again ;
```

### Exercise 4: Temperature Logger (with sensor)

If you have a temperature sensor on ADC:

```
define : read-temp 36 adc@ 100 * 4095 / ;   \ scale to approximate °C
define : log-temp read-temp . ." C" cr ;
define : logger 10 0 do log-temp 1000 ms loop ;
```

### Exercise 5: Multi-Node Communication

On a smart node (gateway), send commands to children:

```
meta children             \ check connected nodes
child 1 "meta role sensor1" send
child 1 "define : ping 42 emit ;" send
child 1 "ping" send
```

---

## Common Patterns

### Debounce a Button

```forth
: debounced?   ( gpio -- flag )
  dup pin-read 0= if         \ first check
    10 ms                     \ wait
    pin-read 0=               \ confirm still pressed
  else
    drop false
  then ;
```

### Heartbeat LED

```forth
variable heartbeat-gpio
2 heartbeat-gpio !

: heartbeat
  heartbeat-gpio @ dup
  pin-read 1 xor swap pin-write
  500 ms ;

: heartbeat-forever begin heartbeat again ;
```

### State Machine

```forth
variable state
0 constant IDLE
1 constant ACTIVE
2 constant ERROR

: set-idle   IDLE state ! ;
: set-active ACTIVE state ! ;
: set-error  ERROR state ! ;

: handle-state
  state @ case
    IDLE of   ." Waiting..." cr endof
    ACTIVE of ." Running..." cr endof
    ERROR of  ." Error!" cr endof
  endcase ;
```

---

## Tips and Gotchas

1. **Stack underflow** — Make sure you have enough values before operations. Use `.s` to inspect.

2. **Forgetting to consume** — Every value pushed must eventually be dropped or used.

3. **Integer only** — Forth uses integers. For decimals, scale up (e.g., 3.14 → 314).

4. **Flash wear** — Don't `safe-save` in a loop. Flash has limited write cycles.

5. **SAFE pin escape** — If stuck, ground GPIO4 and reset to enter REPL mode.

6. **Protocol vs REPL** — In protocol mode, responses end with `! end`. In REPL mode, with ` ok`.

---

## Further Reading

- **Starting Forth** by Leo Brodie — Classic introduction (free online)
- **Thinking Forth** by Leo Brodie — Philosophy of Forth programming
- **Mecrisp-Stellaris** — The Forth implementation Codignity extends
- **ESP32 Technical Reference** — For understanding GPIO, ADC, peripherals
