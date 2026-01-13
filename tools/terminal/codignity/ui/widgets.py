"""Minimal curses widgets for Codignity TUI.

TODO(thesis): Widgets need polish:
- FileBrowser: Add search/filter, remember last path, handle long filenames
- ProgressBar: Add ETA calculation, smoother animation
- Checkbox: Add keyboard focus indicator, group support
- General: Consistent border styles, color theming
"""

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


def draw_progress_bar(
    win: curses.window,
    y: int,
    x: int,
    width: int,
    progress: float,
    label: str = "",
) -> None:
    """Draw a progress bar.

    Args:
        win: Curses window.
        y: Row position.
        x: Column position.
        width: Total width of the bar.
        progress: Progress value 0.0 to 1.0.
        label: Optional label to show after the bar.
    """
    bar_width = width - len(label) - 6  # Leave room for [, ], space, percentage
    if bar_width < 5:
        bar_width = 5

    filled = int(bar_width * min(1.0, max(0.0, progress)))
    empty = bar_width - filled

    bar = "[" + "#" * filled + "-" * empty + "]"
    pct = f" {int(progress * 100):3d}%"

    try:
        win.addstr(y, x, bar, curses.color_pair(COLOR_SUCCESS))
        win.addstr(y, x + len(bar), pct)
        if label:
            win.addstr(y, x + len(bar) + len(pct) + 1, label)
    except curses.error:
        pass


@dataclass
class Checkbox:
    """A toggleable checkbox."""

    label: str
    checked: bool = False

    def toggle(self) -> None:
        """Toggle the checkbox state."""
        self.checked = not self.checked

    def draw(self, win: curses.window, y: int, x: int, selected: bool = False) -> None:
        """Draw the checkbox."""
        check_char = "x" if self.checked else " "
        text = f"[{check_char}] {self.label}"
        attr = curses.A_REVERSE if selected else 0
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass


@dataclass
class FileBrowser:
    """Simple file browser for selecting .cdsnap files."""

    path: str = "."
    files: list[str] = field(default_factory=list)
    selected: int = 0
    filter_ext: str = ".cdsnap"

    def __post_init__(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        """Refresh the file list."""
        from pathlib import Path

        p = Path(self.path)
        if not p.exists():
            self.files = []
            return

        entries: list[str] = []
        # Add parent directory option
        if p.parent != p:
            entries.append("..")

        # Add directories
        try:
            for item in sorted(p.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    entries.append(item.name + "/")
                elif item.is_file():
                    if not self.filter_ext or item.suffix == self.filter_ext:
                        entries.append(item.name)
        except PermissionError:
            pass

        self.files = entries
        self.selected = min(self.selected, max(0, len(self.files) - 1))

    def move_up(self) -> None:
        """Move selection up."""
        if self.files:
            self.selected = (self.selected - 1) % len(self.files)

    def move_down(self) -> None:
        """Move selection down."""
        if self.files:
            self.selected = (self.selected + 1) % len(self.files)

    def select(self) -> str | None:
        """Select current item. Returns full path if file, or navigates if directory."""
        from pathlib import Path

        if not self.files:
            return None

        name = self.files[self.selected]

        if name == "..":
            self.path = str(Path(self.path).parent)
            self.refresh()
            return None
        elif name.endswith("/"):
            self.path = str(Path(self.path) / name[:-1])
            self.refresh()
            return None
        else:
            return str(Path(self.path) / name)

    def get_selected_name(self) -> str:
        """Get the name of the currently selected item."""
        if not self.files:
            return ""
        return self.files[self.selected]

    def draw(self, win: curses.window, y: int, x: int, height: int, width: int) -> None:
        """Draw the file browser."""
        # Show current path
        path_display = f"Path: {self.path}"
        if len(path_display) > width:
            path_display = "..." + path_display[-(width - 3):]
        try:
            win.addstr(y, x, path_display, curses.A_DIM)
        except curses.error:
            pass

        # Calculate visible range
        visible_height = height - 1  # Account for path line
        if not self.files:
            try:
                win.addstr(y + 1, x, "(no files)", curses.A_DIM)
            except curses.error:
                pass
            return

        # Scroll to keep selection visible
        start_idx = 0
        if self.selected >= visible_height:
            start_idx = self.selected - visible_height + 1

        for i, idx in enumerate(range(start_idx, min(start_idx + visible_height, len(self.files)))):
            name = self.files[idx]
            row = y + 1 + i
            attr = curses.A_REVERSE if idx == self.selected else 0

            # Indicate directories
            if name.endswith("/"):
                attr |= curses.A_BOLD

            display = name[:width]
            try:
                win.addstr(row, x, display.ljust(width), attr)
            except curses.error:
                pass


def draw_wizard_frame(
    win: curses.window,
    title: str,
    height: int,
    width: int,
) -> tuple[int, int, int, int]:
    """Draw a wizard dialog frame. Returns (start_y, start_x, inner_height, inner_width)."""
    screen_height, screen_width = win.getmaxyx()

    # Center the frame
    start_y = (screen_height - height) // 2
    start_x = (screen_width - width) // 2

    try:
        # Draw border
        for y in range(height):
            for x in range(width):
                row = start_y + y
                col = start_x + x
                if 0 <= row < screen_height and 0 <= col < screen_width:
                    if y == 0 or y == height - 1:
                        win.addch(row, col, curses.ACS_HLINE)
                    elif x == 0 or x == width - 1:
                        win.addch(row, col, curses.ACS_VLINE)
                    else:
                        win.addch(row, col, " ")

        # Corners
        win.addch(start_y, start_x, curses.ACS_ULCORNER)
        win.addch(start_y, start_x + width - 1, curses.ACS_URCORNER)
        win.addch(start_y + height - 1, start_x, curses.ACS_LLCORNER)
        win.addch(start_y + height - 1, start_x + width - 1, curses.ACS_LRCORNER)

        # Title
        title_x = start_x + (width - len(title) - 4) // 2
        win.addstr(start_y, title_x, f" {title} ", curses.A_BOLD)

    except curses.error:
        pass

    # Return inner dimensions
    return start_y + 1, start_x + 2, height - 2, width - 4
