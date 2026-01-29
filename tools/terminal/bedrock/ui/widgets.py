"""Minimal curses widgets for Bedrock TUI.

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
    COLOR_PROMPT,
    COLOR_KEY_HINT,
    COLOR_MENU_SELECTED,
    COLOR_CHROME,
    COLOR_DIM,
    COLOR_TITLE,
    COLOR_BORDER,
    COLOR_PANEL,
    BANNER_LINES,
    TAGLINE_LINES,
)


def _sanitize_log_line(text: str) -> str:
    """Make log lines safe for curses rendering (strip control chars)."""
    if not text:
        return ""

    text = text.replace("\r", "")
    text = text.expandtabs(4)

    # Replace remaining control characters with a visible placeholder.
    return "".join(ch if (" " <= ch <= "~" or ch >= "\u00a0") else "�" for ch in text)


def draw_chrome_line(
    win: curses.window,
    y: int,
    left: str,
    right: str = "",
    *,
    color_pair: int = COLOR_CHROME,
    attr: int = 0,
) -> None:
    """Draw a full-width "chrome" line with left/right text."""
    height, width = win.getmaxyx()
    usable_width = max(0, width - 1)
    if y < 0 or y >= height or usable_width <= 0:
        return

    style = curses.color_pair(color_pair) | attr
    try:
        win.addstr(y, 0, " " * usable_width, style)
        if left:
            win.addstr(y, 0, left[:usable_width], style)
        if right:
            right = right[:usable_width]
            start_x = max(0, usable_width - len(right))
            if start_x > 0:
                win.addstr(y, start_x, right, style)
    except curses.error:
        pass


def draw_frame(
    win: curses.window,
    y: int,
    x: int,
    height: int,
    width: int,
    title: str = "",
    *,
    border_pair: int = COLOR_BORDER,
    title_pair: int = COLOR_TITLE,
    fill: bool = False,
    fill_pair: int = COLOR_PANEL,
    shadow: bool = False,
) -> tuple[int, int, int, int]:
    """Draw a bordered frame and return inner rect (y, x, h, w)."""
    screen_h, screen_w = win.getmaxyx()
    usable_w = max(0, screen_w - 1)
    height = max(0, min(height, screen_h - y))
    width = max(0, min(width, usable_w - x))
    if height < 2 or width < 2:
        return y, x, 0, 0

    border_attr = curses.color_pair(border_pair)
    title_attr = curses.color_pair(title_pair) | curses.A_BOLD
    fill_attr = curses.color_pair(fill_pair)

    try:
        if shadow:
            shadow_attr = curses.color_pair(COLOR_DIM) | curses.A_DIM
            shadow_y = y + height
            shadow_x = x + width

            if shadow_y < screen_h:
                shadow_w = min(width, max(0, usable_w - (x + 1)))
                if shadow_w > 0:
                    win.hline(shadow_y, x + 1, " ", shadow_w, shadow_attr)

            if shadow_x < usable_w:
                shadow_h = min(height, max(0, screen_h - (y + 1)))
                if shadow_h > 0:
                    win.vline(y + 1, shadow_x, " ", shadow_h, shadow_attr)

        # Border lines
        win.hline(y, x, curses.ACS_HLINE, width, border_attr)
        win.hline(y + height - 1, x, curses.ACS_HLINE, width, border_attr)
        win.vline(y, x, curses.ACS_VLINE, height, border_attr)
        win.vline(y, x + width - 1, curses.ACS_VLINE, height, border_attr)

        # Corners
        win.addch(y, x, curses.ACS_ULCORNER, border_attr)
        win.addch(y, x + width - 1, curses.ACS_URCORNER, border_attr)
        win.addch(y + height - 1, x, curses.ACS_LLCORNER, border_attr)
        win.addch(y + height - 1, x + width - 1, curses.ACS_LRCORNER, border_attr)

        if fill and height > 2 and width > 2:
            blank = " " * (width - 2)
            for row in range(y + 1, y + height - 1):
                win.addstr(row, x + 1, blank, fill_attr)

        if title:
            label = f" {title} "
            label = label[: max(0, width - 2)]
            title_x = x + 1 + max(0, (width - 2 - len(label)) // 2)
            win.addstr(y, title_x, label, title_attr)

    except curses.error:
        pass

    return y + 1, x + 1, height - 2, width - 2


def draw_banner(win: curses.window, y: int = 0, x: int = 0) -> int:
    """Draw the ASCII banner. Returns number of lines drawn."""
    height, width = win.getmaxyx()

    usable_width = max(0, width - 1)
    drawn = 0

    def _draw_line(line: str, attr: int) -> None:
        nonlocal drawn
        row = y + drawn
        if row >= height - 1:
            return

        start_x = max(0, (width - len(line)) // 2)
        try:
            # Lay down a header "slab" so the banner sits on chrome.
            if usable_width > 0:
                win.addstr(row, 0, " " * usable_width, curses.color_pair(COLOR_CHROME))
            max_len = max(0, usable_width - start_x)
            win.addstr(row, start_x, line[:max_len], attr)
            drawn += 1
        except curses.error:
            pass

    for line in BANNER_LINES:
        _draw_line(line, curses.color_pair(COLOR_BANNER) | curses.A_BOLD)
    for line in TAGLINE_LINES:
        _draw_line(line, curses.color_pair(COLOR_CHROME) | curses.A_DIM)

    return drawn


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
        usable_width = max(0, width - 1)
        win.addstr(y, 0, " " * usable_width, curses.color_pair(COLOR_KEY_HINT))
        win.addstr(y, 0, hints[:usable_width], curses.color_pair(COLOR_KEY_HINT))
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
        if text == "":
            return

        was_scrolled = self.scroll_offset > 0
        raw_lines = text.split("\n")
        new_lines = [_sanitize_log_line(line) for line in raw_lines]
        for line in new_lines:
            self.lines.append((line, color_pair))

        # Trim if too many lines
        if len(self.lines) > self.max_lines:
            removed = len(self.lines) - self.max_lines
            self.lines = self.lines[removed:]

            # Clamp scroll after retention kicks in.
            max_offset = max(0, len(self.lines) - 1)
            self.scroll_offset = min(self.scroll_offset, max_offset)

        if was_scrolled:
            # Keep the currently-visible content stable when new log lines arrive.
            self.scroll_offset = min(
                self.scroll_offset + len(new_lines),
                max(0, len(self.lines) - 1),
            )
        else:
            # Auto-scroll to bottom if the user hasn't scrolled up.
            self.scroll_to_bottom()

    def scroll_to_bottom(self) -> None:
        """Scroll to show the most recent lines."""
        self.scroll_offset = 0

    def scroll_to_top(self) -> None:
        """Scroll to show the oldest lines (clamped on draw)."""
        self.scroll_offset = len(self.lines)

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll up by N lines."""
        self.scroll_offset = max(0, self.scroll_offset + lines)

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
        if visible_lines <= 0 or width <= 0:
            return

        max_offset = max(0, total_lines - visible_lines)
        self.scroll_offset = min(max(0, self.scroll_offset), max_offset)

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
                if color:
                    attr = curses.color_pair(color)
                else:
                    # Auto-highlight common protocol shapes.
                    if display_line.startswith("#"):
                        attr = curses.color_pair(COLOR_ERROR)
                    elif display_line.startswith("> "):
                        attr = curses.color_pair(COLOR_PROMPT)
                    elif display_line.startswith("! "):
                        attr = curses.color_pair(COLOR_DIM)
                    else:
                        attr = curses.color_pair(COLOR_PANEL)

                win.addstr(row, x, display_line.ljust(width), attr)
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

        max_w = max(0, width - 4)
        max_h = max(0, height - 4)
        if max_w < 24 or max_h < 10:
            return

        # Calculate menu dimensions (with padding and room for a hint line).
        item_width = max(len(f"{i.key.upper():<2} {i.label}") for i in self.items)
        menu_width = max(len(self.title) + 8, item_width + 8, 36)
        menu_height = len(self.items) + 6

        menu_width = min(menu_width, max_w)
        menu_height = min(menu_height, max_h)

        # Center the menu
        start_y = max(0, (height - menu_height) // 2)
        start_x = max(0, (width - menu_width) // 2)

        inner_y, inner_x, inner_h, inner_w = draw_frame(
            win,
            start_y,
            start_x,
            menu_height,
            menu_width,
            self.title,
            border_pair=COLOR_BORDER,
            title_pair=COLOR_TITLE,
            fill=True,
            fill_pair=COLOR_PANEL,
            shadow=True,
        )
        if inner_h <= 0 or inner_w <= 0:
            return

        content_x = inner_x + 1
        content_w = max(0, inner_w - 2)
        content_y = inner_y + 1

        try:
            for i, item in enumerate(self.items):
                row = content_y + i
                if row >= inner_y + inner_h - 1:
                    break

                marker = ">" if i == self.selected else " "
                key = item.key.upper()
                text = f"{marker} {key:<2} {item.label}"
                text = text[:content_w].ljust(content_w)

                if not item.enabled:
                    attr = curses.color_pair(COLOR_DIM) | curses.A_DIM
                elif i == self.selected:
                    attr = curses.color_pair(COLOR_MENU_SELECTED) | curses.A_BOLD
                else:
                    attr = curses.color_pair(COLOR_PANEL)

                win.addstr(row, content_x, text, attr)

            hint = "Esc:Close  Enter:Select  j/k:Move"
            hint = hint[:content_w].ljust(content_w)
            win.addstr(inner_y + inner_h - 1, content_x, hint, curses.color_pair(COLOR_KEY_HINT))

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
    buttons = f"y:{yes_label}  n:{no_label}  Esc:Cancel"
    dialog_width = max(len(message) + 6, len(buttons) + 6, 36)
    dialog_height = 7
    dialog_width = min(dialog_width, max(0, width - 4))

    start_y = max(0, (height - dialog_height) // 2)
    start_x = max(0, (width - dialog_width) // 2)

    try:
        inner_y, inner_x, inner_h, inner_w = draw_frame(
            win,
            start_y,
            start_x,
            dialog_height,
            dialog_width,
            "Confirm",
            border_pair=COLOR_BORDER,
            title_pair=COLOR_TITLE,
            fill=True,
            fill_pair=COLOR_PANEL,
            shadow=True,
        )
        if inner_h <= 0 or inner_w <= 0:
            return

        msg = message[:inner_w]
        msg_x = inner_x + max(0, (inner_w - len(msg)) // 2)
        win.addstr(inner_y + 1, msg_x, msg, curses.color_pair(COLOR_PANEL))

        btn = buttons[:inner_w]
        btn_x = inner_x + max(0, (inner_w - len(btn)) // 2)
        win.addstr(inner_y + inner_h - 2, btn_x, btn, curses.color_pair(COLOR_KEY_HINT))

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

    dialog_width = max(len(prompt) + 6, 44)
    dialog_height = 7
    dialog_width = min(dialog_width, max(0, width - 4))

    start_y = max(0, (height - dialog_height) // 2)
    start_x = max(0, (width - dialog_width) // 2)

    try:
        inner_y, inner_x, inner_h, inner_w = draw_frame(
            win,
            start_y,
            start_x,
            dialog_height,
            dialog_width,
            "Command",
            border_pair=COLOR_BORDER,
            title_pair=COLOR_TITLE,
            fill=True,
            fill_pair=COLOR_PANEL,
            shadow=True,
        )
        if inner_h <= 0 or inner_w <= 0:
            return

        # Prompt
        win.addstr(
            inner_y + 1,
            inner_x + 1,
            prompt[: max(0, inner_w - 2)],
            curses.color_pair(COLOR_PANEL),
        )

        # Input field
        input_y = inner_y + 2
        input_x = inner_x + 1
        input_width = max(1, inner_w - 2)

        # Draw input value
        display_value = value[:input_width]
        win.addstr(
            input_y,
            input_x,
            display_value,
            curses.color_pair(COLOR_PROMPT) | curses.A_UNDERLINE,
        )

        # Fill remaining space with underline
        remaining = input_width - len(display_value)
        if remaining > 0:
            win.addstr(
                input_y,
                input_x + len(display_value),
                " " * remaining,
                curses.color_pair(COLOR_PROMPT) | curses.A_UNDERLINE,
            )

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
        win.addstr(y, x + len(bar), pct, curses.color_pair(COLOR_PANEL))
        if label:
            win.addstr(
                y,
                x + len(bar) + len(pct) + 1,
                label,
                curses.color_pair(COLOR_PANEL),
            )
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
        base = curses.color_pair(COLOR_SUCCESS if self.checked else COLOR_PANEL)
        attr = base | (curses.A_REVERSE if selected else 0)
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass


@dataclass
class FileBrowser:
    """Simple file browser for selecting snapshot files."""

    path: str = "."
    files: list[str] = field(default_factory=list)
    selected: int = 0
    filter_exts: tuple[str, ...] = (".brsnap", ".cdsnap")

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
                    if not self.filter_exts or item.suffix in self.filter_exts:
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
            win.addstr(
                y,
                x,
                path_display.ljust(width),
                curses.color_pair(COLOR_DIM) | curses.A_DIM,
            )
        except curses.error:
            pass

        # Calculate visible range
        visible_height = height - 1  # Account for path line
        if not self.files:
            try:
                win.addstr(
                    y + 1,
                    x,
                    "(no files)".ljust(width),
                    curses.color_pair(COLOR_DIM) | curses.A_DIM,
                )
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
            if idx == self.selected:
                attr = curses.color_pair(COLOR_MENU_SELECTED) | curses.A_BOLD
            else:
                attr = curses.color_pair(COLOR_PANEL)

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
    start_y = max(0, (screen_height - height) // 2)
    start_x = max(0, (screen_width - width) // 2)

    inner_y, inner_x, inner_h, inner_w = draw_frame(
        win,
        start_y,
        start_x,
        height,
        width,
        title,
        border_pair=COLOR_BORDER,
        title_pair=COLOR_TITLE,
        fill=True,
        fill_pair=COLOR_PANEL,
        shadow=True,
    )

    # Additional padding for wizard content.
    padded_x = inner_x + 1
    padded_w = max(0, inner_w - 2)
    return inner_y, padded_x, inner_h, padded_w
