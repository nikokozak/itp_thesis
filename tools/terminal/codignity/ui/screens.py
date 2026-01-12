"""Screen management and state machine for Codignity TUI."""

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


def io_worker(state: AppState) -> None:
    """Background worker for serial I/O."""
    from ..session import SerialSession, SerialError
    from ..protocol import probe, ensure_protocol, parse_meta_dump, is_error

    while state.running:
        try:
            task = state.io_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        action, *args = task

        try:
            if action == "probe":
                port = args[0] if args else state.port
                with SerialSession.open(port=port, settle_s=5.0) as session:
                    result = probe(session, timeout_s=3.0)
                    state.result_queue.put(("probe_ok", result, session.port))

            elif action == "send":
                cmd = args[0]
                if state.session is None:
                    state.result_queue.put(("error", "Not connected"))
                    continue

                with SerialSession.open(port=state.port, settle_s=5.0) as session:
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
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("meta", timeout_s=3.0)
                    state.result_queue.put(("meta_ok", response))

            elif action == "history":
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("history", timeout_s=3.0)
                    state.result_queue.put(("history_ok", response))

            elif action == "source":
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("source", timeout_s=3.0)
                    state.result_queue.put(("source_ok", response))

            elif action == "validate":
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
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
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("explain", timeout_s=3.0)
                    state.result_queue.put(("explain_ok", response))

            elif action == "identity":
                with SerialSession.open(port=state.port, settle_s=5.0) as session:
                    if not ensure_protocol(session, timeout_s=3.0):
                        state.result_queue.put(("error", "Could not enter protocol mode"))
                        continue

                    response = session.send_protocol("?", timeout_s=3.0)
                    state.result_queue.put(("identity_ok", response))

        except SerialError as e:
            state.result_queue.put(("error", str(e)))
        except Exception as e:
            state.result_queue.put(("error", f"Unexpected error: {e}"))


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
        state.message = "Load not yet implemented in TUI"
        state.message_is_error = True
        state.screen = Screen.MESSAGE
        # TODO(thesis): implement LOAD wizard (reuse CLI `cmd_load` algorithm).

    elif action == Action.SNAPSHOT:
        state.message = "Snapshot not yet implemented in TUI"
        state.message_is_error = True
        state.screen = Screen.MESSAGE
        # TODO(thesis): implement SNAPSHOT wizard (path picker + summary + optional safe-save).

    elif action == Action.RESTORE:
        state.message = "Restore not yet implemented in TUI"
        state.message_is_error = True
        state.screen = Screen.MESSAGE
        # TODO(thesis): implement RESTORE wizard (diff preview + confirm + restore algorithm).


def execute_confirmed_action(state: AppState, action: Action) -> None:
    """Execute an action after confirmation."""
    # TODO(thesis): wire confirmation modal to destructive operations (e.g., restart/rollback).
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
