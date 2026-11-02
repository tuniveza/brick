"""Tests for the forgiving English and the safety nets: everything here builds and runs a real program.

Usage: python3 tests/test_forgiving.py
"""
import os
import pty
import subprocess
import sys
import termios
import time

from terminal import build, folder, read_until, run

GREEN, RESET = "\x1b[38;2;0;192;0m", "\x1b[0m"
HERE = os.path.dirname(os.path.abspath(__file__))
BRICK = os.path.join(os.path.dirname(HERE), "brick.py")


def output(text, typing=()):
    screen, code, _ = run(build(text, folder()), typing)
    assert code == 0, (code, screen)
    return screen


def refusal(text):
    from expressions import Problem
    try:
        build(text, folder())
    except Problem as problem:
        return str(problem)
    raise AssertionError(f"{text!r} should have been refused")


def test_colours_before_or_after():
    assert output("write in green ten") == f"{GREEN}ten{RESET}\n"
    assert output("write ten in green") == f"{GREEN}ten{RESET}\n"
    assert output('write "ten", in green') == f"{GREEN}ten{RESET}\n"
    assert output("write in bold red GAME OVER") == f"\x1b[1m\x1b[38;2;255;0;0mGAME OVER{RESET}\n"
    assert output("write hi on a blue background") == f"\x1b[48;2;0;0;255mhi{RESET}\n"
    assert output("write I live in a red house") == "I live in a red house\n"


def test_more_colours():
    assert output("write trash in orange") == f"\x1b[38;2;255;165;0mtrash{RESET}\n"
    assert output("write hi on a pink background") == f"\x1b[48;2;255;128;192mhi{RESET}\n"


def test_after_a_while():
    started = time.time()
    assert output("write hi, after 0.3 seconds write bye") == "hi\nbye\n"
    assert output("write a and 0.2 seconds later write b") == "a\nb\n"
    assert output("write c. In 0.1 seconds, write d") == "c.\nd\n"
    assert time.time() - started >= 0.6


def test_numbers_shown_as_typed():
    assert output("write ten") == "ten\n"
    assert output("write 3.5") == "3.5\n"
    assert output("write 3.5 plus 1") == "4.50\n"


def test_polite_extra_words():
    assert output("computer, can you make it say hello twice") == "hello\nhello\n"
    assert output("please write hi and please beep") == "hi\n\a"
    assert output("first write one, then write two, and finally write three") == "one\ntwo\nthree\n"


def test_sentences_and_colons():
    assert output("write hi. write bye") == "hi.\nbye\n"
    assert output("repeat 2 times: write hi") == "hi\nhi\n"
    assert output("3 times write ho") == "ho\nho\nho\n"
    assert output("write “curly quotes” are fine") == "curly quotes are fine\n"


def test_loops():
    assert output("set x to 0, add 1 to x until x is 3, write x") == "3\n"
    assert output("set y to 0, while y is less than 4 add 1 to y, write y") == "4\n"
    assert output("set z to 0, forever add 1 to z and if z is 5 leave the loop, write z") == "5\n"
    assert output("set n to 0, repeat until n is 2, add 1 to n\nwrite n") == "2\n"
    assert output("set k to 0, keep going until k is 3: add 1 to k\nwrite k") == "3\n"


def test_everyday_phrasing():
    assert output("score = 5, add one to score, score is now score times 2, write score") == "12\n"
    assert output("make a list called fruits, add apple to fruits, add pear to fruits, "
                  "for every fruit in fruits, write fruit") == "apple\npear\n"
    assert output("make a list called fruits, add apple to fruits\nhow many in fruits") == "1\n"
    assert output("set name to Ada, write hello name") == "hello Ada\n"
    assert output("set score to 6, if the score is 6, say six! otherwise say not six") == "six!\n"
    assert "Did you mean 'score'?" in refusal("set score to 1, add scroe to score")


def test_counting():
    assert output("count to 3") == "1\n2\n3\n"
    assert output("count down from 3 to 1") == "3\n2\n1\n"
    assert output("for each n from 2 to 6 if n is more than 4 write n") == "5\n6\n"
    assert output("set total to 0, for each n from 1 to 4, add n to total\nwrite total") == "10\n"
    assert output("do this 2 times: write hi") == "hi\nhi\n"


def test_answers():
    screen = output("ask a number as guess, write guess plus 1",
                    [("Number? ", "abc\n"), ("Please type a number: ", "5\n")])
    assert screen.endswith("6\n"), repr(screen)
    screen = output('ask "Again?" as answer, if answer is yes write ok, otherwise write no',
                    [("Again? ", "YES  \n")])
    assert screen.endswith("ok\n"), repr(screen)
    screen = output("ask the user for their name, write hi name", [("Name? ", "Al\n")])
    assert screen.endswith("hi Al\n"), repr(screen)
    screen = output('ask "Name?" in green as name, write hi name', [("Name? ", "Bo\n")])
    assert screen.startswith(f"{GREEN}Name? {RESET}Bo\nhi Bo"), repr(screen)


def test_names_with_spaces_and_random_items():
    assert output('set high score to 10, add 5 to high score, write "best:" high score') == "best: 15\n"
    assert output('make a list called pets, add "cat" to pets, write a random item from pets') == "cat\n"
    screen = output("set n to a random number between 1 and 3, if n is at least 1 and n is at most 3 write ok")
    assert screen == "ok\n"


def test_moving_and_stopping():
    assert output("move to the top, move to the left side, move down 2") == "\x1b[1;1H\x1b[1G\x1b[2B"
    assert output("write a, stop the game, write b") == f"a\n{RESET}"
    assert output("write 5 divided by 0") == "infinity\n"
    assert output("colour green, write hi") == f"{GREEN}hi\n{RESET}"


def test_ctrl_c_while_waiting_puts_the_terminal_back():
    path = build("write ready, wait for a key, write after", folder())
    keyboard, terminal = pty.openpty()
    process = subprocess.Popen([path], stdin=terminal, stdout=terminal, stderr=terminal)
    screen = read_until(keyboard, b"", b"ready", 5)
    time.sleep(0.2)
    os.write(keyboard, b"\x03")
    assert process.wait(timeout=5) == 130
    assert termios.tcgetattr(terminal)[3] & termios.ECHO, "typing should show again"
    os.close(terminal)
    os.close(keyboard)
    assert b"after" not in screen


def test_input_ending_ends_the_program():
    path = build("repeat forever: ask a number as n", folder())
    finished = subprocess.run([path], stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
    assert finished.returncode == 0


def test_helpful_messages():
    assert "What should the window do?" in refusal("put the window somewhere nice")
    assert "Did you mean 'score'?" in refusal("set score to 1, if scroe is 1 write hi")
    assert "missing its partner" in refusal('write "hello')
    assert "Did you mean 'write'?" in refusal("wirte hello")
    assert "You can say: put name on the end of names" in refusal("put x")
    assert "no loop to leave" in refusal("leave the loop")


def test_brick_command():
    shown = subprocess.run([sys.executable, BRICK, "help"], capture_output=True, text=True)
    assert "ask \"What is your name?\" as name" in shown.stdout, shown.stdout
    missing = subprocess.run([sys.executable, BRICK, "nothing-here.txt"], capture_output=True, text=True,
                             cwd=folder())
    assert "can't find" in missing.stdout and missing.returncode == 1, missing.stdout
    here = folder()
    with open(os.path.join(here, "hi.txt"), "w") as f:
        f.write("write hi")
    ran = subprocess.run([sys.executable, BRICK, "hi"], capture_output=True, text=True, cwd=here)
    assert ran.stdout.endswith("hi\n"), ran.stdout


def test_quoted_words_before_a_full_stop():
    # these used to crash brick itself, instead of building or giving a message
    assert output('repeat 2 times: write "hi".') == "hi.\nhi.\n"           # a sentence's full stop is shown
    from expressions import Problem
    try:
        build('Let the user guess the number, and demonstrate "too large" or "too little".', folder())
    except Problem:
        pass


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
