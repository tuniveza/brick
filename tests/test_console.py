"""Tests for the console and window words. Programs run in a 20 x 40 pseudo-terminal.

Usage: python3 tests/test_console.py
"""
import os
import sys

from terminal import build, folder, run
from reader import words_of  # noqa: E402 (terminal finds brick)
from window import Window  # noqa: E402

GREEN, RED, RESET = "\x1b[38;2;0;192;0m", "\x1b[38;2;255;0;0m", "\x1b[0m"


def output(text, typing=()):
    screen, code, _ = run(build(text, folder()), typing, size=(20, 40))
    assert code == 0, (code, screen)
    return screen


def refusal(text):
    from expressions import Problem
    try:
        build(text, folder())
    except Problem as problem:
        return str(problem)
    raise AssertionError(f"{text!r} should have been refused")


def test_console_size():
    assert output("write the width of the console") == "40\n"
    assert output("write the height of the screen") == "20\n"


def test_text_anywhere():
    assert output("write GO in the middle of the screen") == "\x1b[10;20HGO\n"
    assert output("set score to 5, write score at the top right") == "\x1b[1;40H5\n"
    assert output("write hi at row 2 column 10") == "\x1b[2;10Hhi\n"
    assert output("write GO in green in the middle") == f"\x1b[10;20H{GREEN}GO{RESET}\n"
    assert output("write in green ten at the bottom left") == f"\x1b[20;1H{GREEN}ten{RESET}\n"
    assert output("write this line is far too long for the right side at the right side").startswith("\x1b[1G")


def test_putting_text_on_the_screen():
    assert output("put purple at the right side of the screen") == "\x1b[35Gpurple\n"
    assert output("put GO in green in the middle") == f"\x1b[10;20H{GREEN}GO{RESET}\n"
    assert output("place hi at row 2 column 10") == "\x1b[2;10Hhi\n"
    assert output('make a list called names\nput "Zed" at the top of names\nput "Bo" on the end of names\n'
                  "for each name in names write name") == "Zed\nBo\n"
    assert output("add hi in red to the right of the window") == f"\x1b[39G{RED}hi{RESET}\n"
    assert output("add red text saying hi at the top") == f"\x1b[1;1H{RED}hi{RESET}\n"
    assert "What should the red text say?" in refusal("add red text to the right of the window")
    assert output("put text on it that says hi") == "hi\n"
    assert output("write a message in the window saying hello there") == "hello there\n"
    assert output("put red text at the top that reads hi") == f"\x1b[1;1H{RED}hi{RESET}\n"


def test_making_text_disappear():
    assert output("write hi at the top right\nmake it disappear\nwrite ok") == \
        "\x1b[1;39Hhi\n\x1b7\x1b[1;39H  \x1b8ok\n"
    assert output("write hi on the right\nmake it vanish") == "\x1b[39G\x1b7hi\n\x1b8  \r\n"
    assert output("write hi\nhide it\nwrite ok") == "hi\n\x1b[1F\x1b[2Kok\n"
    assert output("write hi\nmake it disappear after 1 second") == "hi\n\x1b[1F\x1b[2K"
    assert "Show something first" in refusal("make it disappear")


def test_a_wait_at_the_end():
    assert output("write hi after 1 second") == "hi\n"
    assert output("write 2 seconds") == "2 seconds\n"
    assert output("write it ends in 5 minutes") == "it ends in 5 minutes\n"


def test_moving_the_cursor():
    assert output("move to the middle of the screen") == "\x1b[10;21H"
    assert output("move to row 3 column 7, move down 2") == "\x1b[3;7H\x1b[2B"


def test_title():
    assert output("set the title to My Game") == "\x1b]2;My Game\a"
    assert output("set n to 3, name the window Level n") == "\x1b]2;Level 3\a"


def test_window_words_are_safe_outside_their_own_window():
    """In a terminal that isn't the program's own window, window words must not move anything."""
    env = dict(os.environ, BRICK_WINDOW="pid:1")      # names a process that has no window
    for line in ["put console at left side of screen and write in green ten",
                 "make the window full screen, write ok",
                 "make the window bigger, move the window right 200, centre the window, write ok",
                 "make the window 800 by 600, write ok"]:
        screen, code, _ = run(build(line, folder()), size=(20, 40), env=env)
        assert code == 0, (line, code, screen)
        assert screen.endswith("\n"), (line, screen)
    screen, _, _ = run(build("make the window full screen, write ok", folder()), size=(20, 40), env=env)
    assert screen == "\x1b[9;1tok\n", repr(screen)                # the console code goes first
    line = "place window at right side of the screen width 50px and height 50px then put text on it that says hi"
    program = build(line, folder())
    assert b"put(W - 50, y, 50, 50)" in open(program, "rb").read()
    screen, _, _ = run(program, size=(20, 40), env=env)
    assert screen == "\x1b[4;50;50thi\n", repr(screen)
    for size, said in [((800, 600), "800x600"), ((800, 600), "800px by 600px"), ((400, None), "400 pixels wide")]:
        assert Window.window_size(None, words_of(said)) == size, said


if __name__ == "__main__":
    tests = [value for name, value in list(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"passed: {test.__name__}")
        except Exception as problem:
            failed += 1
            print(f"FAILED: {test.__name__}: {type(problem).__name__}: {problem}")
    print(f"{len(tests) - failed} of {len(tests)} tests passed.")
    sys.exit(1 if failed else 0)
