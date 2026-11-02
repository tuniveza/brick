"""The neural reader: lines with ideas brick was never taught, read with the language model on this computer.
Skipped when Ollama or the model isn't here. A model's wording can vary a little between versions, so most
(not all) must come out right: each must build exactly the program its meaning builds.

Usage: python3 tests/test_neural.py
"""
import os
import sys

from terminal import folder
import neural  # noqa: E402 (terminal finds brick)

NEW_IDEAS = [
    ("make the computer go ding", "beep"),
    ("splash the whole screen purple", "set the background colour to purple"),
    ("paint everything black", "set the background colour to black"),
    ("wipe everything off and say hi", "clear the screen then write hi"),
    ("wait half a minute then say done", "wait 30 seconds then write done"),
    ("type hi but in green please", "write hi in green"),
    ("colour the backdrop navy", "set the background colour to navy"),
    ("write hello in blue at the x 20 and y 20", "write hello in blue at row 20 column 20"),
    ("show the word ready in the very middle of the screen", "write ready in the middle"),
    ("say hello three times in red", "write hello 3 times in red"),
]


def built(text, where, by_itself=False):
    from compiler import Compiler
    compiler = Compiler(os.path.join(where, "mywords.txt"), ask_user=lambda question: "no")
    try:
        return compiler.compile_text(text) if by_itself else compiler.compile(text)
    except Exception:
        return None


def test_new_ideas():
    where = folder()
    os.environ["BRICK_MEMORY"] = os.path.join(where, "empty-memory.txt")
    os.environ.pop("BRICK_NEURAL", None)
    try:
        if neural.off() or not neural.ready():
            return              # no Ollama or no model here (brick neural setup)
        wrong = [line for line, meant in NEW_IDEAS if built(line, where) != built(meant, where, by_itself=True)]
        assert len(wrong) <= 2, f"{len(wrong)} of {len(NEW_IDEAS)} read wrong: {wrong}"
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
