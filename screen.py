"""Built-in bricks for the console and its window.

Console first: the console's size (an ioctl), and putting the cursor anywhere (standard codes).
Desktop second: some things only the desktop can do, like moving the window itself.
For those, the program hands a few lines of Lua to Hyprland (`hyprctl eval`), naming its own
window: the one in BRICK_WINDOW (set by `brick` when it opens a window), else its parent's
pid. If that isn't a window, or there's no Hyprland, nothing happens.
"""
from asm import EQUAL, LESS, NOT_EQUAL, R8, R9, R10, R11, R12, RAX, RCX, RDI, RDX, RSI, RSP

ROWS_COLUMNS = 0x5413          # ioctl: how many rows and columns the console has


def add_all(a):
    for brick in (console_size, place_cursor, getenv, desktop):
        brick(a)


def remember_environment(a):
    """Runs first, while rsp still points at argc: note where the environment starts."""
    a.load(RAX, RSP)                   # [rsp] = argc
    a.shift_left(RAX, 3)
    a.op("add", RAX, RSP)
    a.op_n("add", RAX, 16)             # past argc, the arguments and their ending 0
    a.address(RCX, "environment")
    a.store(RCX, 0, RAX)
    a.space["environment"] = 8


def console_size(a):
    """-> rax = rows, rcx = columns (24 x 80 if this isn't a console)."""
    size = a.reserve(8, "console_size")
    a.label("console_size")
    a.set(RAX, 16)
    a.set(RDI, 1)
    a.set(RSI, ROWS_COLUMNS)
    a.address(RDX, size)
    a.syscall()
    a.op("test", RAX, RAX)
    a.jump_if(NOT_EQUAL, "cs_guess")
    a.address(RDX, size)
    a.load(RAX, RDX)
    a.mov(RCX, RAX)
    a.shift_right(RCX, 16)
    a.op_n("and", RCX, 0xFFFF)
    a.op_n("and", RAX, 0xFFFF)
    a.jump_if(EQUAL, "cs_guess")
    a.ret()
    a.label("cs_guess")
    a.set(RAX, 24)
    a.set(RCX, 80)
    a.ret()


def place_cursor(a):
    """rax = row (0: stay on this row), rcx = column -> the cursor goes there."""
    v = a.reserve(16, "place_vars")
    a.label("place_cursor")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.store(R11, 8, RCX)
    a.address(RAX, a.text("\x1b["))
    a.call("write_text")
    a.address(R11, v)
    a.load(RAX, R11, 0)
    a.op("test", RAX, RAX)
    a.jump_if(EQUAL, "pc_column")
    a.call("number_to_text")
    a.call("write_text")
    a.address(RAX, a.text(";"))
    a.call("write_text")
    a.address(R11, v)
    a.load(RAX, R11, 8)
    a.call("number_to_text")
    a.call("write_text")
    a.address(RAX, a.text("H"))
    a.jump("write_text")
    a.label("pc_column")
    a.load(RAX, R11, 8)
    a.call("number_to_text")
    a.call("write_text")
    a.address(RAX, a.text("G"))
    a.jump("write_text")


def getenv(a):
    """rax = a name followed by '=' (as a text) -> rax = its value as a text, or 0 if it isn't set."""
    a.label("getenv")
    a.mov(R8, RAX)
    a.address(R9, "environment")
    a.load(R9, R9)
    a.label("ge_next")
    a.load(R10, R9)
    a.op("test", R10, R10)
    a.jump_if(EQUAL, "ge_none")
    a.mov(RSI, R10)
    a.lea(RDI, R8, 8)
    a.load(RCX, R8)
    a.compare_bytes()
    a.jump_if(EQUAL, "ge_found")
    a.op_n("add", R9, 8)
    a.jump("ge_next")
    a.label("ge_found")                # rsi now points just past the '='
    a.mov(R12, RSI)
    a.set(RCX, 0)
    a.label("ge_length")
    a.mov(RDX, R12)
    a.op("add", RDX, RCX)
    a.load_byte(RDX, RDX)
    a.op("test", RDX, RDX)
    a.jump_if(EQUAL, "ge_copy")
    a.op_n("add", RCX, 1)
    a.jump("ge_length")
    a.label("ge_copy")
    a.call("new_text")
    a.load(RCX, RAX)
    a.lea(RDI, RAX, 8)
    a.mov(RSI, R12)
    a.copy_bytes()
    a.ret()
    a.label("ge_none")
    a.set(RAX, 0)
    a.ret()


def desktop(a):
    """rax = Lua for Hyprland, which can use P (this program's window) -> run it, then wait a moment
    so the console has caught up with any new size."""
    v = a.reserve(64, "desktop_vars")    # 0 the Lua, 8 the whole command, 16.. argument list
    pause = a.reserve(16, "desktop_pause")
    a.label("desktop")
    a.address(R11, v)
    a.store(R11, 0, RAX)
    a.address(RAX, a.text("BRICK_WINDOW="))      # which window is ours?
    a.call("getenv")
    a.op("test", RAX, RAX)
    a.jump_if(NOT_EQUAL, "dt_named")
    a.set(RAX, 110)                              # getppid: the terminal that started us
    a.syscall()
    a.call("number_to_text")
    a.mov(RCX, RAX)
    a.address(RAX, a.text("pid:"))
    a.call("join")
    a.label("dt_named")
    a.mov(RCX, RAX)
    a.address(RAX, a.text('local P = "'))
    a.call("join")
    a.address(RCX, a.text('" '))
    a.call("join")
    a.address(R11, v)
    a.load(RCX, R11, 0)
    a.call("join")
    a.address(R11, v)
    a.store(R11, 8, RAX)
    a.set(RAX, 57)                               # fork
    a.syscall()
    a.op("test", RAX, RAX)
    a.jump_if(EQUAL, "dt_child")
    a.jump_if(LESS, "dt_done")
    a.mov(RDI, RAX)                              # wait4 for hyprctl to finish
    a.set(RSI, 0)
    a.set(RDX, 0)
    a.set(R10, 0)
    a.set(RAX, 61)
    a.syscall()
    a.address(RDI, pause)                        # 0.15 seconds for the console to resize
    a.set(RAX, 150_000_000)
    a.store(RDI, 8, RAX)
    a.set(RSI, 0)
    a.set(RAX, 35)
    a.syscall()
    a.label("dt_done")
    a.ret()
    a.label("dt_child")
    a.address(RDI, a.text("/dev/null"))          # hyprctl's own messages go nowhere
    a.op_n("add", RDI, 8)
    a.set(RSI, 1)
    a.set(RDX, 0)
    a.set(RAX, 2)
    a.syscall()
    a.mov(R12, RAX)
    for screen in (1, 2):
        a.set(RAX, 33)                           # dup2
        a.mov(RDI, R12)
        a.set(RSI, screen)
        a.syscall()
    a.address(R11, v)
    for n, word in enumerate(("hyprctl", "eval")):
        a.address(RAX, a.text(word))
        a.op_n("add", RAX, 8)
        a.store(R11, 16 + 8 * n, RAX)
    a.load(RAX, R11, 8)
    a.op_n("add", RAX, 8)
    a.store(R11, 32, RAX)
    a.set(RAX, 0)
    a.store(R11, 40, RAX)
    a.address(RDI, a.text("/usr/bin/hyprctl"))   # execve
    a.op_n("add", RDI, 8)
    a.lea(RSI, R11, 16)
    a.address(RDX, "environment")
    a.load(RDX, RDX)
    a.set(RAX, 59)
    a.syscall()
    a.set(RAX, 60)                               # no hyprctl: just end this copy
    a.set(RDI, 127)
    a.syscall()
