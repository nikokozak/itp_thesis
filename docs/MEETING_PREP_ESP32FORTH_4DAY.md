# Deep-Dive Prep (4 days × ~2h): ESP32 DevKit V1 + ESP32forth + Bedrock

You have ~8 focused hours. The win condition is not “know everything”; it’s: (1) clear mental models, (2) crisp answers, (3) knowing what to measure when you *don’t* know.

This plan is optimized for a conversation with someone who will go deep (hardware, boot chain, timing, firmware architecture, language/runtime tradeoffs).

---

## Success Criteria (What “Ready” Looks Like)

By the end of Day 4 you can:

- Explain (on a whiteboard) how your ESP32 boots, runs, and is updated in <2 minutes.
- Explain how ESP32forth compiles/runs words + how you persist/restore state in <2 minutes.
- Explain your “always answerable” story (and the limits) in <2 minutes.
- Answer follow-ups with confidence *or* with a credible “I’d verify it like this” method.

Your outputs:

- A 1-page cheat sheet: **boot + memory + serial + Forth runtime**.
- A 10-question mock Q&A with your own short answers.

---

## Your Exact Stack (So Your Explanations Match Reality)

Hardware:

- ESP32 DOIT **DevKit V1**.
- SAFE/escape hatch: `GPIO4` wired to GND (see `firmware/esp32/bedrock.fs`).

Firmware/runtime:

- **ESP32forth v7 / ForthESP32** (ueForth-derived) as the base runtime (Arduino sketch): `firmware/esp32/esp32forth/.../ESP32forth.ino`.
- Bedrock protocol firmware: `firmware/esp32/bedrock.fs` loaded into ESP32forth.

Transport/protocol:

- USB serial (UART via USB-to-UART bridge), typically `115200 8N1`.
- Line-oriented commands; responses always terminate with `! end` (see `PROTOCOL_REFERENCE.md`).

Persistence + autostart (what’s actually happening on-device):

- ESP32forth `remember` saves the current image to `/spiffs/myforth`; `revive` restores it.
- ESP32forth `autoexec` tries `/spiffs/autoexec.fs` first, then falls back to `revive`.
- Restore ends by executing `'cold` if it is non-zero; Bedrock sets `'cold` to `br-boot` before saving, so the node autostarts into protocol mode unless SAFE is held.

Reload safety:

- `firmware/esp32/bedrock.fs` uses a `br-dev` + `forget` anchor (and forgets legacy `cd-dev`) to avoid dictionary growth crashes on repeated reloads.

---

## Practical Reality: Flashing + Connecting (DevKit V1)

### Flashing ESP32forth (once, or when you update the base runtime)

Your “core” flash step is effectively:

```sh
arduino-cli --config-file tools/arduino/arduino-cli.yaml compile \
  --fqbn esp32:esp32:esp32doit-devkit-v1 \
  --build-path .arduino/build/esp32forth \
  --upload -p /dev/cu.usbserial-0001 \
  firmware/esp32/esp32forth/ESP32forth-7.0.6.19/ESP32forth
```

What to be able to explain if asked:

- The ESP32 has a ROM bootloader + flash app images.
- Upload tools toggle reset/boot mode (often via DTR/RTS lines on DevKit boards) to enter UART download mode and write flash.

### Connecting over serial without sabotaging boot

On many DevKit boards, opening the serial port toggles control lines and can reset the ESP32.

What you do about it (and can say out loud):

- Wait a “quiet settle” period (~4–5s) after opening the port so ESP32forth `autoexec` can `revive` the saved image (sending bytes too early can interrupt boot).
- If you *want* to interrupt autoexec and enter the raw REPL (e.g. to reload code), you can open the port and send a safe no-op like `sp0 sp!` quickly.

In this repo, the tooling already encodes this idea:

- `tools/terminal/bedrock_cli.py` uses a short settle when it wants to interrupt autoexec (`load`), and a longer settle when it wants autoexec to complete (`probe`/normal commands).

---

## Meeting Story (The 3 Explanations You’ll Rehearse)

### 1) “How does a microcontroller run your program?”

Keep it concrete:

- Reset happens → ROM bootloader checks boot pins → loads app from flash → runtime init → your main loop/task runs forever.
- Flash holds program + persistent image; RAM holds stacks/buffers/current state.
- Peripherals are memory-mapped and driven by registers/interrupts.

### 2) “How does Forth compile/run on the ESP32?”

Your clean explanation:

- Forth is an interactive compiler: typing `: name ... ;` compiles a new “word” into the dictionary *on device*.
- Words are dictionary entries (name + metadata + code pointer + parameters/body).
- The interpreter reads tokens, looks them up, and either executes them (interpret state) or compiles them (compile state).
- You persist the current dictionary image with `remember` (Bedrock wraps this behind `save`/`safe-save`).

### 3) “How do you stay answerable while doing ‘real work’?”

Your clean explanation:

- You separate “control work” (sensor/LED loop) from “command loop” (protocol).
- In ESP32forth, cooperative tasks exist (`task`, `pause`). If your control loop yields (`pause`/`ms`) regularly, the command loop stays responsive.
- You avoid background printing on the UART because it corrupts a strict line protocol; instead you buffer logs and fetch them via a command.
- Hard limits: if the VM wedges (hard fault, interrupts disabled too long, runaway non-yielding loop), software can’t guarantee responsiveness—so you keep a physical SAFE pin escape hatch.

---

## Day 1 (2h): MCU Boot + Memory + “Where the code lives”

**Goal:** whiteboard “reset → boot → runtime → your app” and explain flash/RAM/peripherals cleanly.

### 0:00–0:10 — Setup (don’t skip)

- Confirm you can connect to your board.
- Run: `?` and `explain` once using your usual workflow so you’re not debugging tooling during prep.

### 0:10–1:00 — Build the mental model (watch/read)

- Modern Embedded Systems Programming (Miro Samek): focus on startup, vector table, and “what the linker does”.
  - https://www.state-machine.com/video-course/
- ESP-IDF “Memory Types” (skim): IRAM/DRAM vs flash-mapped code/data.
  - https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-guides/memory-types.html

### 1:00–1:30 — Output: 1-page sketch

Draw a single page:

- Reset causes → ROM bootloader → flash app → runtime init → loop/tasks.
- Flash vs RAM vs memory-mapped peripherals.
- Where your Forth image lives (`/spiffs/myforth`) vs where “right now” state lives (RAM).

### 1:30–2:00 — Practice out loud

Record a voice memo and iterate until it’s clean:

- “How does the ESP32 boot into our protocol loop?”
- “Where does the firmware live and how does it get updated?”

---

## Day 2 (2h): Interrupts, Timing, UART, and Reset-on-Connect

**Goal:** answer “how do you keep real-time-ish behavior and still be interactive?”

### 0:00–0:15 — Your system-specific drill

Read these once (not forever), then explain them in your own words:

- `PROTOCOL_REFERENCE.md`
- `firmware/esp32/bedrock.fs` (skim: the protocol loop, `br-node`, `br-handle-line`, `br-boot`, SAFE pin)

### 0:15–1:00 — Conceptual resources (fast, not textbook)

- Arduino interrupts overview (concepts transfer):  
  https://forum.dronebotworkshop.com/2022-videos/understanding-arduino-interrupts-hardware-pin-change-timer-interrupts/
- RTOS basics (so you can contrast with cooperative scheduling):  
  https://www.digikey.com/en/maker/projects/introduction-to-rtos-solution-to-arduino-limitations/959f80c0c3cd4ed8b8f2b6d3c78c0b21

### 1:00–1:30 — Output: “Always answerable” constraints list

Write 10 bullets:

- Things that *break* responsiveness (interrupts off, long critical sections, blocking I/O without timeouts, runaway loop without `pause`, hard fault, brownout).
- Things you do to *preserve* it (yield points, bounded work per loop iteration, watchdog strategy, safe boot pin).

### 1:30–2:00 — Practice “connecting story”

Have a clean, no-drama explanation ready:

- Why opening serial can reset a DevKit.
- Why you wait before sending bytes (to let `autoexec` → `revive` finish).
- How your tooling intentionally interrupts autoexec when you *want* a REPL.

---

## Day 3 (2h): Forth You Can Explain (without sounding mystical)

**Goal:** confidently explain dictionary + stacks + interpret/compile state.

### 0:00–0:15 — Hands-on warmup (on your actual device)

In REPL mode (SAFE held at boot if needed), run:

- `words` (what is a “vocabulary/wordlist”?)
- `see <word>` (decompilation exists; it’s introspectable)
- `.s` / `depth` (show stack thinking)

### 0:15–1:15 — Read (friendly, high yield)

- Starting Forth (online): focus on early chapters + “under the hood”.
  - https://www.forth.com/starting-forth/

### 1:15–1:40 — Implementation intuition (dictionary structure)

- A quick dictionary-structure overview (NFA/LFA/CFA/PFA language):  
  https://arduino-forth.com/article/FORTH_learn_dictStructure

### 1:40–2:00 — Output: “Forth in 90 seconds” script

Write a short script you can say verbatim. Include:

- “interactive compiler”
- “dictionary”
- “interpret vs compile state”
- “persistence via saved image”

---

## Day 4 (2h): ESP32forth specifics + Bedrock specifics + full rehearsal

**Goal:** answer “how does this specific firmware behave” questions.

### 0:00–0:30 — ESP32forth specifics (read/skim)

- ESP32forth reference:  
  https://esp32forth.appspot.com/ESP32forth.html

Focus on:

- Tasks: `task`, `pause`, `ms` (cooperative scheduling model).
- Files + persistence: `remember`, `revive`, `startup:`, `autoexec`.

### 0:30–1:10 — Bedrock specifics (your own code)

Skim and be able to point to:

- `firmware/esp32/bedrock.fs`:
  - reload anchor (`br-dev` + `forget`)
  - protocol loop (`br-node`)
  - SAFE boot behavior (`br-safe-gpio`, `br-boot`)
  - persistence behavior (`save`, `safe-save`)
- `tools/terminal/bedrock_cli.py`:
  - settle logic (interrupt vs allow autoexec)
  - load path / persist path

### 1:10–2:00 — Mock interview (say it out loud)

Do 10 questions. Keep answers short. If you don’t know: say how you’d verify.

Suggested prompts:

1) “What exactly happens at power-on on your DevKit?”
2) “How do you update firmware? What’s in flash vs SPIFFS?”
3) “Why Forth instead of C++/Arduino sketches?”
4) “How do you guarantee the device stays interactive while sampling/controlling?”
5) “What are the failure modes? What does SAFE do?”
6) “How do you avoid corrupting the protocol with logging?”
7) “What’s the worst thing that can happen if a user defines a bad word?”
8) “What does `save` mean in your system? What gets persisted?”
9) “How would you port this to another MCU?”
10) “What’s your story for child nodes / UART routing?”

---

## Two “Mentor Moves” That Great Technical Conversations Use

### 1) Answer → then name the uncertainty boundary

Example:

- “In our current build it’s cooperative tasks; as long as the control loop yields, the protocol stays responsive.”
- “If you want a hard guarantee under wedged conditions, you need external debug/reset or a hardware watchdog policy.”

### 2) If you don’t know: propose the measurement

“I don’t know offhand, but I can verify by (a) dumping the boot log, (b) toggling DTR/RTS and observing reset causes, and (c) measuring latency under load with a timestamped ping command.”

That reads as competence, not weakness.

---

## Optional (if you have 30 extra minutes): Make a “demo script” for yourself

Write the exact sequence you’ll run in front of him, including timing pauses:

- connect → `?` → `explain` → show a live `define` → show `history`/`source` → `safe-save` → reboot → show it autostarts → show SAFE pin escape hatch.

Keep it boringly reliable.
