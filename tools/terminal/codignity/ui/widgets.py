"""Minimal curses widgets for Codignity TUI."""

from __future__ import annotations

import curses
from dataclasses import dataclass, field
from typing import Callable

from .theme import (
    COLOR_BANNER,
    COLOR_STATUS,
    COLOR_ERROR,
    COLOR_SUCCESS,
    COLOR_KEY_HINT,
    COLOR_MENU_SELECTED,
    BANNER_LINES,
)


def draw_banner(win: curses.window, y: int = 0, x: int = 0) -> int:
    """Draw the ASCII banner. Returns number of lines drawn."""
    height, width = win.getmaxyx()

    for i, line in enumerate(BANNER_LINES):
        if y + i >= height - 1:
            break
        # Center the banner
        start_x = max(0, (width - len(line)) // 2)
        try:
            win.addstr(y + i, start_x, line[:width - start_x], curses.color_pair(COLOR_BANNER))
        except curses.error:
            pass

    return len(BANNER_LINES)


def draw_status_bar(
    win: curses.window,
    node_id: str | None = None,
    role: str | None = None,
    mode: str | None = None,
    fifo_size: int | None = None,
) -> None:
    """Draw the status bar at the bottom of the window."""
    height, width = win.getmaxyx()
    y = height - 2

    # Build status string
    parts = []
    if node_id:
        parts.append(f"Node: {node_id}")
    if role:
        parts.append(f"Role: {role}")
    if mode:
        parts.append(f"Mode: {mode}")
    if fifo_size is not None:
        parts.append(f"FIFO: {fifo_size}")

    status = "  |  ".join(parts) if parts else "Not connected"
    status = f" {status} "

    # Pad to full width
    status = status.ljust(width - 1)[:width - 1]

    try:
        win.addstr(y, 0, status, curses.color_pair(COLOR_STATUS))
    except curses.error:
        pass


def draw_key_hints(win: curses.window, hints: str) -> None:
    """Draw key hints at the very bottom."""
    height, width = win.getmaxyx()
    y = height - 1

    try:
        win.addstr(y, 0, hints[:width - 1], curses.color_pair(COLOR_KEY_HINT))
    except curses.error:
        pass


@dataclass
class LogPane:
    """Scrollable log pane for protocol I/O."""

    lines: list[tuple[str, int]] = field(default_factory=list)  # (text, color_pair)
    max_lines: int = 500
    scroll_offset: int = 0

    def append(self, text: str, color_pair: int = 0) -> None:
        """Append a line to the log."""
        for line in text.split("\n"):
            self.lines.append((line, color_pair))

        # Trim if too many lines
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines :]
            self.scroll_offset = max(0, self.scroll_offset - (len(self.lines) - self.max_lines))

        # Auto-scroll to bottom
        self.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        """Scroll to show the most recent lines."""
        self.scroll_offset = 0

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll up by N lines."""
        max_offset = max(0, len(self.lines) - 1)
        self.scroll_offset = min(max_offset, self.scroll_offset + lines)

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll down by N lines."""
        self.scroll_offset = max(0, self.scroll_offset - lines)

    def draw(self, win: curses.window, y: int, x: int, height: int, width: int) -> None:
        """Draw the log pane in the given area."""
        # Calculate which lines to show
        visible_lines = height
        total_lines = len(self.lines)

        if total_lines == 0:
            return

        # Start from bottom, offset by scroll
        end_idx = total_lines - self.scroll_offset
        start_idx = max(0, end_idx - visible_lines)

        for i, (line, color) in enumerate(self.lines[start_idx:end_idx]):
            row = y + i
            if row >= y + height:
                break

            # Truncate line to fit
            display_line = line[:width]
            try:
                win.addstr(row, x, display_line, curses.color_pair(color))
            except curses.error:
                pass


@dataclass
class MenuItem:
    """A menu item."""

    label: str
    key: str
    action: Callable[[], None] | None = None
    enabled: bool = True


class Menu:
    """A simple menu modal."""

    def __init__(self, title: str, items: list[MenuItem]):
        self.title = title
        self.items = items
        self.selected = 0

    def move_up(self) -> None:
        """Move selection up."""
        self.selected = (self.selected - 1) % len(self.items)
        # Skip disabled items
        attempts = 0
        while not self.items[self.selected].enabled and attempts < len(self.items):
            self.selected = (self.selected - 1) % len(self.items)
            attempts += 1

    def move_down(self) -> None:
        """Move selection down."""
        self.selected = (self.selected + 1) % len(self.items)
        # Skip disabled items
        attempts = 0
        while not self.items[self.selected].enabled and attempts < len(self.items):
            self.selected = (self.selected + 1) % len(self.items)
            attempts += 1

    def get_selected(self) -> MenuItem:
        """Get the currently selected item."""
        return self.items[self.selected]

    def draw(self, win: curses.window) -> None:
        """Draw the menu centered on the screen."""
        height, width = win.getmaxyx()

        # Calculate menu dimensions
        menu_width = max(len(self.title) + 4, max(len(f"  {i.key}: {i.label}  ") for i in self.items))
        menu_height = len(self.items) + 4  # title + border + items + border

        # Center the menu
        start_y = (height - menu_height) // 2
        start_x = (width - menu_width) // 2

        # Draw border
        try:
            for y in range(menu_height):
                for x in range(menu_width):
                    row = start_y + y
                    col = start_x + x
                    if 0 <= row < height and 0 <= col < width:
                        if y == 0 or y == menu_height - 1:
                            win.addch(row, col, curses.ACS_HLINE)
                        elif x == 0 or x == menu_width - 1:
                            win.addch(row, col, curses.ACS_VLINE)

            # Corners
            win.addch(start_y, start_x, curses.ACS_ULCORNER)
            win.addch(start_y, start_x + menu_width - 1, curses.ACS_URCORNER)
            win.addch(start_y + menu_height - 1, start_x, curses.ACS_LLCORNER)
            win.addch(start_y + menu_height - 1, start_x + menu_width - 1, curses.ACS_LRCORNER)

            # Title
            title_x = start_x + (menu_width - len(self.title)) // 2
            win.addstr(start_y + 1, title_x, self.title, curses.A_BOLD)

            # Items
            for i, item in enumerate(self.items):
                row = start_y + 3 + i
                label = f" {item.key}: {item.label} "
                label = label.ljust(menu_width - 4)

                attr = curses.color_pair(COLOR_MENU_SELECTED) if i == self.selected else 0
                if not item.enabled:
                    attr = curses.A_DIM

                win.addstr(row, start_x + 2, label[:menu_width - 4], attr)

        except curses.error:
            pass


def draw_confirm_dialog(
    win: curses.window,
    message: str,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> None:
    """Draw a confirmation dialog."""
    height, width = win.getmaxyx()

    # Calculate dialog dimensions
    dialog_width = max(len(message) + 4, len(yes_label) + len(no_label) + 10)
    dialog_height = 5

    start_y = (height - dialog_height) // 2
    start_x = (width - dialog_width) // 2

    try:
        # Draw border
        for y in range(dialog_height):
            for x in range(dialog_width):
                row = start_y + y
                col = start_x + x
                if 0 <= row < height and 0 <= col < width:
                    if y == 0 or y == dialog_height - 1:
                        win.addch(row, col, curses.ACS_HLINE)
                    elif x == 0 or x == dialog_width - 1:
                        win.addch(row, col, curses.ACS_VLINE)
                    else:
                        win.addch(row, col, " ")

        # Corners
        win.addch(start_y, start_x, curses.ACS_ULCORNER)
        win.addch(start_y, start_x + dialog_width - 1, curses.ACS_URCORNER)
        win.addch(start_y + dialog_height - 1, start_x, curses.ACS_LLCORNER)
        win.addch(start_y + dialog_height - 1, start_x + dialog_width - 1, curses.ACS_LRCORNER)

        # Message
        msg_x = start_x + (dialog_width - len(message)) // 2
        win.addstr(start_y + 2, msg_x, message)

        # Buttons hint
        buttons = f"[{yes_label}] / [{no_label}]"
        btn_x = start_x + (dialog_width - len(buttons)) // 2
        win.addstr(start_y + 3, btn_x, buttons, curses.color_pair(COLOR_KEY_HINT))

    except curses.error:
        pass


def draw_input_dialog(
    win: curses.window,
    prompt: str,
    value: str = "",
    cursor_pos: int = 0,
) -> None:
    """Draw an input dialog."""
    height, width = win.getmaxyx()

    dialog_width = max(len(prompt) + 4, 40)
    dialog_height = 5

    start_y = (height - dialog_height) // 2
    start_x = (width - dialog_width) // 2

    try:
        # Draw border
        for y in range(dialog_height):
            for x in range(dialog_width):
                row = start_y + y
                col = start_x + x
                if 0 <= row < height and 0 <= col < width:
                    if y == 0 or y == dialog_height - 1:
                        win.addch(row, col, curses.ACS_HLINE)
                    elif x == 0 or x == dialog_width - 1:
                        win.addch(row, col, curses.ACS_VLINE)
                    else:
                        win.addch(row, col, " ")

        # Corners
        win.addch(start_y, start_x, curses.ACS_ULCORNER)
        win.addch(start_y, start_x + dialog_width - 1, curses.ACS_URCORNER)
        win.addch(start_y + dialog_height - 1, start_x, curses.ACS_LLCORNER)
        win.addch(start_y + dialog_height - 1, start_x + dialog_width - 1, curses.ACS_LRCORNER)

        # Prompt
        win.addstr(start_y + 1, start_x + 2, prompt)

        # Input field
        input_y = start_y + 2
        input_x = start_x + 2
        input_width = dialog_width - 4

        # Draw input value
        display_value = value[:input_width]
        win.addstr(input_y, input_x, display_value, curses.A_UNDERLINE)

        # Fill remaining space with underline
        remaining = input_width - len(display_value)
        if remaining > 0:
            win.addstr(input_y, input_x + len(display_value), " " * remaining, curses.A_UNDERLINE)

        # Position cursor
        curses.curs_set(1)
        cursor_x = input_x + min(cursor_pos, input_width - 1)
        win.move(input_y, cursor_x)

    except curses.error:
        pass


def draw_message(win: curses.window, message: str, is_error: bool = False) -> None:
    """Draw a message at the center of the screen."""
    height, width = win.getmaxyx()

    y = height // 2
    x = (width - len(message)) // 2

    color = curses.color_pair(COLOR_ERROR if is_error else COLOR_SUCCESS)

    try:
        win.addstr(y, max(0, x), message[:width], color | curses.A_BOLD)
    except curses.error:
        pass
