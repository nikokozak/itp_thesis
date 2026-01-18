"""Theme constants for Codignity TUI.

The TUI aims for a readable, high-contrast "control deck" look (cyberpunk/CRT)
while keeping compatibility with basic 8-color terminals.
"""

import curses
import os

# ASCII art banner
BANNER = r"""
   ______  ____  ____  _ ____ _   _ ___ _____ __   __
  / ___/ / __ \|  _ \| |  _ \ | | |_ _|_   _|\ \ / /
 / /__ / / /_/ /| | | | | |_) | |_| || |  | |   \ V /
 \___//_/\____/ |_| |_|_|____/ \___/|___| |_|    |_|
"""

BANNER_LINES = [line for line in BANNER.strip().split("\n")]
TAGLINE_LINES = [
    "SELF-DESCRIBING NODES // UART LINE PROTOCOL",
    "OFFLINE MAINTAINABLE // READABLE BY HUMANS",
]

BANNER_HEIGHT = len(BANNER_LINES) + len(TAGLINE_LINES)
BANNER_WIDTH = max(
    max(len(line) for line in BANNER_LINES),
    max(len(line) for line in TAGLINE_LINES),
)

# Color pair indices
COLOR_NORMAL = 0
COLOR_BANNER = 1
COLOR_STATUS = 2
COLOR_ERROR = 3
COLOR_SUCCESS = 4
COLOR_PROMPT = 5
COLOR_KEY_HINT = 6
COLOR_MENU_SELECTED = 7
COLOR_CHROME = 8
COLOR_DIM = 9
COLOR_WARNING = 10
COLOR_TITLE = 11
COLOR_BORDER = 12
COLOR_PANEL = 13

# Theme selection (environment variable; see `codignity_tui.py --help`).
THEME_ENV = "CODIGNITY_TUI_THEME"
THEME_DEFAULT = "cyberpunk"


def _pick_color(color_256: int, color_8: int) -> int:
    """Pick a color for the current terminal capabilities."""
    return color_256 if curses.COLORS >= 256 else color_8


def init_colors(theme: str | None = None) -> bool:
    """Initialize color pairs. Returns True if colors available."""
    if not curses.has_colors():
        return False

    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        # Some curses builds/terms don't support default colors.
        pass

    theme_name = (theme or os.environ.get(THEME_ENV, THEME_DEFAULT)).strip().lower()
    if theme_name not in ("cyberpunk", "classic"):
        theme_name = THEME_DEFAULT

    if theme_name == "classic":
        # Existing, conservative 8-color palette.
        curses.init_pair(COLOR_BANNER, curses.COLOR_WHITE, curses.COLOR_CYAN)
        curses.init_pair(COLOR_STATUS, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(COLOR_ERROR, curses.COLOR_RED, -1)
        curses.init_pair(COLOR_SUCCESS, curses.COLOR_GREEN, -1)
        curses.init_pair(COLOR_PROMPT, curses.COLOR_YELLOW, -1)
        curses.init_pair(COLOR_KEY_HINT, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(COLOR_MENU_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(COLOR_CHROME, curses.COLOR_BLACK, curses.COLOR_CYAN)

        # Extras (best-effort).
        curses.init_pair(COLOR_DIM, curses.COLOR_WHITE, -1)
        curses.init_pair(COLOR_WARNING, curses.COLOR_YELLOW, -1)
        curses.init_pair(COLOR_TITLE, curses.COLOR_CYAN, -1)
        curses.init_pair(COLOR_BORDER, curses.COLOR_CYAN, -1)
        curses.init_pair(COLOR_PANEL, curses.COLOR_WHITE, -1)
        return True

    # Cyberpunk palette (uses 256-color indices when available).
    bg_panel = _pick_color(17, curses.COLOR_BLACK)  # dark navy
    bg_bar = _pick_color(18, curses.COLOR_BLUE)     # slightly brighter navy

    fg_text = _pick_color(252, curses.COLOR_WHITE)  # near-white
    fg_dim = _pick_color(245, curses.COLOR_WHITE)   # grey (8-color fallback uses A_DIM elsewhere)

    fg_cyan = _pick_color(51, curses.COLOR_CYAN)        # neon cyan
    fg_magenta = _pick_color(201, curses.COLOR_MAGENTA) # neon magenta
    fg_green = _pick_color(46, curses.COLOR_GREEN)      # neon green
    fg_red = _pick_color(197, curses.COLOR_RED)         # hot red/pink
    fg_orange = _pick_color(214, curses.COLOR_YELLOW)   # amber/orange

    # Primary UI surfaces
    curses.init_pair(COLOR_CHROME, fg_text, bg_bar)
    curses.init_pair(COLOR_STATUS, fg_text, bg_bar)
    curses.init_pair(COLOR_KEY_HINT, fg_cyan, bg_bar)

    # Panels + frames
    curses.init_pair(COLOR_PANEL, fg_text, bg_panel)
    curses.init_pair(COLOR_BORDER, fg_cyan, bg_panel)
    curses.init_pair(COLOR_TITLE, fg_magenta, bg_panel)
    curses.init_pair(COLOR_DIM, fg_dim, bg_panel)

    # Semantic colors (kept on panel background so log/panels stay consistent)
    curses.init_pair(COLOR_SUCCESS, fg_green, bg_panel)
    curses.init_pair(COLOR_ERROR, fg_red, bg_panel)
    curses.init_pair(COLOR_WARNING, fg_orange, bg_panel)
    curses.init_pair(COLOR_PROMPT, fg_orange, bg_panel)

    # Banner + selection
    curses.init_pair(COLOR_BANNER, fg_cyan, bg_bar)
    curses.init_pair(COLOR_MENU_SELECTED, bg_panel, fg_magenta)

    return True


# Key hints
KEY_HINTS = {
    "home": "p Probe  g Pins  m Meta  h Hist  s Src  v Val  l Load  c Snap  r Rest  ↑/↓ Scroll  Tab Menu  ? Help  q Quit",
    "menu": "j/k or Arrows Navigate  Enter Select  Esc Close",
    "confirm": "y Yes  n No  Esc Cancel",
    "input": "Enter Submit  Esc Cancel",
    "help": "Esc Close  Tab Menu",
    "load_wizard": "Space Toggle  Enter Start  Esc Cancel",
    "snapshot_wizard": "Space Toggle  Enter Create  Esc Cancel",
    "restore_wizard": "Arrows Navigate  Enter Select/Restore  Esc Cancel",
    "pins": "j/k Nav  c Claim  u Release  t Toggle  i In  o Out  r Refresh  Esc Back",
}
