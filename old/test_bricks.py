"""Tests: build programs from bricks, run them in a pseudo-terminal, and type answers like a person.

Usage: python3 test_bricks.py
"""
import os
import pty
import select
import subprocess
import tempfile
import time

from build import build
from check import read_program


def run_in_terminal(lines, typing=()):
    """Build lines into a program and run it in a pseudo-terminal.
    typing is a list of (text to wait for, answer to type).
    Returns (everything on screen, what was on screen just before each answer, exit code)."""
    program, refusals = build(lines)
    assert not refusals, refusals
    path = os.path.join(tempfile.mkdtemp(), "program")
    with open(path, "wb") as f:
        f.write(program)
    os.chmod(path, 0o755)

    keyboard, terminal = pty.openpty()
    process = subprocess.Popen([path], stdin=terminal, stdout=terminal, stderr=terminal)
    os.close(terminal)
    screen, before_typing = b"", []
    for prompt, answer in typing:
        screen = read_until(keyboard, screen, prompt.encode())
        time.sleep(0.2)                     # give the program time to run ahead, if it wrongly would
        screen = read_until(keyboard, screen, None, seconds=0.1)
        before_typing.append(screen.decode())
        os.write(keyboard, answer.encode() + b"\n")
    screen = read_until(keyboard, screen, None)
    code = process.wait(timeout=5)
    os.close(keyboard)
    return screen.decode().replace("\r\n", "\n"), before_typing, code


def read_until(keyboard, screen, text, seconds=5):
    """Keep reading the screen until text shows up, the program ends, or time runs out."""
    deadline = time.time() + seconds
    while (text is None or text not in screen) and time.time() < deadline:
        ready, _, _ = select.select([keyboard], [], [], deadline - time.time())
        if not ready:
            break
        try:
            more = os.read(keyboard, 1024)
        except OSError:                     # the program has ended
            break
        if not more:
            break
        screen += more
    return screen


def test_demo():
    lines = read_program(os.path.join(os.path.dirname(__file__), "examples", "demo.txt"))
    screen, before_typing, code = run_in_terminal(lines, [
        ("What is your name? ", "Ada"),
        ("What is your favourite food? ", "pancakes"),
        ("Press Enter to continue...", ""),
    ])
    assert screen.startswith("\x1b[2J\x1b[H"), "clear"
    assert "\x1b[36m\x1b[1mWelcome to the console brick system!\n" in screen, "colour, bold, say"
    assert "\x1b[0m\n" in screen, "plain, blank line"
    assert "What is your name? Ada\n" in screen, "ask (the typed answer shows on screen)"
    assert "Nice to meet you, Ada.\n" in screen, "say with a saved answer"
    assert "Ada likes pancakes. Good choice!\n" in screen, "say with two saved answers"
    assert "\aPress Enter to continue..." in screen, "beep, wait"
    assert "Goodbye" not in before_typing[2], "wait really pauses"
    assert screen.endswith("\x1b[35mGoodbye, Ada!\n\x1b[0m"), "stop resets colours"
    assert code == 0, "stop ends cleanly"


def test_every_colour():
    names = ["red", "green", "yellow", "blue", "purple", "cyan", "white", "grey"]
    codes = [31, 32, 33, 34, 35, 36, 37, 90]
    lines = [line for name in names for line in (f"colour {name}", f'say "{name}"')]
    screen, _, code = run_in_terminal(lines)
    for name, number in zip(names, codes):
        assert f"\x1b[{number}m{name}\n" in screen, name
    assert code == 0


def test_stops_cleanly_without_stop():
    screen, _, code = run_in_terminal(["colour red", 'say "no stop here"'])
    assert screen == "\x1b[31mno stop here\n\x1b[0m"
    assert code == 0


def test_empty_answer():
    screen, _, code = run_in_terminal(['ask "Name?" as name', 'say "Hi [name]!"'], [("Name? ", "")])
    assert screen == "Name? \nHi !\n\x1b[0m"
    assert code == 0


def test_refusals():
    program, refusals = build(['say "Hi [name]"', "colour pink", "dance", "stop", 'say "late"'])
    assert program is None
    assert len(refusals) == 4
    assert "ask \"...\" as name" in refusals[0]
    assert "pink" in refusals[1]
    assert "don't recognise" in refusals[2]
    assert "already stopped" in refusals[3]


if __name__ == "__main__":
    tests = [test_demo, test_every_colour, test_stops_cleanly_without_stop, test_empty_answer, test_refusals]
    for test in tests:
        test()
        print(f"passed: {test.__name__}")
    print(f"All {len(tests)} tests passed.")
