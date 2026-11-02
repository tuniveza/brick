"""Test helpers: build a program from English and run it in a pseudo-terminal, typing like a person."""
import fcntl
import os
import pty
import select
import subprocess
import struct
import sys
import tempfile
import termios
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["BRICK_MEMORY"] = "off"       # the universe reads lines the same way every time
os.environ["BRICK_FACTORY"] = "off"      # and nothing learns while the tests run
from compiler import Compiler  # noqa: E402


def build(text, folder, ask_user=lambda question: "no"):
    """Build text into folder/program, with your own words kept in folder/mywords.txt."""
    program = Compiler(os.path.join(folder, "mywords.txt"), ask_user).compile(text)
    path = os.path.join(folder, "program")
    with open(path, "wb") as f:
        f.write(program)
    os.chmod(path, 0o755)
    return path


def run(path, typing=(), folder=None, seconds=10, size=(24, 80), env=None):
    """Run in a pseudo-terminal of size (rows, columns). typing: (text to wait for, keys to type) pairs.
    Returns (screen with \\r\\n made \\n, exit code, the time each wait-for text appeared)."""
    keyboard, terminal = pty.openpty()
    fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", size[0], size[1], 0, 0))
    process = subprocess.Popen([path], stdin=terminal, stdout=terminal, stderr=terminal,
                               cwd=folder or os.path.dirname(path), env=env)
    os.close(terminal)
    screen, seen_at, looked = b"", [], 0
    for wait_for, keys in typing:
        screen = read_until(keyboard, screen, wait_for.encode(), seconds, looked)
        seen_at.append(time.time())
        assert wait_for.encode() in screen[looked:], f"never saw {wait_for!r}; screen was {screen!r}"
        looked = screen.index(wait_for.encode(), looked) + len(wait_for)
        if isinstance(keys, (int, float)):        # a number means: pause this long, then press x
            time.sleep(keys)
            keys = "x"
        os.write(keyboard, keys.encode())
    screen = read_until(keyboard, screen, None, seconds)
    code = process.wait(timeout=seconds)
    os.close(keyboard)
    return screen.decode().replace("\r\n", "\n"), code, seen_at


def read_until(keyboard, screen, text, seconds, looked=0):
    """Read until text appears after position looked, the program ends, or time runs out."""
    deadline = time.time() + seconds
    while (text is None or text not in screen[looked:]) and time.time() < deadline:
        ready, _, _ = select.select([keyboard], [], [], max(0, deadline - time.time()))
        if not ready:
            break
        try:
            more = os.read(keyboard, 4096)
        except OSError:                           # the program has ended
            break
        if not more:
            break
        screen += more
    return screen


def folder():
    return tempfile.mkdtemp(prefix="bricks-")
