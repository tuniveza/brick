"""Tests for each build step. Every test builds real programs and runs them in a pseudo-terminal.

Usage: python3 tests/test_steps.py
"""
import datetime
import os
import re
import subprocess
import sys

from terminal import build, folder, run

GREEN, RED, RESET = "\x1b[38;2;0;192;0m", "\x1b[38;2;255;0;0m", "\x1b[0m"
HERE = os.path.dirname(os.path.abspath(__file__))
BRICK = os.path.join(os.path.dirname(HERE), "brick.py")


def test_base():
    screen, code, _ = run(build("""
write hello there in green
set x to 7
write x plus 3
write x divided by 2
write 6 divided by 3
write 3.5 times 2
write three point five plus 1 to 3 places
write 0.1 plus 0.2
write round 2.5, round up 2.1, round down 2.9 and whole 7.8
write 10 divided by 4 times 2
write minus 3 plus 1
""", folder()))
    assert screen == (f"{GREEN}hello there{RESET}\n10\n3.50\n2\n7.00\n4.500\n0.30\n"
                      "3, 3, 2 and 7\n5\n-2\n"), repr(screen)
    assert code == 0


def test_step6_reaction_game():
    """Must pass: the reaction game, word for word from the spec."""
    path = build("write get ready, wait a random number from 1 to 5 seconds, write GO in green, "
                 "start a timer as t, wait for a key, write you took t seconds", folder())
    screen, code, seen_at = run(path, [("get ready", ""), ("GO", 0.4)])
    took = re.fullmatch(rf"get ready\n{re.escape(GREEN)}GO{re.escape(RESET)}\nyou took (\d+\.\d\d) seconds\n",
                        screen)
    assert took, repr(screen)
    assert 0.35 <= float(took.group(1)) <= 1.5, took.group(1)          # one key, no Enter needed
    assert 0.9 <= seen_at[1] - seen_at[0] <= 5.6, seen_at[1] - seen_at[0]  # the random wait
    assert code == 0


def test_step6_clock_and_decimals():
    screen, code, _ = run(build("""
start timing as t
wait 0.5 seconds
write how long since t
write the time
write 7 divided by 2 rounded
set price to 2.5
write price times 3 to 1 place
""", folder()))
    lines = screen.splitlines()
    assert 0.49 <= float(lines[0]) <= 0.7, lines[0]
    shown = datetime.datetime.strptime(lines[1], "%H:%M:%S").time()
    now = datetime.datetime.now(datetime.timezone.utc)
    gap = abs((now.hour * 3600 + now.minute * 60 + now.second) - (shown.hour * 3600 + shown.minute * 60 + shown.second))
    assert gap <= 2 or gap >= 86398, (lines[1], now)
    assert lines[2:] == ["4", "7.5"], lines
    assert code == 0


def test_step7_lists():
    """Must pass: make a list, ask 3 times and add, then hello to each."""
    path = build("""
make a list called names, ask a name 3 times and add it to names, then for each name in names write hello name
write there are how many in names people, the first is first in names and the last is last in names
put "Zed" at the front of names
write item 2 of names
if names contains "Bob" write Bob is here, otherwise write no Bob
if "Max" is in names write Max is here, otherwise write no Max
remove the last from names
write I took off it, leaving names
make a list called scores, add 3 to scores, add 4.5 to scores, write scores
""", folder())
    screen, code, _ = run(path, [("Name? ", "Ada\n"), ("Name? ", "Bob\n"), ("Name? ", "Cy\n")])
    assert screen == ("Name? Ada\nName? Bob\nName? Cy\nhello Ada\nhello Bob\nhello Cy\n"
                      "there are 3 people, the first is Ada and the last is Cy\n"
                      "Ada\nBob is here\nno Max\nI took off it, leaving Zed, Ada, Bob\n"
                      "3, 4\n"), repr(screen)
    assert code == 0


HIGH_SCORE = """
load best.txt as best
ask "What did you score?" as score
if score is more than best, write "New high score!" in green and save score to best.txt, otherwise write "The high score is still" best
"""


def test_step8_files():
    """Must pass: a high score that survives closing the program."""
    here = folder()
    path = build(HIGH_SCORE, here)
    first, _, _ = run(path, [("score? ", "40\n")], here)
    assert first == (f"(best.txt doesn't exist yet, so best starts empty.)\n"
                     f"What did you score? 40\n{GREEN}New high score!{RESET}\n"), repr(first)
    second, _, _ = run(path, [("score? ", "25\n")], here)
    assert second == "What did you score? 25\nThe high score is still 40\n", repr(second)
    third, _, _ = run(path, [("score? ", "90\n")], here)
    assert third.endswith(f"{GREEN}New high score!{RESET}\n")
    assert open(os.path.join(here, "best.txt")).read() == "90\n"


def test_step8_lists_and_deleting():
    here = folder()
    path = build("""
add "Ada" to the end of names.txt
add "Bob" to the end of names.txt
make a list called names
load names.txt as names
write how many in names "names:" names
delete names.txt
""", here)
    screen, _, _ = run(path, [("(yes/no) ", "no\n")], here)
    assert "2 names: Ada, Bob\n" in screen and "OK, I kept it.\n" in screen, repr(screen)
    assert os.path.exists(os.path.join(here, "names.txt"))
    screen, _, _ = run(path, [("(yes/no) ", "yes\n")], here)
    assert "4 names: Ada, Bob, Ada, Bob\n" in screen and "Deleted.\n" in screen, repr(screen)
    assert not os.path.exists(os.path.join(here, "names.txt"))


def test_step9_words():
    """Must pass: a hangman-style letter check."""
    path = build("""
set secret to "banana"
write the word has how many letters in secret letters and starts with first letter of secret in capitals
ask a letter as guess
set guess to lowercase guess
if secret contains guess, write yes! guess is in the word in green, otherwise write "no", guess is not in the word in red
for each letter in secret if letter is guess write letter on the same line otherwise write _ on the same line
write a blank line
write shout secret, letter 3 of secret, last letter of secret
if secret starts with "ban" write it starts with ban
if secret ends with "x" write wrong, otherwise write it does not end with x
set code to "42" as a number
write code plus 8
write join secret with "!" followed by " " followed by 7 as words
for each word in "the quick fox" write word in capitals
""", folder())
    screen, code, _ = run(path, [("Letter? ", "A\n")])
    assert screen == ("the word has 6 letters and starts with B\n"
                      f"Letter? A\n{GREEN}yes! a is in the word{RESET}\n_a_a_a\n"
                      "BANANA, n, a\nit starts with ban\nit does not end with x\n50\nbanana! 7\n"
                      "THE\nQUICK\nFOX\n"), repr(screen)
    screen, _, _ = run(path, [("Letter? ", "z\n")])
    assert f'{RED}no, z is not in the word{RESET}\n______\n' in screen, repr(screen)


def test_step10_your_own_words():
    """Must pass: teach greet, use it, close, open again, and greet still works."""
    here = folder()
    path = build("""
to greet someone means write hi someone in green
a turn means move left then beep
to double a number means write number times 2
greet Dominic
do a turn
double 21
""", here)
    screen, _, _ = run(path, folder=here)
    assert screen == f"{GREEN}hi Dominic{RESET}\n\x1b[1D\a42\n", repr(screen)
    assert "to greet someone means" in open(os.path.join(here, "mywords.txt")).read()
    # A brand-new run of the tool, as if it had been closed and opened again.
    with open(os.path.join(here, "again.txt"), "w") as f:
        f.write("greet Ada\nask your name\ngreet name\n")
    built = subprocess.run([sys.executable, BRICK, "build", "again.txt"], cwd=here,
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stdout
    screen, _, _ = run(os.path.join(here, "again"), [("Name? ", "Zoe\n")], here)
    assert screen == f"{GREEN}hi Ada{RESET}\nName? Zoe\n{GREEN}hi Zoe{RESET}\n", repr(screen)


def test_step10_clash_asks_first():
    asked = []
    for answer, expected in (("no", "\a"), ("yes", "boop\n")):
        here = folder()
        path = build("to beep means write boop\nbeep",
                     here, lambda question: asked.append(question) or answer)
        screen, _, _ = run(path, folder=here)
        assert screen == expected, (answer, repr(screen))
    assert asked[0] == "'beep' is already a built-in word. Replace it with yours? (yes/no) "


def test_friendly_refusals():
    from expressions import Problem
    for line, message in [
        ("wirte hello", "Did you mean 'write'?"),
        ("otherwise write no", "'otherwise' needs an 'if'"),
        ("add 1 to score", "I don't know 'score' yet"),
        ("load as best", "Load which file?"),
    ]:
        try:
            build(line, folder())
        except Problem as problem:
            assert message in str(problem), (line, str(problem))
        else:
            raise AssertionError(f"{line!r} should have been refused")


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
