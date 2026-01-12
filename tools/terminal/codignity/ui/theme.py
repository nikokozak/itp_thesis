"""Theme constants for Codignity TUI."""

import curses

# ASCII art banner
BANNER = r"""
  ____          _ _             _ _
 / ___|___   __| (_) __ _ _ __ (_) |_ _   _
| |   / _ \ / _` | |/ _` | '_ \| | __| | | |
| |__| (_) | (_| | | (_| | | | | | |_| |_| |
 \____\___/ \__,_|_|\__, |_| |_|_|\__|\__, |
                    |___/             |___/
"""

BANNER_LINES = [line for line in BANNER.strip().split("\n")]
BANNER_HEIGHT = len(BANNER_LINES)
BANNER_WIDTH = max(len(line) for line in BANNER_LINES)

# Color pair indices
COLOR_NORMAL = 0
COLOR_BANNER = 1
COLOR_STATUS = 2
COLOR_ERROR = 3
COLOR_SUCCESS = 4
COLOR_PROMPT = 5
COLOR_KEY_HINT = 6
COLOR_MENU_SELECTED = 7


def init_colors() -> bool:
    """Initialize color pairs. Returns True if colors available."""
    if not curses.has_colors():
        return False

    curses.start_color()
    curses.use_default_colors()

    # Define color pairs (fg, bg)
    curses.init_pair(COLOR_BANNER, curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_STATUS, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(COLOR_SUCCESS, curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_PROMPT, curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_KEY_HINT, curses.COLOR_BLUE, -1)
    curses.init_pair(COLOR_MENU_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)

    return True


# Key hints
KEY_HINTS = {
    "home": "q:Quit  Tab:Menu  ?:Help  Enter:Send",
    "menu": "Up/Down:Navigate  Enter:Select  Esc:Close",
    "confirm": "y:Yes  n:No  Esc:Cancel",
    "input": "Enter:Submit  Esc:Cancel",
}
