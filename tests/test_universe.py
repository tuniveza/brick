"""Tests for the textual universe: loose lines brick can't read itself, said again in brick's words.

Usage: python3 tests/test_universe.py
"""
import os
import sys

from terminal import build, folder, run
from compiler import Compiler  # noqa: E402 (terminal finds brick)
from expressions import Problem  # noqa: E402

RED, TEAL, PINK, RESET = "\x1b[38;2;255;0;0m", "\x1b[38;2;0;128;128m", "\x1b[38;2;255;128;192m", "\x1b[0m"


def output(text):
    screen, code, _ = run(build(text, folder()), (), size=(6, 40))
    assert code == 0, (code, screen)
    return screen


def same_as(loose, tidy):
    """The loose line builds exactly the program its tidy telling does."""
    where = folder()
    with open(build(loose, where), "rb") as f:
        loose_program = f.read()
    with open(build(tidy, where), "rb") as f:
        assert loose_program == f.read(), (loose, tidy)


def read_as(line):
    compiler = Compiler(folder() + "/mywords.txt", ask_user=lambda question: "no")
    compiler.compile(line)
    return [note.split(" read as: ")[1] for note in compiler.notes if " read as: " in note]


def test_jumbled_lines():
    same_as("type at left of the screen the words hi in teal", "write hi in teal at left of the screen")
    same_as("can you place text at the right side of the screen in the color pink and make it say hello",
            "write hello in pink at the right side of the screen")
    same_as("put hi at left side of screen with red color", "write hi in red at left side of screen")
    same_as("left side of screen write hi in red", "write hi in red at left side of screen")
    assert output("type at left of the screen the words hi in teal") == f"\x1b[1G{TEAL}hi{RESET}\n"


def test_misread_lines_get_a_second_opinion():
    # brick built this by showing 'blue text that says ...' word for word: the universe reads it again
    BLUE = "\x1b[38;2;0;0;255m"
    line = "can you put at the top of the screen a blue text that says hi there I am a nob end"
    assert output(line) == f"\x1b[1;1H{BLUE}hi there I am a nob end{RESET}\n"
    assert read_as('write "a text that says hi"') == []           # quoted: shown just as written
    assert read_as("put text on it that says hi in the color magenta") == []        # brick reads it right


def test_text_with_a_place_after_it_is_the_word_text():
    assert output("put text at left side of screen with red color") == f"\x1b[1G{RED}text{RESET}\n"


def test_short_and_shuffled():
    same_as("hi in red", "write hi in red")
    same_as("red hi", "write hi in red")
    same_as("hi write", "write hi")
    same_as("hi x3", "write hi 3 times")
    same_as("2 secs wait", "wait 2 seconds")
    same_as("wait 2 secs then hi", "wait 2 seconds then write hi")
    same_as("after 5 secs bye", "after 5 seconds write bye")
    same_as("screen clear", "clear the screen")
    same_as("bg red", "set the background colour to red")
    same_as("red background", "set the background colour to red")
    same_as("text green", "set the colour to green")
    same_as("window left", "put the window on the left side of the screen")


def test_it_says_how_it_read_a_line():
    assert read_as("red hi") == ["write hi in red"]
    assert read_as("write hi in red") == []                  # brick reads that itself: the universe isn't asked


def test_mistakes_are_still_mistakes():
    for line, message in [
        ("wirte hello", "Did you mean 'write'?"),
        ("put x", "Put it where?"),
        ("make it disappear", "Make what disappear?"),
        ("put the window somewhere nice", "What should the window do?"),
        ('write "hello', "missing its partner"),
        ("set word to hi\nwrite the biggest in word", "Line 2"),
    ]:
        try:
            build(line, folder())
        except Problem as problem:
            assert message in str(problem), (line, str(problem))
        else:
            raise AssertionError(f"{line!r} should have been refused")


def test_synchronicity_picks_the_reading_that_fits():
    import synchronicity
    assert read_as("orange juice at the top") == ["write juice in orange at the top"]     # orange: a colour
    path = os.path.join(folder(), "memory.txt")
    memory = synchronicity.Memory(path)
    for _ in range(30):         # the factory kept seeing orange as words to show, next to a place
        memory.observe([("orange", "words", False), ("juice", "words", False), ("top", "place", True)])
    memory.save()
    os.environ["BRICK_MEMORY"] = path
    try:
        assert read_as("orange juice at the top") == ["write orange juice at the top"]
        assert read_as("hi in red") == ["write hi in red"]       # red was never seen as words: still a colour
    finally:
        os.environ["BRICK_MEMORY"] = "off"


def test_conceptnet_keeps_known_phrases_together():
    import conceptnet
    if not os.path.isfile(conceptnet.PATH):
        return                  # not fetched here (python3 conceptnet.py fetch)
    os.environ["BRICK_MEMORY"] = os.path.join(folder(), "empty.txt")      # ConceptNet's bias, nothing learned
    try:
        assert read_as("orange juice at the top") == ["write orange juice at the top"]
        assert read_as("hi in red") == ["write hi in red"]
        assert read_as("backcloth crimson") == ["set the background colour to crimson"]    # = backdrop
        assert read_as("put text at left side of screen with red color") == ['write "text" in red at left side of screen']
    finally:
        os.environ["BRICK_MEMORY"] = "off"


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
