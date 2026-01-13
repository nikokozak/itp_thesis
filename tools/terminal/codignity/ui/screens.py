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

from .theme import init_colors, KEY_HINTS, BANNER_HEIGHT
from .widgets import (
    draw_banner,
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
    COLOR_ERROR,
    COLOR_SUCCESS,
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
    LOAD_WIZARD = auto()
    SNAPSHOT_WIZARD = auto()
    RESTORE_WIZARD = auto()


class Action(Enum):
    """Actions that can be triggered."""

    QUIT = auto()
    PROBE = auto()
    META = auto()
    HISTORY = auto()
    SOURCE = auto()
    EXPLAIN = auto()
    IDENTITY = auto()
    LOAD = auto()
    SNAPSHOT = auto()
    RESTORE = auto()
    CLEAR = auto()
    SEND = auto()
    VALIDATE = auto()


@dataclass
class AppState:
    """Application state."""

    screen: Screen = Screen.HOME
    port: str = ""
    session: "SerialSession | None" = None
    mode: str = "unknown"
    node_id: str | None = None
    role: str | None = None
    ver: str | None = None
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


def create_main_menu(state: AppState) -> Menu:
    """Create the main menu."""
    connected = state.session is not None

    items = [
        MenuItem("Probe Device", "p", enabled=True),
        MenuItem("Identity (?)", "i", enabled=connected),
        MenuItem("Explain", "e", enabled=connected),
        MenuItem("Meta Dump", "m", enabled=connected),
        MenuItem("History", "h", enabled=connected),
        MenuItem("Source", "s", enabled=connected),
        MenuItem("Validate", "v", enabled=connected),
        MenuItem("Load Firmware", "l", enabled=True),
        MenuItem("Create Snapshot", "c", enabled=connected),
        MenuItem("Restore Snapshot", "r", enabled=True),
        MenuItem("Clear Log", "x", enabled=True),
        MenuItem("Quit", "q", enabled=True),
    ]

    return Menu("Codignity", items)


def handle_menu_select(state: AppState, key: str) -> Action | None:
    """Map menu selection key to action."""
    key_map = {
        "p": Action.PROBE,
        "i": Action.IDENTITY,
        "e": Action.EXPLAIN,
        "m": Action.META,
        "h": Action.HISTORY,
        "s": Action.SOURCE,
        "v": Action.VALIDATE,
        "l": Action.LOAD,
        "c": Action.SNAPSHOT,
        "r": Action.RESTORE,
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
        with SerialSession.open(port=state.port, settle_s=2.0, quiet=False) as session:
            # Send interrupt to stop autoexec
            session.send_line("")
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
        with SerialSession.open(port=state.port, settle_s=5.0) as session:
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

        with SerialSession.open(port=state.port, settle_s=2.0, quiet=False) as session:
            # Interrupt autoexec
            session.send_line("")
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
        with SerialSession.open(port=state.port, settle_s=5.0) as session:
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
    from ..protocol import probe, ensure_protocol, parse_meta_dump, is_error

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
        target_port = port or state.port

        # Reuse existing session if port matches
        if persistent_session is not None and session_port == target_port:
            return persistent_session

        # Port changed or no session - close old and open new
        close_persistent()
        settle_s = 5.0 if needs_settle else 0.0
        persistent_session = SerialSession.open(port=target_port, settle_s=settle_s)
        session_port = target_port
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
                    if state.session is None:
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

                elif action == "explain":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("explain", timeout_s=3.0)
                    state.result_queue.put(("explain_ok", response))

                elif action == "identity":
                    session = get_session()
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("?", timeout_s=3.0)
                    state.result_queue.put(("identity_ok", response))

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
            state.fifo_size = probe_result.fifo
            state.session = True  # Marker that we've connected

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

        elif result_type in ("meta_ok", "history_ok", "source_ok", "explain_ok", "identity_ok"):
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
            state.log.append(f"Restored successfully: {node_id} ({role})", COLOR_SUCCESS)
            state.screen = Screen.HOME

        elif result_type == "restore_error":
            error_msg = result[1]
            state.restore_running = False
            state.restore_status = f"Error: {error_msg}"
            state.log.append(f"Restore failed: {error_msg}", COLOR_ERROR)


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
    elif state.screen == Screen.LOAD_WIZARD:
        handle_load_wizard_input(state, key)
    elif state.screen == Screen.SNAPSHOT_WIZARD:
        handle_snapshot_wizard_input(state, key)
    elif state.screen == Screen.RESTORE_WIZARD:
        handle_restore_wizard_input(state, key)


def handle_home_input(state: AppState, key: int) -> None:
    """Handle input on the home screen."""
    if key == ord("q"):
        state.running = False
    elif key == ord("\t") or key == curses.KEY_F1:
        state.menu = create_main_menu(state)
        state.screen = Screen.MENU
    elif key == ord("?"):
        state.log.append("Help: Tab=Menu, q=Quit, PgUp/PgDn=Scroll")
    elif key == curses.KEY_PPAGE:
        state.log.scroll_up(5)
    elif key == curses.KEY_NPAGE:
        state.log.scroll_down(5)
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


def handle_text_input(state: AppState, key: int) -> None:
    """Handle text input dialog."""
    if key == 27:  # Escape
        state.screen = Screen.HOME
        curses.curs_set(0)
    elif key == ord("\n") or key == ord("\r"):
        if state.input_action == Action.SEND and state.input_value:
            state.log.append(f"> {state.input_value}")
            state.io_queue.put(("send", state.input_value))
        state.screen = Screen.HOME
        curses.curs_set(0)
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

    elif action == Action.EXPLAIN:
        state.log.append("Fetching explanation...")
        state.io_queue.put(("explain",))

    elif action == Action.IDENTITY:
        state.log.append("Fetching identity...")
        state.io_queue.put(("identity",))

    elif action == Action.VALIDATE:
        state.log.append("Running validation...")
        state.io_queue.put(("validate",))

    elif action == Action.CLEAR:
        state.log.lines.clear()
        state.log.scroll_offset = 0

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


def execute_confirmed_action(state: AppState, action: Action) -> None:
    """Execute an action after confirmation."""
    # TODO(thesis): wire confirmation modal to destructive operations (e.g., restart/rollback).
    pass


def draw_load_wizard(win: curses.window, state: AppState) -> None:
    """Draw the load firmware wizard."""
    y, x, inner_h, inner_w = draw_wizard_frame(win, "Load Codignity", 12, 50)

    try:
        # Status message
        win.addstr(y + 1, x, state.load_status[:inner_w])

        # Progress bar (if loading)
        if state.load_running or state.load_progress > 0:
            lines_text = f"{state.load_current_line}/{state.load_total_lines} lines"
            draw_progress_bar(win, y + 3, x, inner_w, state.load_progress, lines_text)

        # Persist checkbox (only if not running)
        if not state.load_running:
            state.load_persist.draw(win, y + 5, x)

            # Instructions
            win.addstr(y + 7, x, "Press Enter to start loading", curses.A_DIM)
            win.addstr(y + 8, x, "Press Escape to cancel", curses.A_DIM)
        else:
            win.addstr(y + 7, x, "Loading in progress...", curses.A_DIM)

    except curses.error:
        pass


def draw_snapshot_wizard(win: curses.window, state: AppState) -> None:
    """Draw the snapshot creation wizard."""
    y, x, inner_h, inner_w = draw_wizard_frame(win, "Create Snapshot", 14, 55)

    try:
        # Filename
        win.addstr(y + 1, x, "Filename:")
        win.addstr(y + 2, x, state.snapshot_filename[:inner_w], curses.A_UNDERLINE)

        # Node info
        if state.node_id:
            win.addstr(y + 4, x, f"Node: {state.node_id} ({state.role or 'unknown'})")

        # Safe-save checkbox
        state.snapshot_safe_save.draw(win, y + 6, x)

        # Status
        if state.snapshot_status:
            win.addstr(y + 8, x, state.snapshot_status[:inner_w])

        # Instructions
        win.addstr(y + 10, x, "Press Enter to create snapshot", curses.A_DIM)
        win.addstr(y + 11, x, "Press Escape to cancel", curses.A_DIM)

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
            win.addstr(y + 1, x, path_display, curses.A_DIM)

            # Preview info
            for i, line in enumerate(state.restore_preview[:10]):
                if y + 3 + i < y + inner_h - 4:
                    win.addstr(y + 3 + i, x, line[:inner_w])

            # Progress bar (if restoring)
            if state.restore_running:
                draw_progress_bar(win, y + inner_h - 4, x, inner_w, state.restore_progress)
                win.addstr(y + inner_h - 3, x, state.restore_status[:inner_w])
            else:
                # Instructions
                win.addstr(y + inner_h - 3, x, "Press Enter to restore, Escape to go back", curses.A_DIM)

        except curses.error:
            pass
    else:
        # File browser mode
        y, x, inner_h, inner_w = draw_wizard_frame(win, "Select Snapshot", 16, 55)

        try:
            win.addstr(y + 1, x, "Select a .cdsnap file:", curses.A_DIM)

            if state.restore_file_browser:
                state.restore_file_browser.draw(win, y + 3, x, inner_h - 5, inner_w)

            win.addstr(y + inner_h - 2, x, "Enter: Select, Escape: Cancel", curses.A_DIM)

        except curses.error:
            pass


def draw_screen(win: curses.window, state: AppState) -> None:
    """Draw the current screen."""
    win.erase()
    height, width = win.getmaxyx()

    # Always draw banner and status bar
    banner_end = draw_banner(win)

    # Log pane area
    log_y = banner_end + 1
    log_height = height - banner_end - 3  # Leave room for status and hints

    state.log.draw(win, log_y, 0, log_height, width)

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
    elif state.screen == Screen.LOAD_WIZARD:
        draw_load_wizard(win, state)
    elif state.screen == Screen.SNAPSHOT_WIZARD:
        draw_snapshot_wizard(win, state)
    elif state.screen == Screen.RESTORE_WIZARD:
        draw_restore_wizard(win, state)

    win.refresh()


def run_tui(port: str | None = None) -> int:
    """Run the TUI application.

    Args:
        port: Serial port path (auto-detects if None).

    Returns:
        Exit code (0 for success).
    """

    def main(stdscr: curses.window) -> int:
        # Setup
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(True)  # Non-blocking input
        stdscr.timeout(100)  # 100ms timeout for getch

        init_colors()

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
