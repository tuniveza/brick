"""Messy directions: no grammar, any order, slips, chatter, run-ons. Each must build exactly the same program
as its tidy meaning. The universe reads them with ConceptNet on and an empty memory, so it's the same every
time. (Lines the scrambler found; see scrambler.py.)

Usage: python3 tests/test_messy.py
"""
import os
import sys

from terminal import folder
import conceptnet  # noqa: E402 (terminal finds brick)

MESSY = [
    # single directions, any order
    ("put text at left side of screen with red color", 'write "text" in red at left side of screen'),
    ("type at left of the screen the words hi in teal", "write hi in teal at left of the screen"),
    ("can you place text at the right side of the screen in the color pink and make it say hello",
     "write hello in pink at the right side of the screen"),
    ("can you put at the top of the screen a blue text that says hi there I am a nob end",
     "write hi there I am a nob end in blue at the top of the screen"),
    ("at top side screen put the words all done with red color", "write all done in red at the top"),
    ("show at bottom of screen nice one blue", "write nice one in blue at the bottom"),
    ("the words lets go green type at the right of the screen", "write lets go in green at the right"),
    ("text that says lets go put red x2 at the top", "write lets go in red at the top 2 times"),
    ("saying lets go at THE bottom write", "write lets go at the bottom"),
    ("in color color yellow at the bottom write see you soon 3 times", "write see you soon in yellow at the bottom 3 times"),
    ("x4 level up with red color print at the right", "write level up in red at the right 4 times"),
    ("lets go put bottom", "write lets go at the bottom"),
    ("all done with lime color", "write all done in lime"),
    ("hi in red", "write hi in red"),
    ("red hi", "write hi in red"),
    ("hi x3", "write hi 3 times"),
    ("orange juice at the top", "write orange juice at the top"),
    ("good morning in red", "write good morning in red"),
    ("write she was saying hi", "write she was saying hi"),
    ("write I live in a red house", "write I live in a red house"),
    # things and the window
    ("bg red", "set the background colour to red"),
    ("red background", "set the background colour to red"),
    ("set bg to yellow", "set the background colour to yellow"),
    ("make text navy", "set the colour to navy"),
    ("make writing green", "set the colour to green"),
    ("text colour lime", "set the colour to lime"),
    ("window left", "put the window on the left side of the screen"),
    ("left side window", "put the window on the left side of the screen"),
    ("window to right", "put the window on the right side of the screen"),
    ("screen clear", "clear the screen"),
    ("2 secs wait", "wait 2 seconds"),
    ("wait for 3 seconds", "wait 3 seconds"),
    # positions: x across, y down
    ("write hello in blue at the x 20 and y 20", "write hello in blue at row 20 column 20"),
    ("write hello in blue at x=20 y=20", "write hello in blue at row 20 column 20"),
    ("put hi at (5, 10) in red", "write hi in red at row 10 column 5"),
    ("write hi at 20,20", "write hi at row 20 column 20"),
    ("say hello at position 3 4", "write hello at row 4 column 3"),
    ("write hi at y 3", "write hi at row 3"),
    ("write what is 7 x 6?", "write what is 7 x 6?"),
    # slips
    ("put wnidow right", "put the window on the right side of the screen"),
    ("AFER 6 secs x4 saying game over say on right", "after 6 seconds write game over at the right 4 times"),
    ("1 scs wit", "wait 1 second"),
    ("make bg maenta", "set the background colour to magenta"),
    ("pirnt at bottom see you soon in lime", "write see you soon in lime at the bottom"),
    # synonyms
    ("discontinue the program", "stop the program"),
    ("state hello in red", "say hello in red"),
    ("show saying try again in the color white", "write try again in white"),
    ('PUT at left navy "lets go"', "write lets go in navy at the left"),
    ("display at the left the words you win", "write you win at the left"),
    ("display X2 see you soon left", "write see you soon at the left 2 times"),
    ("hoold hoold on 3 seconds", "wait 3 seconds"),
    ("4 tiems write text that says level up in gold colour", "write level up in gold 4 times"),
    ("text that says well done in tael tael color at the left", "write well done in teal at the left"),
    ("5 ties left put text that says good morning", "write good morning at the left 5 times"),
    ("well done say at right", "write well done at the right"),
    ("trn the bg navy", "set the background colour to navy"),
    ("tael bg", "set the background colour to teal"),
    ("make writing navvy", "set the colour to navy"),
    ("the words good morning in nay put on the top", "write good morning in navy at the top"),
    ("bg coloor cyan", "set the background colour to cyan"),
    ("saying happy days on the right wih orange color after 8 seconds display",
     "after 8 seconds write happy days in orange at the right"),
    ("IN crimson colour hi there at right side of screen pint", "write hi there in crimson at the right"),
    ('print at RIGHT side screen in gold color 3 times "ready"', "write ready in gold at the right 3 times"),
    ("right saying try again put witth navy color", "write try again in navy at the right"),
    ("window on lfet", "put the window on the left side of the screen"),
    ("saying good morning display at the left in crimson coloor", "write good morning in crimson at the left"),
    ("print saying see you soon wite on bottom", "write see you soon in white at the bottom"),
    ("put red text at the top that reads hi", "write hi in red at the top"),
    ("gold background background", "set the background colour to gold"),
    # paragraphs
    ("put window window right. also make text lime pause 1 sec;cls",
     "put the window on the right side of the screen then set the colour to lime then wait 1 second then clear the screen"),
    ("um wait for 2 secs... turn text red, then text red left side window.",
     "wait 2 seconds then set the colour to red then set the colour to red then put the window on the left side of the screen"),
    ("screen clear; 4 secs wati pls in lime color show all done at bottom.",
     "clear the screen then wait 4 seconds then write all done in lime at the bottom"),
    ("pls put window window left, make the wrtiing gold!",
     "put the window on the left side of the screen then set the colour to gold"),
    ("paint background cyan text crimson and then turn text white...",
     "set the background colour to cyan then set the colour to crimson then set the colour to white"),
    ("window left then hey righht side window ; right SIDE window  window on left pls",
     "put the window on the left side of the screen then put the window on the right side of the screen then "
     "put the window on the right side of the screen then put the window on the left side of the screen"),
    ("hold on 1 sec then window right  make text white white...",
     "wait 1 second then put the window on the right side of the screen then set the colour to white"),
    ("text color yellow  turn text white yeah and then also clear screen, then paint the bg TEAL.",
     "set the colour to yellow then set the colour to white then clear the screen then set the background colour to teal"),
    ('now wait 5 secs level up IN teal color put in YELLOW type "welcome back" ; MAKE writing crimson!',
     "wait 5 seconds then write level up in teal then write welcome back in yellow then set the colour to crimson"),
    ('turn text gold;now set background to crimson;"all done" say in cyan colour to left  background orange!',
     "set the colour to gold then set the background colour to crimson then write all done in cyan at the left "
     "then set the background colour to orange"),
    ("can you make bg cyan, then text color green ok and then window left",
     "set the background colour to cyan then set the colour to green then put the window on the left side of the screen"),
    ("window on on the the right. blue text that says level up say  also text colour gold",
     "put the window on the right side of the screen then write level up in blue then set the colour to gold"),
    ("turn text yellow. also sleep 1 sec;clear screen!", "set the colour to yellow then wait 1 second then clear the screen"),
    ("window to right  hi there write to right in red",
     "put the window on the right side of the screen then write hi there in red at the right"),
    ("at top the screen in yellow color text that says good morning then wait for 3 seconds lol",
     "write good morning in yellow at the top then wait 3 seconds"),
    ("just in TEAL right of screen text that says welcome back real quick pause 2 seconds??",
     "write welcome back in teal at the right then wait 2 seconds"),
    ("wipe screen... can you top in pink colour put put the words nice one",
     "clear the screen then write nice one in pink at the top"),
]


def built(text, where, by_itself=False):
    from compiler import Compiler
    compiler = Compiler(os.path.join(where, "mywords.txt"), ask_user=lambda question: "no")
    try:
        return compiler.compile_text(text) if by_itself else compiler.compile(text)
    except Exception:
        return None


def test_messy_directions():
    if not os.path.isfile(conceptnet.PATH):
        return                  # ConceptNet isn't here (python3 conceptnet.py fetch)
    where = folder()
    os.environ["BRICK_MEMORY"] = os.path.join(where, "empty-memory.txt")
    os.environ["BRICK_NEURAL"] = "off"          # the universe's own rules (the model has tests/test_neural.py)
    try:
        wrong = []
        for messy, tidy in MESSY:
            want = built(tidy, where, by_itself=True)
            assert want is not None, f"the tidy meaning doesn't build: {tidy}"
            if built(messy, where) != want:
                wrong.append(messy)
        assert not wrong, f"{len(wrong)} of {len(MESSY)} read wrong: {wrong}"
    finally:
        os.environ["BRICK_MEMORY"] = "off"
        os.environ.pop("BRICK_NEURAL", None)


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
