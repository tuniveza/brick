"""The scrambler: broken, errored paragraphs of directions, each with a known right answer.

It writes directions the way people really type when they don't care: any order, no grammar, no
punctuation or the wrong punctuation, semicolons, run-ons, missing verbs, short forms, chatter
('ok so', 'lol'), random capitals, doubled words, and now and then a typo. Each paragraph is made from
tidy directions brick reads perfectly, so the scrambler knows exactly which program the mess should make:

  'ok so TOP of screen hello there in red;bg blue   then 2 secs wait lol'
  should make the same program as:
  'write hello there in red at the top then set the background colour to blue then wait 2 seconds'

The factory runs it every round and learns from what brick gets wrong (see factory.py).
    python3 scrambler.py 10        show 10 scrambled paragraphs, and how brick did with each
"""
import os
import random
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

WORDS = ["hello", "hi there", "game over", "well done", "you win", "good morning", "nice one", "try again",
         "welcome back", "see you soon", "happy days", "level up", "ready", "lets go", "all done"]
COLOURS = ["red", "green", "blue", "yellow", "orange", "pink", "purple", "cyan", "white", "crimson", "teal",
           "gold", "navy", "lime", "magenta"]
SIDES = ["left", "right", "top", "bottom"]
SHORT = {"seconds": "secs", "second": "sec", "background": "bg", "colour": "color", "please": "pls",
         "you": "u", "and": "&", "screen": "screen", "window": "window"}
CHATTER_BEFORE = ["ok so", "um", "can you", "pls", "just", "right", "so yeah", "hey", "now", "and", "also"]
CHATTER_AFTER = ["lol", "pls", "thx", "ok", "real quick", "rn", "yeah", "thanks", "!!", "..."]
JOINS = [" ; ", "; ", ";", " then ", ", then ", " and then ", ". ", " ", "... ", " - ", ", ", " then ", "  ", " & then "]


class Part:
    """One direction: how brick says it, and the parts it's made of."""

    def __init__(self, tidy, pieces, keep=()):
        self.tidy = tidy              # brick's own words: this builds the right program
        self.pieces = pieces          # the parts, each a list of ways to say it ('' = leave it out)
        self.keep = set(keep)         # which parts are the words to show: never scrambled


def show():
    words, colour, side = random.choice(WORDS), random.choice(COLOURS + [None, None]), random.choice(SIDES + [None])
    later, count = random.choice([None, None, None, random.randint(2, 9)]), random.choice([None, None, None, random.randint(2, 5)])
    tidy = (f"after {later} seconds " if later else "") + f"write {words}" + (f" in {colour}" if colour else "") + \
        (f" at the {side}" if side else "") + (f" {count} times" if count else "")
    pieces = {"verb": ["write", "say", "show", "print", "display", "type", "put", ""] if (colour or side or later or count)
              else ["write", "say", "show", "print", "display", "type"],
              "words": [words, f"text that says {words}", f"the words {words}", f"saying {words}", f'"{words}"']}
    if colour:
        pieces["colour"] = [f"in {colour}", colour, f"with {colour} color", f"in the color {colour}", f"in {colour} colour"]
    if side:
        pieces["place"] = [f"at the {side}", side, f"at the {side} of the screen", f"{side} of screen", f"to the {side}",
                           f"at {side} side of screen", f"on the {side}"]
    if count:
        pieces["count"] = [f"{count} times", f"x{count}"]
    if later:
        pieces["later"] = [f"after {later} seconds", f"after {later} secs", f"after {later} sec"]
    return Part(tidy, pieces, keep=["words"])


def background():
    c = random.choice(COLOURS)
    return Part(f"set the background colour to {c}", {"all": [f"bg {c}", f"background {c}", f"{c} background",
                f"make the bg {c}", f"turn the background {c}", f"set background to {c}", f"paint the background {c}",
                f"background colour {c}", f"make background {c}"]})


def window():
    side = random.choice(["left", "right"])
    return Part(f"put the window on the {side} side of the screen", {"all": [f"window {side}", f"put window {side}",
                f"window to the {side}", f"move the window to the {side} side", f"put the window at {side} side of screen",
                f"{side} side window", f"window on the {side}"]})


def clear():
    return Part("clear the screen", {"all": ["clear", "clear screen", "screen clear", "wipe the screen", "cls",
                                             "clear the screen", "wipe screen"]})


def wait():
    n = random.randint(1, 5)
    unit = "second" if n == 1 else "seconds"
    return Part(f"wait {n} {unit}", {"all": [f"wait {n} secs", f"{n} secs wait", f"pause {n} {unit}", f"wait {n} s",
                f"wait for {n} {unit}", f"hold on {n} {unit}", f"sleep {n} {unit}"]})


def text_colour():
    c = random.choice(COLOURS)
    return Part(f"set the colour to {c}", {"all": [f"text {c}", f"make text {c}", f"turn the text {c}",
                                                    f"text colour {c}", f"make the writing {c}"]})


MAKERS = [show, show, show, show, background, window, clear, wait, text_colour]


# ---------------- scrambling ----------------

def say(part):
    """One messy way to say a direction: its parts in any order, each said any way."""
    chosen = {name: random.choice(ways) for name, ways in part.pieces.items()}
    names = list(chosen)
    random.shuffle(names)
    words = []
    for name in names:
        if not chosen[name]:
            continue
        said = chosen[name] if name in part.keep else mess(chosen[name])
        words.append(said)
    return " ".join(words)


def mess(text):
    """Small damage to words that aren't the words to show."""
    out = []
    for word in text.split():
        low = word.lower()
        if low in ("the", "a", "of") and random.random() < 0.5:
            continue                                     # no small words
        if low in SHORT and random.random() < 0.4:
            word = SHORT[low]
        if random.random() < 0.04:
            word = typo(word)
        if random.random() < 0.03:
            out.append(word)                             # 'write write'
        out.append(word.upper() if random.random() < 0.06 else word)
    return " ".join(out)


def typo(word):
    if len(word) < 4 or not word.isalpha():
        return word
    k = random.randrange(1, len(word) - 1)
    return random.choice([word[:k] + word[k + 1] + word[k] + word[k + 2:],      # swapped letters
                          word[:k] + word[k + 1:],                              # a letter missing
                          word[:k] + word[k] + word[k:]])                       # a letter twice


def paragraph(size=None):
    """A broken paragraph -> (the mess, its directions as typed, the tidy directions)."""
    parts = [random.choice(MAKERS)() for _ in range(size or random.randint(2, 4))]
    said = [say(p) for p in parts]
    mess_text = ""
    for k, s in enumerate(said):
        if random.random() < 0.25:
            s = f"{random.choice(CHATTER_BEFORE)} {s}"
        if random.random() < 0.15:
            s = f"{s} {random.choice(CHATTER_AFTER)}"
        mess_text += (random.choice(JOINS) if k else "") + s
    if random.random() < 0.3:
        mess_text = mess_text.lower()
    mess_text += random.choice(["", "", ".", "!", "...", " lol", "??"])
    return mess_text, said, [p.tidy for p in parts]


# ---------------- how did brick do? ----------------

class Checker:
    def __init__(self):
        self.folder = tempfile.mkdtemp(prefix="brick-scrambler-")

    def build(self, text, by_itself=False):
        from compiler import Compiler
        words = os.path.join(self.folder, "mywords.txt")
        try:
            compiler = Compiler(words, ask_user=lambda question: "no")
            return compiler.compile_text(text) if by_itself else compiler.compile(text)
        except Exception:
            return None
        finally:
            if os.path.exists(words):
                os.remove(words)

    def check(self, mess_text, said, tidy):
        """-> ("right" | "wrong" | "refused" | None if the tidy version doesn't build, [(messy, tidy, how)])."""
        want = self.build(" then ".join(tidy), by_itself=True)
        if want is None:
            return None, []
        got = self.build(mess_text)
        how = "right" if got == want else "refused" if got is None else "wrong"
        missed = []
        if how != "right":                                # which directions did it trip on?
            for messy, meant in zip(said, tidy):
                alone = self.build(messy)
                if alone != self.build(meant, by_itself=True):
                    missed.append((messy, meant, "refused" if alone is None else "wrong"))
        return how, missed

    def done(self):
        shutil.rmtree(self.folder, ignore_errors=True)


def findings(count=40):
    """brick director, brick's own half: scramble a batch, and say in plain English what brick gets wrong."""
    checker, tally, misses = Checker(), {"right": 0, "wrong": 0, "refused": 0}, {}
    for _ in range(count):
        mess_text, said, tidy = paragraph()
        how, missed = checker.check(mess_text, said, tidy)
        if how is None:
            continue
        tally[how] += 1
        for messy, meant, what in missed:
            kind = meant.split(" in ")[0].split(" at ")[0] if meant.startswith("write") else \
                re.sub(r"\b(\d+|" + "|".join(COLOURS + SIDES) + r")\b", "...", meant)
            misses.setdefault((what, "write ..." if meant.startswith(("write", "after")) else kind), []).append((messy, meant))
    checker.done()
    total = sum(tally.values())
    lines = [f"The English Director (brick's own): {total} scrambled paragraphs, each with a known right answer.",
             f"brick read {tally['right']} right, misread {tally['wrong']}, and refused {tally['refused']}.", ""]
    for (what, kind), found in sorted(misses.items(), key=lambda item: -len(item[1])):
        lines.append(f"{'Misread' if what == 'wrong' else 'Refused'} {len(found)} time{'s' if len(found) > 1 else ''}: "
                     f"directions meaning '{kind}'. For example:")
        lines += [f"    '{messy}'  should mean: {meant}" for messy, meant in found[:3]]
    import outliers
    waiting, handed = len(outliers.entries()), len(outliers.entries(outliers.FOR_DIRECTOR))
    if waiting or handed:
        lines += ["", f"Waiting for a person (the Decisions tab in brick gui): {waiting}. "
                      f"Left for the English Director: {handed} (texts/factory/for-director.txt)."]
    return "\n".join(lines)


def main(args):
    count = int(args[0]) if args else 10
    checker, tally = Checker(), {"right": 0, "wrong": 0, "refused": 0}
    for _ in range(count):
        mess_text, said, tidy = paragraph()
        how, missed = checker.check(mess_text, said, tidy)
        if how is None:
            continue
        tally[how] += 1
        print(f"{'✓' if how == 'right' else '✗'} {mess_text}")
        if how != "right":
            print(f"    meant: {' then '.join(tidy)}")
            for messy, meant, what in missed:
                print(f"    {what}: '{messy}'  (meant: {meant})")
    checker.done()
    total = sum(tally.values())
    print(f"\nbrick read {tally['right']} of {total} right; {tally['wrong']} misread, {tally['refused']} refused.")


if __name__ == "__main__":
    main(sys.argv[1:])
