"""Screen management and state machine for Codignity TUI.

IO worker maintains a persistent SerialSession that is reused across commands.
- First probe: 5s settle (allow autoexec to complete)
- Subsequent commands: instant (no settle)
- Settle required again after: port change, serial error, load --persist, restore

TODO(thesis): TUI wizards are functional but need polish:
- Load wizard: Add cancel-during-load support, better error display
- Snapshot wizard: Add filename editing, show defs count before create
- Restore wizard: Improve diff preview, add cancel-during-restore
- General: Keyboard shortcuts shown in wizard frames, consistent styling
- Testing: Needs hardware testing of all wizard flows end-to-end
"""

from __future__ import annotations

import curses
import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from .theme import (
    init_colors,
    KEY_HINTS,
    BANNER_HEIGHT,
    COLOR_BORDER,
    COLOR_DIM,
    COLOR_ERROR,
    COLOR_KEY_HINT,
    COLOR_MENU_SELECTED,
    COLOR_PANEL,
    COLOR_PROMPT,
    COLOR_SUCCESS,
    COLOR_TITLE,
    COLOR_WARNING,
)
from .widgets import (
    draw_banner,
    draw_chrome_line,
    draw_frame,
    draw_status_bar,
    draw_key_hints,
    LogPane,
    Menu,
    MenuItem,
    draw_confirm_dialog,
    draw_input_dialog,
    draw_message,
    draw_progress_bar,
    draw_wizard_frame,
    Checkbox,
    FileBrowser,
)

if TYPE_CHECKING:
    from ..session import SerialSession
    from ..protocol import ProbeResult


class Screen(Enum):
    """Screen states."""

    HOME = auto()
    MENU = auto()
    CONFIRM = auto()
    INPUT = auto()
    MESSAGE = auto()
    HELP = auto()
    LOAD_WIZARD = auto()
    SNAPSHOT_WIZARD = auto()
    RESTORE_WIZARD = auto()
    PINS = auto()  # Pins Inspector screen


class Action(Enum):
    """Actions that can be triggered."""

    QUIT = auto()
    PROBE = auto()
    META = auto()
    HISTORY = auto()
    SOURCE = auto()
    VALIDATE = auto()
    LOAD = auto()
    SNAPSHOT = auto()
    RESTORE = auto()
    CLEAR = auto()
    SEND = auto()
    HELP = auto()
    PINS = auto()  # Open Pins Inspector
    PIN_CLAIM = auto()  # Claim pin (after input prompt)


@dataclass
class AppState:
    """Application state."""

    screen: Screen = Screen.HOME
    port: str = ""
    connected: bool = False
    mode: str = "unknown"
    node_id: str | None = None
    role: str | None = None
    ver: str | None = None
    mcu: str | None = None
    units: str | None = None
    pins: str | None = None
    children: int | None = None
    fifo_size: int | None = None
    log: LogPane = field(default_factory=LogPane)
    menu: Menu | None = None
    confirm_message: str = ""
    confirm_action: Action | None = None
    input_prompt: str = ""
    input_value: str = ""
    input_cursor: int = 0
    input_action: Action | None = None
    message: str = ""
    message_is_error: bool = False
    running: bool = True
    last_error: str | None = None

    # IO queue for serial operations
    io_queue: queue.Queue = field(default_factory=queue.Queue)
    result_queue: queue.Queue = field(default_factory=queue.Queue)

    # Load wizard state
    load_progress: float = 0.0
    load_total_lines: int = 0
    load_current_line: int = 0
    load_persist: Checkbox = field(default_factory=lambda: Checkbox("Persist to flash after loading"))
    load_status: str = ""
    load_running: bool = False

    # Snapshot wizard state
    snapshot_filename: str = ""
    snapshot_defs_count: int = 0
    snapshot_safe_save: Checkbox = field(default_factory=lambda: Checkbox("Run safe-save before snapshot"))
    snapshot_status: str = ""

    # Restore wizard state
    restore_file_browser: FileBrowser | None = None
    restore_snapshot_path: str = ""
    restore_preview: list[str] = field(default_factory=list)
    restore_progress: float = 0.0
    restore_status: str = ""
    restore_running: bool = False

    # Pins Inspector state
    pins_data: dict = field(default_factory=dict)  # gpio -> PinState
    pins_board_id: str | None = None
    pins_selected: int = 0  # Currently selected GPIO index
    pins_gpios: list = field(default_factory=list)  # Sorted list of GPIO numbers
    pins_loading: bool = False
    pins_action_gpio: int | None = None  # GPIO for pending action


def create_main_menu(state: AppState) -> Menu:
    """Create the main menu."""
    connected = state.connected

    items = [
        MenuItem("Probe / Connect", "p", enabled=True),
        MenuItem("Pins Inspector", "g", enabled=connected),
        MenuItem("Refresh Meta", "m", enabled=connected),
        MenuItem("History", "h", enabled=connected),
        MenuItem("Source", "s", enabled=connected),
        MenuItem("Validate", "v", enabled=connected),
        MenuItem("Load Firmware", "l", enabled=True),
        MenuItem("Create Snapshot", "c", enabled=connected),
        MenuItem("Restore Snapshot", "r", enabled=True),
        MenuItem("Help", "?", enabled=True),
        MenuItem("Clear Log", "x", enabled=True),
        MenuItem("Quit", "q", enabled=True),
    ]

    return Menu("Codignity", items)


def handle_menu_select(state: AppState, key: str) -> Action | None:
    """Map menu selection key to action."""
    key_map = {
        "p": Action.PROBE,
        "g": Action.PINS,
        "m": Action.META,
        "h": Action.HISTORY,
        "s": Action.SOURCE,
        "v": Action.VALIDATE,
        "l": Action.LOAD,
        "c": Action.SNAPSHOT,
        "r": Action.RESTORE,
        "?": Action.HELP,
        "x": Action.CLEAR,
        "q": Action.QUIT,
    }
    return key_map.get(key.lower())


def _do_load(state: AppState, persist: bool) -> None:
    """Execute load operation (runs in io_worker thread)."""
    from ..session import SerialSession, SerialError
    from ..protocol import probe, is_error
    from pathlib import Path

    # Find firmware file
    firmware_path = Path(__file__).parent.parent.parent.parent.parent / "firmware" / "esp32" / "codignity.fs"
    if not firmware_path.exists():
        state.result_queue.put(("load_error", f"Firmware not found: {firmware_path}"))
        return

    # Read firmware lines
    with open(firmware_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip() for line in f if line.strip() and not line.strip().startswith("\\")]

    total_lines = len(lines)
    state.result_queue.put(("load_start", total_lines))

    try:
        # Open session with short settle to interrupt autoexec
        with SerialSession.open(port=state.port or None, settle_s=2.0, quiet=False) as session:
            # Send interrupt to stop autoexec
            session.send_line("sp0 sp!")
            time.sleep(0.3)
            session.drain(0.2)

            # Load each line
            for i, line in enumerate(lines):
                if not line:
                    continue
                session.send_repl(line, timeout_s=5.0)
                state.result_queue.put(("load_progress", i + 1, total_lines))

            # Enter protocol mode
            state.result_queue.put(("load_status", "Entering protocol mode..."))
            session.drain(0.2)
            session.send_line("revive")
            session.read_until(b" ok", 3.0)
            session.drain(0.3)

            # Validate
            state.result_queue.put(("load_status", "Validating..."))
            response = session.send_protocol("validate", timeout_s=3.0)
            has_err, err_msg = is_error(response)
            if has_err:
                state.result_queue.put(("load_error", f"Validation failed: {err_msg}"))
                return

            # Persist if requested
            if persist:
                state.result_queue.put(("load_status", "Saving to flash..."))
                response = session.send_protocol("safe-save", timeout_s=5.0)
                has_err, err_msg = is_error(response)
                if has_err:
                    state.result_queue.put(("load_error", f"Safe-save failed: {err_msg}"))
                    return

                state.result_queue.put(("load_status", "Restarting..."))
                session.send_protocol("restart", timeout_s=3.0)

        state.result_queue.put(("load_done", persist))

    except SerialError as e:
        state.result_queue.put(("load_error", str(e)))


def _do_snapshot_create(state: AppState, filename: str, safe_save: bool) -> None:
    """Execute snapshot create operation (runs in io_worker thread)."""
    from ..session import SerialSession, SerialError
    from ..protocol import probe, is_error
    from ..snapshot import Snapshot
    from ..defs_log import load_defs
    from pathlib import Path
    from datetime import datetime, timezone

    try:
        with SerialSession.open(port=state.port or None, settle_s=5.0) as session:
            # Probe for identity
            result = probe(session, timeout_s=3.0)
            node_id = result.node_id or "unknown"

            # Get meta dump
            response = session.send_protocol("meta", timeout_s=3.0)
            meta = {}
            for line in response.splitlines():
                if line.startswith("! ") and not line.startswith("! end"):
                    parts = line[2:].split(" ", 1)
                    if len(parts) == 2:
                        meta[parts[0]] = parts[1]

            # Load defs from log
            defs = load_defs(node_id)

            # Safe-save if requested
            if safe_save:
                state.result_queue.put(("snapshot_status", "Running safe-save..."))
                response = session.send_protocol("safe-save", timeout_s=5.0)
                has_err, err_msg = is_error(response)
                if has_err:
                    state.result_queue.put(("snapshot_error", f"Safe-save failed: {err_msg}"))
                    return

            # Create snapshot
            snapshot = Snapshot(
                date=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                node_id=node_id,
                role=result.role or "",
                ver=result.ver or "",
                meta=meta,
                defs=defs,
                notes={},
            )

            # Save to file
            snapshot.save(Path(filename))
            state.result_queue.put(("snapshot_done", filename, len(defs)))

    except SerialError as e:
        state.result_queue.put(("snapshot_error", str(e)))
    except Exception as e:
        state.result_queue.put(("snapshot_error", f"Unexpected error: {e}"))


def _do_restore_preview(state: AppState, snapshot_path: str) -> None:
    """Load snapshot and generate preview (runs in io_worker thread)."""
    from ..snapshot import Snapshot
    from pathlib import Path

    try:
        snapshot = Snapshot.load(Path(snapshot_path))
        preview = [
            f"Date: {snapshot.date}",
            f"Node: {snapshot.node_id} ({snapshot.role})",
            f"Version: {snapshot.ver}",
            f"Meta: {len(snapshot.meta)} settings",
            f"Defs: {len(snapshot.defs)} definitions",
        ]
        if snapshot.defs:
            preview.append("")
            preview.append("Definitions:")
            for d in snapshot.defs[:5]:
                # Extract name from define
                name = d.split()[2] if len(d.split()) > 2 else d[:30]
                preview.append(f"  + {name}")
            if len(snapshot.defs) > 5:
                preview.append(f"  ... and {len(snapshot.defs) - 5} more")

        state.result_queue.put(("restore_preview_ok", preview))

    except Exception as e:
        state.result_queue.put(("restore_preview_error", str(e)))


def _do_restore(state: AppState, snapshot_path: str) -> None:
    """Execute restore operation (runs in io_worker thread)."""
    from ..session import SerialSession, SerialError
    from ..protocol import probe, is_error
    from ..snapshot import Snapshot
    from pathlib import Path

    try:
        snapshot = Snapshot.load(Path(snapshot_path))

        # Find firmware
        firmware_path = Path(__file__).parent.parent.parent.parent.parent / "firmware" / "esp32" / "codignity.fs"
        if not firmware_path.exists():
            state.result_queue.put(("restore_error", f"Firmware not found: {firmware_path}"))
            return

        with open(firmware_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip() for line in f if line.strip() and not line.strip().startswith("\\")]

        total_steps = len(lines) + len(snapshot.meta) + len(snapshot.defs) + 3  # +3 for validate, save, restart
        current_step = 0

        with SerialSession.open(port=state.port or None, settle_s=2.0, quiet=False) as session:
            # Interrupt autoexec
            session.send_line("sp0 sp!")
            time.sleep(0.3)
            session.drain(0.2)

            # Load firmware
            state.result_queue.put(("restore_status", "Loading firmware..."))
            for i, line in enumerate(lines):
                if not line:
                    continue
                session.send_repl(line, timeout_s=5.0)
                current_step += 1
                state.result_queue.put(("restore_progress", current_step / total_steps))

            # Enter protocol mode
            state.result_queue.put(("restore_status", "Entering protocol mode..."))
            session.drain(0.2)
            session.send_line("revive")
            session.read_until(b" ok", 3.0)
            session.drain(0.3)

            # Apply meta settings
            state.result_queue.put(("restore_status", "Applying meta settings..."))
            for key, value in snapshot.meta.items():
                cmd = f"meta {key} {value}"
                response = session.send_protocol(cmd, timeout_s=3.0)
                has_err, err_msg = is_error(response)
                if has_err:
                    state.result_queue.put(("restore_error", f"Meta error: {err_msg}"))
                    return
                current_step += 1
                state.result_queue.put(("restore_progress", current_step / total_steps))

            # Apply definitions
            state.result_queue.put(("restore_status", "Applying definitions..."))
            for defn in snapshot.defs:
                response = session.send_protocol(defn, timeout_s=3.0)
                has_err, err_msg = is_error(response)
                if has_err:
                    state.result_queue.put(("restore_error", f"Define error: {err_msg}"))
                    return
                current_step += 1
                state.result_queue.put(("restore_progress", current_step / total_steps))

            # Validate
            state.result_queue.put(("restore_status", "Validating..."))
            response = session.send_protocol("validate", timeout_s=3.0)
            has_err, err_msg = is_error(response)
            if has_err:
                state.result_queue.put(("restore_error", f"Validation failed: {err_msg}"))
                return
            current_step += 1
            state.result_queue.put(("restore_progress", current_step / total_steps))

            # Save
            state.result_queue.put(("restore_status", "Saving to flash..."))
            response = session.send_protocol("safe-save", timeout_s=5.0)
            has_err, err_msg = is_error(response)
            if has_err:
                state.result_queue.put(("restore_error", f"Safe-save failed: {err_msg}"))
                return
            current_step += 1
            state.result_queue.put(("restore_progress", current_step / total_steps))

            # Restart
            state.result_queue.put(("restore_status", "Restarting..."))
            session.send_protocol("restart", timeout_s=3.0)
            current_step += 1
            state.result_queue.put(("restore_progress", 1.0))

        # Re-probe after restart
        time.sleep(2)
        with SerialSession.open(port=state.port or None, settle_s=5.0) as session:
            result = probe(session, timeout_s=3.0)
            state.result_queue.put(("restore_done", result.node_id, result.role))

    except SerialError as e:
        state.result_queue.put(("restore_error", str(e)))
    except Exception as e:
        state.result_queue.put(("restore_error", f"Unexpected error: {e}"))


def io_worker(state: AppState) -> None:
    """Background worker for serial I/O.

    Maintains a persistent SerialSession that is reused across commands for low latency.
    The session is only reopened on:
    - First probe (with 5s settle to allow autoexec to complete)
    - Port change
    - Fatal serial error
    - After load/restore wizards (which use their own sessions)
    """
    from ..session import SerialSession, SerialError
    from ..protocol import probe, ensure_protocol, is_error

    # Persistent session - reused across commands for speed
    persistent_session: SerialSession | None = None
    session_port: str | None = None  # Track which port the session is for
    needs_settle: bool = True  # True when next open needs settle (device may have rebooted)

    def close_persistent(device_rebooting: bool = False) -> None:
        """Close the persistent session if open.

        Args:
            device_rebooting: If True, next open will need settle time for autoexec.
        """
        nonlocal persistent_session, session_port, needs_settle
        if persistent_session is not None:
            try:
                persistent_session.close()
            except Exception:
                pass
            persistent_session = None
            session_port = None
        if device_rebooting:
            needs_settle = True

    def get_session(port: str | None = None) -> SerialSession:
        """Get the persistent session, opening if needed.

        Args:
            port: Target port (uses state.port if None).

        Returns:
            The SerialSession to use.
        """
        nonlocal persistent_session, session_port, needs_settle
        target_port: str | None = port or state.port or None
        if target_port == "":
            target_port = None

        # Reuse existing session if port matches (or no explicit target port).
        if persistent_session is not None:
            if target_port is None or session_port == target_port:
                return persistent_session

        # Port changed or no session - close old and open new
        close_persistent()
        settle_s = 5.0 if needs_settle else 0.0
        persistent_session = SerialSession.open(port=target_port, settle_s=settle_s)
        session_port = persistent_session.port
        needs_settle = False  # Settle done
        return persistent_session

    try:
        while state.running:
            try:
                task = state.io_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            action, *args = task

            try:
                if action == "probe":
                    port = args[0] if args else state.port
                    # Port change requires settle (close existing session)
                    if port and session_port and port != session_port:
                        close_persistent()
                    session = get_session(port)
                    result = probe(session, timeout_s=3.0)
                    state.result_queue.put(("probe_ok", result, session.port))

                elif action == "send":
                    cmd = args[0]
                    if not state.connected:
                        state.result_queue.put(("error", "Not connected"))
                        continue

                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol(cmd, timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("response", response, err_msg))
                    else:
                        state.result_queue.put(("response", response, None))

                elif action == "meta":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("meta", timeout_s=3.0)
                    state.result_queue.put(("meta_ok", response))

                elif action == "history":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("history", timeout_s=3.0)
                    state.result_queue.put(("history_ok", response))

                elif action == "source":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("source", timeout_s=3.0)
                    state.result_queue.put(("source_ok", response))

                elif action == "validate":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("validate", timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("validate_fail", err_msg))
                    else:
                        state.result_queue.put(("validate_ok", response))

                elif action == "load":
                    # Load opens its own session - close ours so it doesn't interfere
                    # After load (especially with persist), device may reboot
                    persist = args[0] if args else False
                    close_persistent(device_rebooting=persist)
                    _do_load(state, persist)

                elif action == "snapshot_create":
                    # Snapshot opens its own session, no device reboot
                    close_persistent()
                    filename = args[0] if args else "snapshot.cdsnap"
                    safe_save = args[1] if len(args) > 1 else False
                    _do_snapshot_create(state, filename, safe_save)

                elif action == "restore_preview":
                    snapshot_path = args[0]
                    _do_restore_preview(state, snapshot_path)

                elif action == "restore":
                    # Restore opens its own session and reboots device
                    close_persistent(device_rebooting=True)
                    snapshot_path = args[0]
                    _do_restore(state, snapshot_path)

                elif action == "pins":
                    from ..pins import parse_pins_response
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("pins", timeout_s=5.0)
                    board_id, pins_data = parse_pins_response(response)
                    state.result_queue.put(("pins_ok", board_id, pins_data))

                elif action == "pin_claim":
                    gpio = args[0]
                    owner = args[1]
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol(f"pin-claim {gpio} {owner}", timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("pin_action_error", f"Claim failed: {err_msg}"))
                    else:
                        state.result_queue.put(("pin_action_ok", f"GPIO{gpio} claimed by {owner}"))
                        # Refresh pins after action
                        state.io_queue.put(("pins",))

                elif action == "pin_release":
                    gpio = args[0]
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol(f"pin-release {gpio}", timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("pin_action_error", f"Release failed: {err_msg}"))
                    else:
                        state.result_queue.put(("pin_action_ok", f"GPIO{gpio} released"))
                        state.io_queue.put(("pins",))

                elif action == "pin_mode":
                    gpio = args[0]
                    mode = args[1]
                    pull = args[2] if len(args) > 2 else None
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    cmd = f"pin-mode {gpio} {mode}"
                    if pull:
                        cmd += f" pull={pull}"
                    response = session.send_protocol(cmd, timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("pin_action_error", f"Mode change failed: {err_msg}"))
                    else:
                        state.result_queue.put(("pin_action_ok", f"GPIO{gpio} set to {mode}"))
                        state.io_queue.put(("pins",))

                elif action == "pin_write":
                    gpio = args[0]
                    value = args[1]
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol(f"pin-write {gpio} {value}", timeout_s=3.0)
                    has_err, err_msg = is_error(response)
                    if has_err:
                        state.result_queue.put(("pin_action_error", f"Write failed: {err_msg}"))
                    else:
                        state.result_queue.put(("pin_action_ok", f"GPIO{gpio} = {value}"))
                        state.io_queue.put(("pins",))

            except SerialError as e:
                # Serial error - close session so next command reconnects
                close_persistent()
                state.result_queue.put(("error", str(e)))
            except Exception as e:
                state.result_queue.put(("error", f"Unexpected error: {e}"))
    finally:
        # Clean up on exit
        close_persistent()


def process_results(state: AppState) -> None:
    """Process results from the IO worker."""
    while True:
        try:
            result = state.result_queue.get_nowait()
        except queue.Empty:
            break

        result_type = result[0]

        if result_type == "probe_ok":
            probe_result = result[1]
            port = result[2]
            state.port = port
            state.mode = probe_result.mode
            state.node_id = probe_result.node_id
            state.role = probe_result.role
            state.ver = probe_result.ver
            state.mcu = probe_result.mcu
            state.fifo_size = probe_result.fifo
            state.units = probe_result.units
            state.pins = probe_result.pins
            state.children = probe_result.children
            state.connected = True
            state.last_error = None

            state.log.append(f"Connected to {port}", COLOR_SUCCESS)
            state.log.append(f"  Node: {state.node_id or 'unknown'}")
            state.log.append(f"  Role: {state.role or 'unknown'}")
            state.log.append(f"  Mode: {state.mode}")

        elif result_type == "error":
            error_msg = result[1]
            state.log.append(f"Error: {error_msg}", COLOR_ERROR)
            state.last_error = error_msg

        elif result_type == "response":
            response = result[1]
            error = result[2]
            state.log.append(response)
            if error:
                state.log.append(f"Error: {error}", COLOR_ERROR)

        elif result_type == "meta_ok":
            from ..protocol import parse_meta_dump

            response = result[1]
            meta = parse_meta_dump(response)

            if "id" in meta:
                state.node_id = meta["id"] or state.node_id
            if "role" in meta:
                state.role = meta["role"] or state.role
            if "ver" in meta:
                state.ver = meta["ver"] or state.ver
            if "mcu" in meta:
                state.mcu = meta["mcu"] or state.mcu
            if "units" in meta:
                state.units = meta["units"] or state.units
            if "pins" in meta:
                state.pins = meta["pins"] or state.pins

            if "fifo" in meta:
                try:
                    state.fifo_size = int(meta["fifo"].strip())
                except ValueError:
                    pass
            if "children" in meta:
                try:
                    state.children = int(meta["children"].strip())
                except ValueError:
                    pass

            state.log.append(f"Meta refreshed ({len(meta)} keys)", COLOR_SUCCESS)
            for key in ("mcu", "units", "pins", "children"):
                if key in meta and meta[key]:
                    state.log.append(f"  {key}: {meta[key]}")

        elif result_type in ("history_ok", "source_ok"):
            response = result[1]
            state.log.append(response)

        elif result_type == "validate_ok":
            state.log.append("Validation passed", COLOR_SUCCESS)

        elif result_type == "validate_fail":
            error_msg = result[1]
            state.log.append(f"Validation failed: {error_msg}", COLOR_ERROR)

        # Load wizard results
        elif result_type == "load_start":
            state.load_total_lines = result[1]
            state.load_current_line = 0
            state.load_progress = 0.0
            state.load_status = "Loading firmware..."

        elif result_type == "load_progress":
            state.load_current_line = result[1]
            state.load_total_lines = result[2]
            state.load_progress = result[1] / result[2] if result[2] > 0 else 0

        elif result_type == "load_status":
            state.load_status = result[1]

        elif result_type == "load_done":
            persist = result[1]
            state.load_running = False
            state.load_progress = 1.0
            state.load_status = "Load complete!" + (" (persisted)" if persist else "")
            state.log.append("Firmware loaded successfully", COLOR_SUCCESS)
            state.screen = Screen.HOME

        elif result_type == "load_error":
            error_msg = result[1]
            state.load_running = False
            state.load_status = f"Error: {error_msg}"
            state.log.append(f"Load failed: {error_msg}", COLOR_ERROR)

        # Snapshot wizard results
        elif result_type == "snapshot_status":
            state.snapshot_status = result[1]

        elif result_type == "snapshot_done":
            filename = result[1]
            defs_count = result[2]
            state.log.append(f"Snapshot saved: {filename} ({defs_count} defs)", COLOR_SUCCESS)
            state.screen = Screen.HOME

        elif result_type == "snapshot_error":
            error_msg = result[1]
            state.snapshot_status = f"Error: {error_msg}"
            state.log.append(f"Snapshot failed: {error_msg}", COLOR_ERROR)

        # Restore wizard results
        elif result_type == "restore_preview_ok":
            state.restore_preview = result[1]

        elif result_type == "restore_preview_error":
            error_msg = result[1]
            state.restore_preview = [f"Error loading snapshot: {error_msg}"]

        elif result_type == "restore_status":
            state.restore_status = result[1]

        elif result_type == "restore_progress":
            state.restore_progress = result[1]

        elif result_type == "restore_done":
            node_id = result[1]
            role = result[2]
            state.restore_running = False
            state.restore_progress = 1.0
            state.restore_status = "Restore complete!"
            state.node_id = node_id
            state.role = role
            state.connected = True
            state.log.append(f"Restored successfully: {node_id} ({role})", COLOR_SUCCESS)
            state.screen = Screen.HOME

        elif result_type == "restore_error":
            error_msg = result[1]
            state.restore_running = False
            state.restore_status = f"Error: {error_msg}"
            state.log.append(f"Restore failed: {error_msg}", COLOR_ERROR)

        # Pins Inspector results
        elif result_type == "pins_ok":
            board_id = result[1]
            pins_data = result[2]
            state.pins_data = pins_data
            state.pins_board_id = board_id
            state.pins_gpios = sorted(pins_data.keys())
            state.pins_loading = False
            state.log.append(f"Pins loaded ({len(pins_data)} GPIOs)", COLOR_SUCCESS)

        elif result_type == "pin_action_ok":
            message = result[1]
            state.log.append(message, COLOR_SUCCESS)

        elif result_type == "pin_action_error":
            message = result[1]
            state.log.append(message, COLOR_ERROR)


def handle_input(state: AppState, key: int) -> None:
    """Handle keyboard input based on current screen."""
    if state.screen == Screen.HOME:
        handle_home_input(state, key)
    elif state.screen == Screen.MENU:
        handle_menu_input(state, key)
    elif state.screen == Screen.CONFIRM:
        handle_confirm_input(state, key)
    elif state.screen == Screen.INPUT:
        handle_text_input(state, key)
    elif state.screen == Screen.MESSAGE:
        # Any key dismisses message
        state.screen = Screen.HOME
    elif state.screen == Screen.HELP:
        handle_help_input(state, key)
    elif state.screen == Screen.LOAD_WIZARD:
        handle_load_wizard_input(state, key)
    elif state.screen == Screen.SNAPSHOT_WIZARD:
        handle_snapshot_wizard_input(state, key)
    elif state.screen == Screen.RESTORE_WIZARD:
        handle_restore_wizard_input(state, key)
    elif state.screen == Screen.PINS:
        handle_pins_input(state, key)


def handle_home_input(state: AppState, key: int) -> None:
    """Handle input on the home screen."""
    if key == ord("q") or key == ord("Q"):
        state.running = False
    elif key == ord("\t") or key == curses.KEY_F1:
        state.menu = create_main_menu(state)
        state.screen = Screen.MENU
    elif key == ord("?"):
        execute_action(state, Action.HELP)
    elif key == ord("p") or key == ord("P"):
        execute_action(state, Action.PROBE)
    elif key == ord("m") or key == ord("M"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.META)
    elif key == ord("h") or key == ord("H"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.HISTORY)
    elif key == ord("s") or key == ord("S"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.SOURCE)
    elif key == ord("v") or key == ord("V"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.VALIDATE)
    elif key == ord("l") or key == ord("L"):
        execute_action(state, Action.LOAD)
    elif key == ord("c") or key == ord("C"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.SNAPSHOT)
    elif key == ord("r") or key == ord("R"):
        execute_action(state, Action.RESTORE)
    elif key == ord("g") or key == ord("G"):
        if not state.connected:
            state.log.append("Not connected (press p to probe)", COLOR_ERROR)
        else:
            execute_action(state, Action.PINS)
    elif key == ord("x") or key == ord("X"):
        execute_action(state, Action.CLEAR)
    elif key in (curses.KEY_UP, ord("k")):
        state.log.scroll_up(1)
    elif key in (curses.KEY_DOWN, ord("j")):
        state.log.scroll_down(1)
    elif key == curses.KEY_PPAGE:
        state.log.scroll_up(5)
    elif key == curses.KEY_NPAGE:
        state.log.scroll_down(5)
    elif key == curses.KEY_HOME:
        state.log.scroll_to_top()
    elif key == curses.KEY_END:
        state.log.scroll_to_bottom()
    elif key == ord("\n") or key == ord("\r"):
        # Prompt for command
        state.input_prompt = "Command:"
        state.input_value = ""
        state.input_cursor = 0
        state.input_action = Action.SEND
        state.screen = Screen.INPUT


def handle_menu_input(state: AppState, key: int) -> None:
    """Handle input on the menu screen."""
    if state.menu is None:
        state.screen = Screen.HOME
        return

    if key == 27:  # Escape
        state.screen = Screen.HOME
    elif key == curses.KEY_UP or key == ord("k"):
        state.menu.move_up()
    elif key == curses.KEY_DOWN or key == ord("j"):
        state.menu.move_down()
    elif key == ord("\n") or key == ord("\r"):
        item = state.menu.get_selected()
        if item.enabled:
            action = handle_menu_select(state, item.key)
            execute_action(state, action)
    else:
        # Check for direct key press
        ch = chr(key) if 32 <= key < 127 else ""
        action = handle_menu_select(state, ch)
        if action:
            execute_action(state, action)


def handle_confirm_input(state: AppState, key: int) -> None:
    """Handle input on confirm dialog."""
    if key == ord("y") or key == ord("Y"):
        if state.confirm_action:
            execute_confirmed_action(state, state.confirm_action)
        state.screen = Screen.HOME
    elif key == ord("n") or key == ord("N") or key == 27:
        state.screen = Screen.HOME


def handle_help_input(state: AppState, key: int) -> None:
    """Handle input on the help overlay."""
    if key in (27, ord("q"), ord("Q"), ord("?")):
        state.screen = Screen.HOME
    elif key == ord("\t"):
        state.menu = create_main_menu(state)
        state.screen = Screen.MENU


def handle_text_input(state: AppState, key: int) -> None:
    """Handle text input dialog."""
    if key == 27:  # Escape
        # Return to appropriate screen based on action
        if state.input_action == Action.PIN_CLAIM:
            state.screen = Screen.PINS
        else:
            state.screen = Screen.HOME
        state.pins_action_gpio = None
        try:
            curses.curs_set(0)
        except curses.error:
            pass
    elif key == ord("\n") or key == ord("\r"):
        if state.input_action == Action.SEND and state.input_value:
            state.log.append(f"> {state.input_value}")
            state.io_queue.put(("send", state.input_value))
            state.screen = Screen.HOME
        elif state.input_action == Action.PIN_CLAIM and state.input_value:
            # Execute pin claim with entered owner
            gpio = state.pins_action_gpio
            owner = state.input_value.strip()
            if gpio is not None and owner:
                state.io_queue.put(("pin_claim", gpio, owner))
            state.pins_action_gpio = None
            state.screen = Screen.PINS
        else:
            state.screen = Screen.HOME
        try:
            curses.curs_set(0)
        except curses.error:
            pass
    elif key == curses.KEY_BACKSPACE or key == 127:
        if state.input_cursor > 0:
            state.input_value = (
                state.input_value[: state.input_cursor - 1]
                + state.input_value[state.input_cursor :]
            )
            state.input_cursor -= 1
    elif key == curses.KEY_LEFT:
        state.input_cursor = max(0, state.input_cursor - 1)
    elif key == curses.KEY_RIGHT:
        state.input_cursor = min(len(state.input_value), state.input_cursor + 1)
    elif 32 <= key < 127:
        ch = chr(key)
        state.input_value = (
            state.input_value[: state.input_cursor]
            + ch
            + state.input_value[state.input_cursor :]
        )
        state.input_cursor += 1


def handle_load_wizard_input(state: AppState, key: int) -> None:
    """Handle input on the load wizard screen."""
    if state.load_running:
        # Can't interact while loading
        return

    if key == 27:  # Escape
        state.screen = Screen.HOME
    elif key == ord(" "):
        # Toggle persist checkbox
        state.load_persist.toggle()
    elif key == ord("\n") or key == ord("\r"):
        # Start loading
        state.load_running = True
        state.load_status = "Starting load..."
        state.io_queue.put(("load", state.load_persist.checked))


def handle_snapshot_wizard_input(state: AppState, key: int) -> None:
    """Handle input on the snapshot wizard screen."""
    if key == 27:  # Escape
        state.screen = Screen.HOME
    elif key == ord(" "):
        # Toggle safe-save checkbox
        state.snapshot_safe_save.toggle()
    elif key == ord("\n") or key == ord("\r"):
        # Start snapshot creation
        state.snapshot_status = "Creating snapshot..."
        state.io_queue.put(("snapshot_create", state.snapshot_filename, state.snapshot_safe_save.checked))


def handle_restore_wizard_input(state: AppState, key: int) -> None:
    """Handle input on the restore wizard screen."""
    if state.restore_running:
        # Can't interact while restoring
        return

    if key == 27:  # Escape
        if state.restore_snapshot_path:
            # Go back to file selection
            state.restore_snapshot_path = ""
            state.restore_preview = []
        else:
            state.screen = Screen.HOME
    elif state.restore_file_browser and not state.restore_snapshot_path:
        # File browser mode
        if key == curses.KEY_UP or key == ord("k"):
            state.restore_file_browser.move_up()
        elif key == curses.KEY_DOWN or key == ord("j"):
            state.restore_file_browser.move_down()
        elif key == ord("\n") or key == ord("\r"):
            result = state.restore_file_browser.select()
            if result:
                # File selected, load preview
                state.restore_snapshot_path = result
                state.io_queue.put(("restore_preview", result))
    elif state.restore_snapshot_path:
        # Preview mode
        if key == ord("\n") or key == ord("\r"):
            # Confirm restore
            state.restore_running = True
            state.restore_status = "Restoring..."
            state.io_queue.put(("restore", state.restore_snapshot_path))


def handle_pins_input(state: AppState, key: int) -> None:
    """Handle input on the Pins Inspector screen."""
    # Get selected GPIO
    selected_gpio = None
    if state.pins_gpios and 0 <= state.pins_selected < len(state.pins_gpios):
        selected_gpio = state.pins_gpios[state.pins_selected]

    if key == 27:  # Escape
        state.screen = Screen.HOME
    elif key == ord("r") or key == ord("R"):
        # Refresh pins
        state.pins_loading = True
        state.io_queue.put(("pins",))
    elif key == curses.KEY_UP or key == ord("k"):
        # Move selection up
        if state.pins_gpios and state.pins_selected > 0:
            state.pins_selected -= 1
    elif key == curses.KEY_DOWN or key == ord("j"):
        # Move selection down
        if state.pins_gpios and state.pins_selected < len(state.pins_gpios) - 1:
            state.pins_selected += 1
    elif key == curses.KEY_HOME:
        state.pins_selected = 0
    elif key == curses.KEY_END:
        if state.pins_gpios:
            state.pins_selected = len(state.pins_gpios) - 1
    elif key == ord("c") or key == ord("C"):
        # Claim selected pin - prompt for owner
        if selected_gpio is not None:
            state.pins_action_gpio = selected_gpio
            state.input_prompt = f"Owner for GPIO{selected_gpio}:"
            state.input_value = ""
            state.input_cursor = 0
            state.input_action = Action.PIN_CLAIM
            state.screen = Screen.INPUT
    elif key == ord("u") or key == ord("U"):
        # Release/unclaim selected pin
        if selected_gpio is not None:
            state.io_queue.put(("pin_release", selected_gpio))
    elif key == ord("t") or key == ord("T"):
        # Toggle pin (read then write opposite)
        if selected_gpio is not None:
            pin_state = state.pins_data.get(selected_gpio)
            if pin_state:
                # Safety check: refuse to toggle strapping/flash pins
                if pin_state.is_strapping() or pin_state.is_flash():
                    state.log.append(f"GPIO{selected_gpio} is dangerous (strapping/flash)", COLOR_ERROR)
                elif pin_state.level is not None:
                    new_value = 1 - pin_state.level
                    state.io_queue.put(("pin_write", selected_gpio, new_value))
                else:
                    state.log.append(f"GPIO{selected_gpio} level unknown, cannot toggle", COLOR_ERROR)
    elif key == ord("i") or key == ord("I"):
        # Set pin to input
        if selected_gpio is not None:
            pin_state = state.pins_data.get(selected_gpio)
            if pin_state and pin_state.is_flash():
                state.log.append(f"GPIO{selected_gpio} is a flash pin, cannot change mode", COLOR_ERROR)
            else:
                state.io_queue.put(("pin_mode", selected_gpio, "in", "up"))
    elif key == ord("o") or key == ord("O"):
        # Set pin to output
        if selected_gpio is not None:
            pin_state = state.pins_data.get(selected_gpio)
            if pin_state and (pin_state.is_flash() or pin_state.is_input_only()):
                flags_str = ",".join(pin_state.flags) if pin_state.flags else "restricted"
                state.log.append(f"GPIO{selected_gpio} cannot be set to output ({flags_str})", COLOR_ERROR)
            else:
                state.io_queue.put(("pin_mode", selected_gpio, "out"))


def execute_action(state: AppState, action: Action | None) -> None:
    """Execute an action."""
    if action is None:
        return

    state.screen = Screen.HOME

    if action == Action.QUIT:
        state.running = False

    elif action == Action.PROBE:
        state.log.append("Probing device...")
        state.io_queue.put(("probe",))

    elif action == Action.META:
        state.log.append("Fetching metadata...")
        state.io_queue.put(("meta",))

    elif action == Action.HISTORY:
        state.log.append("Fetching history...")
        state.io_queue.put(("history",))

    elif action == Action.SOURCE:
        state.log.append("Fetching source...")
        state.io_queue.put(("source",))

    elif action == Action.VALIDATE:
        state.log.append("Running validation...")
        state.io_queue.put(("validate",))

    elif action == Action.CLEAR:
        state.log.lines.clear()
        state.log.scroll_offset = 0
    elif action == Action.HELP:
        state.screen = Screen.HELP

    elif action == Action.LOAD:
        # Initialize load wizard state
        state.load_progress = 0.0
        state.load_total_lines = 0
        state.load_current_line = 0
        state.load_persist.checked = False
        state.load_status = "Ready to load firmware"
        state.load_running = False
        state.screen = Screen.LOAD_WIZARD

    elif action == Action.SNAPSHOT:
        # Initialize snapshot wizard state
        from datetime import datetime
        state.snapshot_filename = f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.cdsnap"
        state.snapshot_defs_count = 0
        state.snapshot_safe_save.checked = False
        state.snapshot_status = ""
        state.screen = Screen.SNAPSHOT_WIZARD

    elif action == Action.RESTORE:
        # Initialize restore wizard state
        state.restore_file_browser = FileBrowser(path=".", filter_ext=".cdsnap")
        state.restore_snapshot_path = ""
        state.restore_preview = []
        state.restore_progress = 0.0
        state.restore_status = ""
        state.restore_running = False
        state.screen = Screen.RESTORE_WIZARD

    elif action == Action.PINS:
        # Open Pins Inspector screen and fetch pin data
        state.pins_loading = True
        state.screen = Screen.PINS
        state.io_queue.put(("pins",))


def execute_confirmed_action(state: AppState, action: Action) -> None:
    """Execute an action after confirmation."""
    # TODO(thesis): wire confirmation modal to destructive operations (e.g., restart/rollback).
    pass


def draw_help(win: curses.window, state: AppState) -> None:
    """Draw a help overlay (keyboard map + workflow)."""
    height, width = win.getmaxyx()
    frame_height = min(height - 2, 24)
    frame_width = min(width - 2, 78)

    if frame_height < 12 or frame_width < 44:
        try:
            msg = "Terminal too small for help"
            win.addstr(
                height // 2,
                max(0, (width - len(msg)) // 2),
                msg[: max(0, width - 1)],
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
        except curses.error:
            pass
        return

    y, x, inner_h, inner_w = draw_wizard_frame(win, "Help", frame_height, frame_width)
    if inner_h <= 0 or inner_w <= 0:
        return

    def add_line(row: int, text: str, color: int = COLOR_PANEL, attr: int = 0) -> None:
        try:
            win.addstr(
                row,
                x,
                text[:inner_w].ljust(inner_w),
                curses.color_pair(color) | attr,
            )
        except curses.error:
            pass

    def add_binding(row: int, key_label: str, desc: str, key_color: int = COLOR_PROMPT) -> None:
        key_col_w = min(10, inner_w)
        key_text = f"{key_label:<{key_col_w}}"
        key_text = key_text[:key_col_w]

        try:
            win.addstr(row, x, key_text, curses.color_pair(key_color) | curses.A_BOLD)
            win.addstr(
                row,
                x + key_col_w,
                desc[: max(0, inner_w - key_col_w)].ljust(max(0, inner_w - key_col_w)),
                curses.color_pair(COLOR_PANEL),
            )
        except curses.error:
            pass

    row = y + 1
    add_line(row, "CODIGNITY // CONTROL DECK — HELP", COLOR_TITLE, curses.A_BOLD)
    row += 1
    try:
        win.hline(row, x, curses.ACS_HLINE, min(inner_w, 60), curses.color_pair(COLOR_BORDER))
    except curses.error:
        pass
    row += 1

    row += 1
    add_line(row, "GLOBAL", COLOR_TITLE, curses.A_BOLD)
    row += 1
    add_binding(row, "Tab", "Menu", COLOR_PROMPT)
    row += 1
    add_binding(row, "Enter", "Send raw protocol line", COLOR_PROMPT)
    row += 1
    add_binding(row, "↑/↓", "Scroll log line   PgUp/PgDn Page   Home/End Jump", COLOR_PROMPT)

    row += 2
    add_line(row, "ACTIONS", COLOR_TITLE, curses.A_BOLD)
    row += 1
    add_binding(row, "p", "Probe / connect", COLOR_PROMPT)
    row += 1
    add_binding(row, "m/h/s/v", "Meta / History / Source / Validate", COLOR_PROMPT)
    row += 1
    add_binding(row, "l/c/r", "Load / Snapshot / Restore   g Pins   x Clear", COLOR_PROMPT)

    row += 2
    add_line(row, "PINS INSPECTOR", COLOR_TITLE, curses.A_BOLD)
    row += 1
    add_binding(row, "j/k", "Move   r Refresh   Esc Back", COLOR_PROMPT)
    row += 1
    add_binding(row, "c/u", "Claim / Release   i/o/t In / Out / Toggle", COLOR_PROMPT)

    row += 2
    add_binding(row, "Theme", "cyberpunk|classic (ENV: CODIGNITY_TUI_THEME)", COLOR_DIM)

    footer = "Esc: Close"
    add_line(y + inner_h - 1, footer, COLOR_KEY_HINT)


def draw_load_wizard(win: curses.window, state: AppState) -> None:
    """Draw the load firmware wizard."""
    y, x, inner_h, inner_w = draw_wizard_frame(win, "Load Codignity", 12, 50)

    try:
        # Status message
        win.addstr(y + 1, x, state.load_status[:inner_w].ljust(inner_w), curses.color_pair(COLOR_PANEL))

        # Progress bar (if loading)
        if state.load_running or state.load_progress > 0:
            lines_text = f"{state.load_current_line}/{state.load_total_lines} lines"
            draw_progress_bar(win, y + 3, x, inner_w, state.load_progress, lines_text)

        # Persist checkbox (only if not running)
        if not state.load_running:
            state.load_persist.draw(win, y + 5, x)

            # Instructions
            win.addstr(
                y + 7,
                x,
                "Press Enter to start loading".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
            win.addstr(
                y + 8,
                x,
                "Press Escape to cancel".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
        else:
            win.addstr(
                y + 7,
                x,
                "Loading in progress...".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )

    except curses.error:
        pass


def draw_snapshot_wizard(win: curses.window, state: AppState) -> None:
    """Draw the snapshot creation wizard."""
    y, x, inner_h, inner_w = draw_wizard_frame(win, "Create Snapshot", 14, 55)

    try:
        # Filename
        win.addstr(y + 1, x, "Filename:".ljust(inner_w), curses.color_pair(COLOR_TITLE) | curses.A_BOLD)
        win.addstr(
            y + 2,
            x,
            state.snapshot_filename[:inner_w].ljust(inner_w),
            curses.color_pair(COLOR_PROMPT) | curses.A_UNDERLINE,
        )

        # Node info
        if state.node_id:
            win.addstr(
                y + 4,
                x,
                f"Node: {state.node_id} ({state.role or 'unknown'})"[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_PANEL),
            )

        # Safe-save checkbox
        state.snapshot_safe_save.draw(win, y + 6, x)

        # Status
        if state.snapshot_status:
            win.addstr(
                y + 8,
                x,
                state.snapshot_status[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_PANEL),
            )

        # Instructions
        win.addstr(
            y + 10,
            x,
            "Press Enter to create snapshot".ljust(inner_w),
            curses.color_pair(COLOR_DIM) | curses.A_DIM,
        )
        win.addstr(
            y + 11,
            x,
            "Press Escape to cancel".ljust(inner_w),
            curses.color_pair(COLOR_DIM) | curses.A_DIM,
        )

    except curses.error:
        pass


def draw_restore_wizard(win: curses.window, state: AppState) -> None:
    """Draw the restore wizard."""
    if state.restore_snapshot_path:
        # Preview mode
        y, x, inner_h, inner_w = draw_wizard_frame(win, "Restore Snapshot", 18, 55)

        try:
            # Show snapshot path
            path_display = state.restore_snapshot_path
            if len(path_display) > inner_w:
                path_display = "..." + path_display[-(inner_w - 3):]
            win.addstr(
                y + 1,
                x,
                path_display[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )

            # Preview info
            for i, line in enumerate(state.restore_preview[:10]):
                if y + 3 + i < y + inner_h - 4:
                    win.addstr(
                        y + 3 + i,
                        x,
                        line[:inner_w].ljust(inner_w),
                        curses.color_pair(COLOR_PANEL),
                    )

            # Progress bar (if restoring)
            if state.restore_running:
                draw_progress_bar(win, y + inner_h - 4, x, inner_w, state.restore_progress)
                win.addstr(
                    y + inner_h - 3,
                    x,
                    state.restore_status[:inner_w].ljust(inner_w),
                    curses.color_pair(COLOR_PANEL),
                )
            else:
                # Instructions
                win.addstr(
                    y + inner_h - 3,
                    x,
                    "Press Enter to restore, Escape to go back"[:inner_w].ljust(inner_w),
                    curses.color_pair(COLOR_DIM) | curses.A_DIM,
                )

        except curses.error:
            pass
    else:
        # File browser mode
        y, x, inner_h, inner_w = draw_wizard_frame(win, "Select Snapshot", 16, 55)

        try:
            win.addstr(
                y + 1,
                x,
                "Select a .cdsnap file:".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )

            if state.restore_file_browser:
                state.restore_file_browser.draw(win, y + 3, x, inner_h - 5, inner_w)

            win.addstr(
                y + inner_h - 2,
                x,
                "Enter: Select, Escape: Cancel".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )

        except curses.error:
            pass


def draw_pins(win: curses.window, state: AppState) -> None:
    """Draw the Pins Inspector screen."""
    from ..boards import get_manifest

    height, width = win.getmaxyx()
    frame_height = min(height - 4, 35)
    frame_width = min(width - 4, 70)

    y, x, inner_h, inner_w = draw_wizard_frame(win, "Pins Inspector", frame_height, frame_width)

    try:
        if state.pins_loading:
            win.addstr(
                y + 1,
                x,
                "Loading pin data...".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
            return

        if not state.pins_data:
            win.addstr(
                y + 1,
                x,
                "No pin data. Press 'r' to refresh.".ljust(inner_w),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
            return

        # Get board manifest for footprint view
        board = None
        if state.pins_board_id:
            board = get_manifest(state.pins_board_id)

        # Get selected GPIO
        selected_gpio = None
        if state.pins_gpios and 0 <= state.pins_selected < len(state.pins_gpios):
            selected_gpio = state.pins_gpios[state.pins_selected]

        if board:
            # Board footprint view (two columns)
            left_pins = board.left_column()
            right_pins = board.right_column()
            max_rows = max(len(left_pins), len(right_pins))

            win.addstr(
                y + 1,
                x,
                board.display_name[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_TITLE) | curses.A_BOLD,
            )
            win.hline(y + 2, x, curses.ACS_HLINE, min(inner_w, 50), curses.color_pair(COLOR_BORDER))

            col1_x = x
            col2_x = x + 26  # Space for left column
            cell_w = 24

            for i in range(min(max_rows, inner_h - 6)):
                row_y = y + 4 + i

                # Left column
                if i < len(left_pins):
                    pin_def = left_pins[i]
                    cell = _format_pin_cell_tui(pin_def, state.pins_data, selected_gpio)
                    cell_attr = curses.color_pair(COLOR_PANEL)
                    if pin_def.gpio is not None:
                        ps = state.pins_data.get(pin_def.gpio)
                        if ps:
                            if ps.is_flash():
                                cell_attr = curses.color_pair(COLOR_ERROR)
                            elif ps.is_strapping():
                                cell_attr = curses.color_pair(COLOR_WARNING)
                            elif ps.is_safe():
                                cell_attr = curses.color_pair(COLOR_SUCCESS)
                    else:
                        cell_attr = curses.color_pair(COLOR_DIM)

                    if pin_def.gpio == selected_gpio:
                        cell_attr = curses.color_pair(COLOR_MENU_SELECTED) | curses.A_BOLD

                    win.addstr(row_y, col1_x, cell[:cell_w].ljust(cell_w), cell_attr)

                # Right column
                if i < len(right_pins):
                    pin_def = right_pins[i]
                    cell = _format_pin_cell_tui(pin_def, state.pins_data, selected_gpio)
                    cell_attr = curses.color_pair(COLOR_PANEL)
                    if pin_def.gpio is not None:
                        ps = state.pins_data.get(pin_def.gpio)
                        if ps:
                            if ps.is_flash():
                                cell_attr = curses.color_pair(COLOR_ERROR)
                            elif ps.is_strapping():
                                cell_attr = curses.color_pair(COLOR_WARNING)
                            elif ps.is_safe():
                                cell_attr = curses.color_pair(COLOR_SUCCESS)
                    else:
                        cell_attr = curses.color_pair(COLOR_DIM)

                    if pin_def.gpio == selected_gpio:
                        cell_attr = curses.color_pair(COLOR_MENU_SELECTED) | curses.A_BOLD

                    if col2_x + cell_w < x + inner_w:
                        win.addstr(row_y, col2_x, cell[:cell_w].ljust(cell_w), cell_attr)

        else:
            # Simple list view (no board manifest)
            win.addstr(
                y + 1,
                x,
                f"Board: {state.pins_board_id or 'unknown'}"[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_TITLE) | curses.A_BOLD,
            )

            list_start = y + 3
            visible_count = inner_h - 5

            for i, gpio in enumerate(state.pins_gpios[:visible_count]):
                state_data = state.pins_data.get(gpio)
                if state_data:
                    level = state_data.level if state_data.level is not None else "-"
                    owner = state_data.owner[:7] if state_data.owner else "-"
                    line = f"GPIO{gpio:02d}: M={state_data.mode[:3]:3s} L={level} O={owner}"
                else:
                    line = f"GPIO{gpio:02d}: ?"

                if gpio == selected_gpio:
                    attr = curses.color_pair(COLOR_MENU_SELECTED) | curses.A_BOLD
                elif state_data and state_data.is_dangerous():
                    attr = curses.color_pair(COLOR_WARNING)
                else:
                    attr = curses.color_pair(COLOR_PANEL)
                win.addstr(list_start + i, x, line[:inner_w].ljust(inner_w), attr)

        # Pin details box
        if selected_gpio is not None and selected_gpio in state.pins_data:
            pin_state = state.pins_data[selected_gpio]
            detail_y = y + inner_h - 5
            win.hline(detail_y, x, curses.ACS_HLINE, min(inner_w, 50), curses.color_pair(COLOR_BORDER))
            win.addstr(
                detail_y + 1,
                x,
                f"GPIO {selected_gpio}:"[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_TITLE) | curses.A_BOLD,
            )

            level = pin_state.level if pin_state.level is not None else "-"
            owner = pin_state.owner or "-"
            flags = ",".join(pin_state.flags) if pin_state.flags else "-"

            win.addstr(
                detail_y + 2,
                x,
                f"Mode: {pin_state.mode}  Level: {level}  Pull: {pin_state.pull}"[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_PANEL),
            )
            win.addstr(
                detail_y + 3,
                x,
                f"Owner: {owner}  Flags: {flags}"[:inner_w].ljust(inner_w),
                curses.color_pair(COLOR_PANEL),
            )

        # Instructions
        win.addstr(
            y + inner_h - 1,
            x,
            "j/k Move   r Refresh   Esc Back".ljust(inner_w),
            curses.color_pair(COLOR_DIM) | curses.A_DIM,
        )

    except curses.error:
        pass


def _format_pin_cell_tui(pin_def, pins_data: dict, selected_gpio: int | None) -> str:
    """Format a pin cell for TUI display."""
    if pin_def.gpio is None:
        # Power/ground/control pin
        kind_marker = {"power": "+", "gnd": "-", "control": "~"}.get(pin_def.kind, " ")
        return f"{pin_def.label:4s} {kind_marker}"

    gpio = pin_def.gpio
    state = pins_data.get(gpio)

    if state is None:
        return f"{pin_def.label:4s} G{gpio:02d} ?"

    level = str(state.level) if state.level is not None else "-"
    mode_abbr = state.mode[0].upper() if state.mode else "?"
    owner = state.owner[:4] if state.owner else "-"

    warn = ""
    if "strapping" in state.flags:
        warn = "!"
    elif "flash" in state.flags:
        warn = "X"

    return f"{pin_def.label:4s} G{gpio:02d} L{level} M{mode_abbr} {owner:4s}{warn}"


def draw_screen(win: curses.window, state: AppState) -> None:
    """Draw the current screen."""
    win.erase()
    height, width = win.getmaxyx()

    # If the terminal is tiny, fall back to the simplest layout.
    if height < (BANNER_HEIGHT + 7) or width < 50:
        banner_end = draw_banner(win)
        log_y = banner_end + 1
        log_height = height - banner_end - 3  # Leave room for status and hints
        state.log.draw(win, log_y, 0, max(0, log_height), max(0, width - 1))
    else:
        now = time.strftime("%H:%M:%S")
        port_label = state.port or "(auto)"

        link = "ON" if state.connected else "OFF"
        node = state.node_id or "—"
        right = f"{now}  {port_label}  LINK:{link}"
        draw_chrome_line(win, 0, " CODIGNITY :: CONTROL DECK ", right, attr=curses.A_BOLD)

        banner_lines = draw_banner(win, y=1)
        info_y = 1 + banner_lines

        node = state.node_id or "—"
        role = state.role or "—"
        ver = state.ver or "—"
        mode = state.mode or "unknown"

        left = f" NODE:{node}  ROLE:{role}  VER:{ver} "
        right = f" MODE:{mode.upper()} "
        draw_chrome_line(win, info_y, left, right)

        body_y = info_y + 1
        body_h = max(0, height - body_y - 2)  # Leave room for status + hints

        if body_h > 2:
            gap = 1
            sidebar_min = 26
            sidebar_w = min(34, max(sidebar_min, width // 4))

            if width < sidebar_min + gap + 30:
                # Not enough width for a sidebar.
                log_y, log_x, log_h, log_w = draw_frame(
                    win, body_y, 0, body_h, width, "LOG / TELEMETRY", fill=True
                )
                state.log.draw(win, log_y, log_x, log_h, log_w)
            else:
                sys_y, sys_x, sys_h, sys_w = draw_frame(
                    win, body_y, 0, body_h, sidebar_w, "SYSTEM", fill=True
                )
                log_y, log_x, log_h, log_w = draw_frame(
                    win,
                    body_y,
                    sidebar_w + gap,
                    body_h,
                    width - (sidebar_w + gap),
                    "LOG / TELEMETRY",
                    fill=True,
                )

                # SYSTEM panel contents
                connected = state.connected
                dot = "●" if connected else "○"
                link_label = "CONNECTED" if connected else "DISCONNECTED"

                lines: list[tuple[str, int, int]] = [
                    (f"LINK: {dot} {link_label}", COLOR_SUCCESS if connected else COLOR_ERROR, curses.A_BOLD),
                    (f"PORT: {port_label}", COLOR_DIM, curses.A_DIM),
                    (f"MODE: {mode.upper()}", COLOR_PANEL, 0),
                    (f"NODE: {node}", COLOR_PANEL, 0),
                    (f"ROLE: {role}", COLOR_PANEL, 0),
                    (f"VER:  {ver}", COLOR_PANEL, 0),
                ]
                if state.mcu:
                    lines.append((f"MCU:  {state.mcu}", COLOR_PANEL, 0))
                if state.units:
                    lines.append((f"UNITS:{state.units}", COLOR_PANEL, 0))
                if state.pins:
                    lines.append((f"PINS: {state.pins}", COLOR_PANEL, 0))
                if state.children is not None:
                    lines.append((f"KIDS: {state.children}", COLOR_PANEL, 0))
                if state.fifo_size is not None:
                    lines.append((f"FIFO: {state.fifo_size}", COLOR_PANEL, 0))
                if state.last_error:
                    lines.append(("", COLOR_PANEL, 0))
                    lines.append(("LAST ERROR", COLOR_ERROR, curses.A_BOLD))
                    lines.append((state.last_error, COLOR_ERROR, 0))

                lines.append(("", COLOR_PANEL, 0))
                lines.append(("ACTIONS", COLOR_TITLE, curses.A_BOLD))
                lines.extend(
                    [
                        (" p   Probe / connect", COLOR_PANEL, 0),
                        (" g   Pins inspector", COLOR_PANEL, 0),
                        (" m   Meta refresh", COLOR_PANEL, 0),
                        (" h   History", COLOR_PANEL, 0),
                        (" s   Source", COLOR_PANEL, 0),
                        (" v   Validate", COLOR_PANEL, 0),
                        (" l   Load firmware", COLOR_PANEL, 0),
                        (" c   Snapshot", COLOR_PANEL, 0),
                        (" r   Restore", COLOR_PANEL, 0),
                        (" Enter  Send command", COLOR_PANEL, 0),
                        (" Tab    Menu", COLOR_PANEL, 0),
                        (" ?      Help", COLOR_PANEL, 0),
                        (" ↑/↓, PgUp/PgDn  Scroll", COLOR_PANEL, 0),
                        (" q      Quit", COLOR_PANEL, 0),
                    ]
                )

                try:
                    row = sys_y
                    for text, color, extra in lines:
                        if row >= sys_y + sys_h:
                            break
                        clipped = text[:sys_w].ljust(sys_w)
                        win.addstr(row, sys_x, clipped, curses.color_pair(color) | extra)
                        row += 1
                except curses.error:
                    pass

                # LOG panel contents
                state.log.draw(win, log_y, log_x, log_h, log_w)

    # Status bar
    draw_status_bar(
        win,
        node_id=state.node_id,
        role=state.role,
        mode=state.mode,
        fifo_size=state.fifo_size,
    )

    # Key hints
    hints = KEY_HINTS.get(state.screen.name.lower(), KEY_HINTS["home"])
    draw_key_hints(win, hints)

    # Overlay screens
    if state.screen == Screen.MENU and state.menu:
        state.menu.draw(win)
    elif state.screen == Screen.CONFIRM:
        draw_confirm_dialog(win, state.confirm_message)
    elif state.screen == Screen.INPUT:
        draw_input_dialog(
            win,
            state.input_prompt,
            state.input_value,
            state.input_cursor,
        )
    elif state.screen == Screen.MESSAGE:
        draw_message(win, state.message, state.message_is_error)
    elif state.screen == Screen.HELP:
        draw_help(win, state)
    elif state.screen == Screen.LOAD_WIZARD:
        draw_load_wizard(win, state)
    elif state.screen == Screen.SNAPSHOT_WIZARD:
        draw_snapshot_wizard(win, state)
    elif state.screen == Screen.RESTORE_WIZARD:
        draw_restore_wizard(win, state)
    elif state.screen == Screen.PINS:
        draw_pins(win, state)

    win.refresh()


def run_tui(port: str | None = None, theme: str | None = None) -> int:
    """Run the TUI application.

    Args:
        port: Serial port path (auto-detects if None).

    Returns:
        Exit code (0 for success).
    """

    def main(stdscr: curses.window) -> int:
        # Setup
        try:
            curses.curs_set(0)  # Hide cursor
        except curses.error:
            pass
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(100)  # 100ms timeout for getch

        has_colors = init_colors(theme)
        if has_colors:
            try:
                stdscr.bkgd(" ", curses.color_pair(COLOR_PANEL))
            except curses.error:
                pass

        state = AppState()
        if port:
            state.port = port

        # Start IO worker thread
        io_thread = threading.Thread(target=io_worker, args=(state,), daemon=True)
        io_thread.start()

        # Initial probe
        state.log.append("Codignity TUI started", COLOR_SUCCESS)
        state.log.append("Press Tab for menu, ? for help")

        if port:
            state.log.append(f"Probing {port}...")
            state.io_queue.put(("probe", port))

        # Main loop
        while state.running:
            # Process IO results
            process_results(state)

            # Draw
            draw_screen(stdscr, state)

            # Handle input
            try:
                key = stdscr.getch()
                if key != -1:
                    handle_input(state, key)
            except curses.error:
                pass

        return 0

    return curses.wrapper(main)
