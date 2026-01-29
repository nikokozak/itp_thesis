# Bedrock Protocol (Thesis)

This repository is the working spec and (soon) prototype for **self-describing embedded systems**: small “nodes” that can explain themselves, show their own source, record their own modification history, and be reprogrammed interactively over a simple text protocol.

## Start Here

- `PROJECT_SPEC.md`: thesis framing, architecture, safety model, demo script, schedule
- `PROTOCOL_REFERENCE.md`: protocol quick reference (commands, responses, wire format)
- `CONTEXT_TRANSFER.md`: short project recap to restore context quickly

## Current Status

Docs/specs are present alongside working ESP32 firmware (`firmware/esp32/bedrock.fs`) and terminal tooling (`tools/terminal/`). The initial baseline target is **ESP32 + ESP32forth** for the smart node, with **ATtiny (C)** as the first “dumb node / sensor adapter” implementation (in progress).

## Principles (Non-Negotiable)

- Human-readable, line-oriented protocol; always terminates responses with `! end`.
- No cloud dependency for operation or understanding.
- Prefer simple, inspectable tools and formats that will still be legible decades from now.
