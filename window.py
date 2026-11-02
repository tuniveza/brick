"""The console and its window, in plain English.

Console first (works in any Linux terminal):
  write GO in the middle of the screen      put text anywhere, using the console's real size
  write score at row 2 column 10
  move to the bottom of the screen
  set the title to My Game                  the window's title
  the width of the console / the height of the console

The window itself (console codes first, then the desktop):
  put the window on the left side of the screen
  make the window full screen / bigger / smaller / 800 by 600
  move the window right 200 / centre the window
A terminal can't move its own window on Wayland, so these also ask Hyprland. They only act on
the program's own window, the one `brick` opens for it; anywhere else they do nothing.
"""
import re

import dictionary
from asm import EQUAL, NOT_ABOVE, NOT_LESS, R8, RAX, RCX, RDX
from expressions import Problem, read_value
from reader import Word, read_number

WINDOW_WORDS = {"window", "console", "terminal"}
FILLER = {"the", "of", "side", "edge", "corner", "half", "screen", "console", "window", "terminal",
          "and", "part", "a", "my", "this"}
VERTICAL = {"top": "top", "bottom": "bottom", "upper": "top", "lower": "bottom"}
HORIZONTAL = {"left": "left", "right": "right", "start": "left", "beginning": "left"}
MIDDLE = {"middle", "centre", "center", "centred", "centered"}

# Lua for Hyprland. P names our window; put(x, y, width, height) floats it and places it on its screen.
LUA_START = (
    "local w = hl.get_window(P) if not w or not w.monitor then return end "
    "local m = w.monitor local W, H = m.width / m.scale, m.height / m.scale "
    "local x, y, sw, sh = w.at.x - m.x, w.at.y - m.y, w.size.x, w.size.y "
    "local function put(px, py, pw, ph) "
    "hl.dispatch(hl.dsp.window.float({ action = 'enable', window = P })) "
    "hl.dispatch(hl.dsp.window.resize({ x = math.floor(pw), y = math.floor(ph), window = P })) "
    "hl.dispatch(hl.dsp.window.move({ x = math.floor(m.x + px), y = math.floor(m.y + py), window = P })) end ")
WINDOW_PLACES = {
    ("top", "left"): "put(0, 0, W / 2, H / 2)", ("top", "right"): "put(W / 2, 0, W / 2, H / 2)",
    ("bottom", "left"): "put(0, H / 2, W / 2, H / 2)", ("bottom", "right"): "put(W / 2, H / 2, W / 2, H / 2)",
    (None, "left"): "put(0, 0, W / 2, H)", (None, "right"): "put(W / 2, 0, W / 2, H)",
    ("top", None): "put(0, 0, W, H / 2)", ("bottom", None): "put(0, H / 2, W, H / 2)",
    ("middle", "centre"): "put((W - sw) / 2, (H - sh) / 2, sw, sh)",
}
WINDOW_HELP = ("Window things I can do: put the window on the left side of the screen, "
               "make the window full screen, make the window bigger, move the window right 200, "
               "set the title to My Game.")


def read_spot(words, names=lambda name: None):
    """'in the middle of the screen', 'at the top left', 'at row 3 column 10', 'on the right side'
    -> (vertical, horizontal), each None, a word like 'top', or ('row', value) / ('column', value).
    The dictionary's places count too: 'at the top-left', 'at the far right'."""
    words = dictionary.respell_all(words, "place")
    said = [w.word for w in words]
    if said in (["centred"], ["centered"]):
        return "middle", "centre"
    if not said or said[0] not in ("in", "at", "on", "to"):
        return None
    vertical = horizontal = None
    i = 1
    while i < len(said):
        x = said[i]
        if x in ("row", "line", "column"):
            try:
                number = read_value(words[i + 1:i + 2], names) if i + 1 < len(words) else None
            except Problem:                         # "at row house": not a spot
                return None
            if number is None or number[0] not in ("number", "name"):     # "row 3", "row n"
                return None
            if x == "column":
                horizontal = ("column", number)
            else:
                vertical = ("row", number)
            i += 2
            continue
        if x in VERTICAL:
            vertical = VERTICAL[x]
        elif x in HORIZONTAL:
            horizontal = HORIZONTAL[x]
        elif x in MIDDLE:
            vertical, horizontal = vertical or "middle", horizontal or "centre"
        elif x not in FILLER:
            return None
        i += 1
    if vertical is None and horizontal is None:
        return None
    return vertical, horizontal


def spot_at_end(body, names=lambda name: None):
    """Find a spot phrase at the end (or start) of the words -> (words left, spot) or (body, None)."""
    for start in range(max(1, len(body) - 9), len(body)):
        spot = read_spot(body[start:], names)
        if spot:
            return body[:start], spot
    for end in range(min(len(body) - 1, 9), 0, -1):
        spot = read_spot(body[:end], names)
        if spot:
            return body[end:], spot
    return body, None


def about_window(words):
    return bool({w.word for w in words} & WINDOW_WORDS)


class Window:
    # ---- console first: put text anywhere ----

    def write_placed(self, body, codes, places, spot, case=None):
        """Show the words at a spot on the screen, worked out from the console's real size."""
        a = self.a
        text, size = a.reserve(8, "placed_text"), a.reserve(16, "console_now")
        self.text_value(body, places, case) if body else self.emitter.emit_text("")
        a.address(RCX, text)
        a.store(RCX, 0, RAX)
        a.call("console_size")
        a.mov(RDX, RCX)
        a.address(RCX, size)
        a.store(RCX, 0, RAX)               # rows
        a.store(RCX, 8, RDX)               # columns
        vertical, horizontal = spot
        self.spot_row(vertical, size)
        a.push(RAX)
        self.spot_column(horizontal, vertical, size, text)
        a.mov(RCX, RAX)
        a.pop(RAX)
        if self.erases and body:                 # remember it, for "make it disappear"
            a.address(RDX, self.placed_slot())
            a.store(RDX, 0, RAX)
            a.store(RDX, 8, RCX)
            a.address(R8, text)
            a.load(R8, R8)
            a.store(RDX, 16, R8)
        a.call("place_cursor")
        if self.erases and body and vertical is None:
            self.show("\x1b7")                  # on whatever row the cursor was: the console remembers where
        if body:
            self.last_shown = "placed"
        if codes:
            self.show("".join(f"\x1b[{code}m" for code in codes))
        a.address(RAX, text)
        a.load(RAX, RAX)
        a.call("write_text")
        if codes:
            self.end_style()

    def spot_row(self, vertical, size):
        a = self.a
        if vertical is None:
            a.set(RAX, 0)                          # stay on this row
        elif vertical == "top":
            a.set(RAX, 1)
        elif vertical == "bottom":
            a.address(RAX, size)
            a.load(RAX, RAX)
        elif vertical == "middle":
            a.address(RAX, size)
            a.load(RAX, RAX)
            a.op_n("add", RAX, 1)
            a.shift_right(RAX, 1)
        else:
            self.emitter.whole(self.emitter.emit(vertical[1]))

    def spot_column(self, horizontal, vertical, size, text):
        """rax = the column to start at, so the text sits where it was asked to (never before 1)."""
        a = self.a
        if horizontal in (None, "left"):
            a.set(RAX, 1)
            return
        if isinstance(horizontal, tuple):
            self.emitter.whole(self.emitter.emit(horizontal[1]))
        else:
            a.address(RAX, size)
            a.load(RAX, RAX, 8)                    # columns
            a.address(RCX, text)
            a.load(RCX, RCX)
            a.load(RCX, RCX)                       # the text's length
            a.op("sub", RAX, RCX)
            if horizontal == "centre":
                a.shift_right(RAX, 1)              # a negative becomes huge here; caught below
                a.op_n("add", RAX, 1)
            else:
                a.op_n("add", RAX, 1)
        ok = a.new_label("column_ok")
        a.op_n("cmp", RAX, 1)
        a.jump_if(NOT_LESS, ok)
        a.set(RAX, 1)
        a.label(ok)
        big = a.new_label("column_fits")
        a.op_n("cmp", RAX, 10000)
        a.jump_if(NOT_ABOVE, big)
        a.set(RAX, 1)
        a.label(big)

    def placed_slot(self):
        """Where the last text put on the screen is remembered: its row (0: the row the console
        remembers), its column, and the text."""
        if not getattr(self, "last_placed", None):
            self.last_placed = self.a.reserve(24, "last_placed")
        return self.last_placed

    def make_disappear(self):
        """'make it disappear': blank out the text just shown, and come back to where the cursor was."""
        a = self.a
        if self.last_shown is None:
            raise Problem("Make what disappear? Show something first, like: "
                          "write hi in red at the top right, then make it disappear after 5 seconds")
        if self.last_shown == "line":
            self.show("\x1b[1F\x1b[2K")           # the line just written: rub it out, and carry on from there
            return
        slot, same_row, done = self.placed_slot(), a.new_label("same_row"), a.new_label("gone")
        a.address(RDX, slot)
        a.load(RAX, RDX, 0)
        a.op("test", RAX, RAX)
        a.jump_if(EQUAL, same_row)
        self.show("\x1b7")
        a.address(RDX, slot)
        a.load(RAX, RDX, 0)
        a.load(RCX, RDX, 8)
        a.call("place_cursor")
        self.blank_out(slot)
        self.show("\x1b8")
        a.jump(done)
        a.label(same_row)
        self.show("\x1b8")
        self.blank_out(slot)
        self.show("\r\n")
        a.label(done)

    def blank_out(self, slot):
        """Spaces over as many letters as the remembered text has."""
        a = self.a
        loop, end = a.new_label("blank"), a.new_label("blanked")
        a.address(RCX, slot)
        a.load(RCX, RCX, 16)
        a.load(RCX, RCX)
        a.push(RCX)
        a.label(loop)
        a.pop(RCX)
        a.op("test", RCX, RCX)
        a.jump_if(EQUAL, end)
        a.op_n("sub", RCX, 1)
        a.push(RCX)
        self.show(" ")
        a.jump(loop)
        a.label(end)

    def move_to_spot(self, words):
        spot = read_spot([Word("to")] + words, self.kind_of)
        if not spot:
            raise Problem("Move to where? Try: move to the top, move to the middle of the screen, "
                          "move to row 3 column 10")
        self.write_placed([], [], None, spot)

    # ---- console first: the title ----

    def set_title(self, words):
        if not words:
            raise Problem("Set the title to what? Try: set the title to My Game")
        self.text_value(words, None)
        self.a.push(RAX)
        self.show("\x1b]2;")
        self.a.pop(RAX)
        self.a.call("write_text")
        self.show("\a")

    # ---- the window itself ----

    def window_action(self, words):
        said = [part for w in words if w.word for part in w.word.split("-")]     # "bottom-right"
        spots = set(said)
        console, lua = "", None
        size = self.window_size(words)
        vertical = next((VERTICAL[x] for x in said if x in VERTICAL), None)
        horizontal = next((HORIZONTAL[x] for x in said if x in HORIZONTAL), None)
        if spots & MIDDLE and not vertical and not horizontal:
            vertical, horizontal = "middle", "centre"
        if spots & {"full", "fullscreen", "fill", "whole", "maximise", "maximize", "maximum", "entire"}:
            console, lua = "\x1b[9;1t", "put(0, 0, W, H)"
        elif spots & {"bigger", "larger", "grow", "wider", "taller"}:
            lua = "put(x - sw / 8, y - sh / 8, sw * 1.25, sh * 1.25)"
        elif spots & {"smaller", "shrink", "tinier", "little"}:
            lua = "put(x + sw / 10, y + sh / 10, sw * 0.8, sh * 0.8)"
        elif size:                                  # a size left out stays as it is; so does a place
            width, height = size
            console = f"\x1b[4;{'' if height is None else height};{'' if width is None else width}t"
            pw, ph = "sw" if width is None else width, "sh" if height is None else height
            px = {"left": "0", "right": f"W - {pw}", "centre": f"(W - {pw}) / 2"}.get(horizontal, "x")
            py = {"top": "0", "bottom": f"H - {ph}", "middle": f"(H - {ph}) / 2"}.get(vertical, "y")
            lua = f"put({px}, {py}, {pw}, {ph})"
        elif said[0] in ("move", "go", "nudge", "shift", "slide") and not spots & (FILLER - {"the", "window", "console", "terminal", "my", "this", "a"}) \
                and spots & {"left", "right", "up", "down"} and "to" not in spots:
            lua = self.nudge(words, said)
        else:
            lua = WINDOW_PLACES.get((vertical, horizontal))
        if lua is None:
            raise Problem("What should the window do? " + WINDOW_HELP)
        self.uses_window = True
        if console:
            self.show(console)
        self.a.address(RAX, self.a.text(LUA_START + lua))
        self.a.call("desktop")

    def window_size(self, words):
        """'800 by 600', '800 x 600', '800x600', 'width 800px and height 600px', '800 pixels wide'
        -> (width, height), either None if it isn't said; None if neither is."""
        words = [Word(part) for w in words for part in re.split(r"(?<=\d)(px|pixels?|x|×)(?=\d|\W|$)", w.raw) if part]
        words = [w for w in words if w.word not in ("px", "pixel", "pixels", "of", "is", "be")]
        said = [w.word for w in words]
        for i, w in enumerate(said):
            if w in ("by", "x", "×", "*") and 0 < i < len(words) - 1:
                width, _ = read_number(words, i - 1)
                height, _ = read_number(words, i + 1)
                if isinstance(width, int) and isinstance(height, int):
                    return width, height
        sizes = {}
        for i, w in enumerate(said):
            side = {"width": "wide", "wide": "wide", "height": "high", "high": "high", "tall": "high"}.get(w)
            number = read_number(words, i + 1)[0] if w in ("width", "height") else \
                read_number(words, i - 1)[0] if i else None             # "width 50" / "50 wide"
            if side and isinstance(number, int):
                sizes[side] = number
        return (sizes.get("wide"), sizes.get("high")) if sizes else None

    def nudge(self, words, said):
        steps = next((n for n in (read_number(words, i)[0] for i in range(len(words))) if isinstance(n, int)), 100)
        direction = next(x for x in said if x in ("left", "right", "up", "down"))
        dx, dy = {"left": (-steps, 0), "right": (steps, 0), "up": (0, -steps), "down": (0, steps)}[direction]
        return f"put(x + {dx}, y + {dy}, sw, sh)"
