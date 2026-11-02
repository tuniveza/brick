"""Was that what you meant? After a program runs, brick asks about the lines it had to guess.

When brick can't read a line as written, the universe guesses what it means ('bg red' -> set the
background colour to red). After the program runs, brick asks whether those guesses were right:
  yes      each guess is kept as it is, and the universe's memory learns from it
  no       a review panel (brick gui, in the browser) lists each guess with the other ways it could be
           read, and a box to say what you meant in brick's own words. In a terminal with no desktop,
           the same questions are asked right there.
Whatever you settle is kept in texts/corrections.txt (your line = what you meant), read first next time,
so that line is never guessed again, and lines like it get better too.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import webbrowser
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "texts", "corrections.txt")
HEADING = """# Your corrections: lines brick had to guess, and what you said they mean (from the review after a run).
# your line = what you meant, in brick's own words. brick reads these first, so they're never guessed again.
# You can change or remove any line here.
"""

_settled, _read_when = None, None


def settled():
    """Your line (lower case) -> what you said it means."""
    global _settled, _read_when
    when = os.path.getmtime(PATH) if os.path.isfile(PATH) else None
    if _settled is None or when != _read_when:
        _settled, _read_when = {}, when
        if when:
            with open(PATH, encoding="utf-8") as f:
                for line in f:
                    if " = " in line and not line.startswith("#"):
                        said, meant = line.rstrip("\n").split(" = ", 1)
                        _settled[said.strip().lower()] = meant.strip()
    return _settled


def keep(line, meant):
    """Remember what a line means, replacing anything said about it before."""
    found = dict(settled())
    found[line.strip().lower()] = meant.strip()
    with open(PATH + ".new", "w", encoding="utf-8") as f:
        f.write(HEADING + "".join(f"{said} = {means}\n" for said, means in found.items()))
    os.replace(PATH + ".new", PATH)


def as_you_said(text):
    """The text with every line you've said the meaning of read your way -> (text, notes)."""
    import synchronicity
    if synchronicity.off() or not settled():
        return text, []
    lines, notes = text.split("\n"), []
    for k, raw in enumerate(lines):
        meant = settled().get(raw.strip().lower())
        if meant and meant.lower() != raw.strip().lower():
            lines[k] = raw[:len(raw) - len(raw.lstrip())] + meant
            notes.append(f"Note: line {k + 1} read as: {meant} (as you said)")
    return "\n".join(lines), notes


# ---------------- what was guessed ----------------

def guessed(text, words_file="mywords.txt"):
    """The lines brick had to guess when building this text, and not yet settled ->
    [{"number", "line", "told", "others"}]: others are other readings that also build."""
    import universe
    from compiler import Compiler
    from expressions import Problem
    words = universe.trial_words(words_file)
    try:
        compiler = Compiler(words, ask_user=lambda question: "no")
        try:
            compiler.compile(text)
        except Problem:
            return []
        lines = text.split("\n")
        guesses = {int(m.group(1)): m.group(2) for m in
                   (re.match(r"Note: line (\d+) read as: (.*)$", note) for note in compiler.notes) if m}
        told_lines = [guesses.get(k + 1, line) for k, line in enumerate(lines)]     # every guess filled in
        found = []
        for number, told in guesses.items():
            line = lines[number - 1].strip()
            if line.lower() in settled():
                continue
            others, made = [], {build("\n".join(told_lines), words)}
            for way in universe.tellings(line):       # other readings, each making a different program
                program = build("\n".join(told_lines[:number - 1] + [way] + told_lines[number:]), words)
                if program and program not in made:
                    made.add(program)
                    others.append(way)
            found.append({"number": number, "line": line, "told": told, "others": others[:4]})
        return found
    finally:
        shutil.rmtree(os.path.dirname(words), ignore_errors=True)


def build(text, words):
    """The program's bytes, or None if it doesn't build."""
    from compiler import Compiler
    try:
        return Compiler(words, ask_user=lambda question: "no").compile_text(text)
    except Exception:
        return None


# ---------------- settling them ----------------

def confirm(line, told):
    """Yes, that's what it meant."""
    keep(line, told)
    learn(line, told)


def correct(text, number, meant, words_file="mywords.txt"):
    """No: it meant this. Returns None if that builds, or brick's message if it doesn't."""
    import universe
    from compiler import failing_lines
    lines = text.split("\n")
    line = lines[number - 1].strip()
    words = universe.trial_words(words_file)
    try:
        attempt = lines[:number - 1] + [meant] + lines[number:]
        if number in failing_lines("\n".join(attempt), words):
            return f"brick can't read '{meant}' either. Try it the way brick help shows."
    finally:
        shutil.rmtree(os.path.dirname(words), ignore_errors=True)
    keep(line, meant)
    learn(line, meant)
    return None


def learn(line, meant):
    """Teach the universe's memory the reading of the line that says what was meant (synchronicity)."""
    import synchronicity
    import universe
    directions = universe.analyse(line)
    if synchronicity.off() or len(directions) != 1:
        return
    for reading in universe.readings(directions[0]):
        if meant in universe.tell(reading):
            memory = synchronicity.Memory()
            memory.observe(reading.roles())
            memory.save()
            return


# ---------------- asking, after a run ----------------

def ask(source):
    """After a program ran in a terminal or its own window: were brick's guesses right?"""
    if os.environ.get("BRICK_REVIEW") == "off" or not sys.stdin.isatty() or not os.path.isfile(source):
        return
    with open(source, encoding="utf-8", errors="replace") as f:
        text = f.read()
    words = os.path.join(os.path.dirname(os.path.abspath(source)), "mywords.txt")
    found = guessed(text, words)
    if not found:                              # nothing guessed: still ask, so anything wrong can be fixed
        if yes(input("\n\nDid it do what you meant? (y/n) ")):
            return
        if desktop():
            panel(source)
            print("The fix panel is open in your browser: pick the line that went wrong.")
        else:
            fix_here(text, words)
        return
    print(f"\n\nbrick had to guess what {'this line' if len(found) == 1 else f'{len(found)} lines'} meant:")
    for g in found:
        print(f"  line {g['number']}: {g['line']}\n          read as: {g['told']}")
    if not yes(input("Did it do what you meant? (y/n) ")):
        if desktop():
            panel(source)
            print("The review panel is open in your browser.")
        else:
            here(text, found, words)
        return
    for g in found:
        confirm(g["line"], g["told"])
    print("Good: brick will read " + ("it" if len(found) == 1 else "them") + " that way from now on.")


def here(text, found, words):
    """The review panel's questions, in the terminal."""
    for g in found:
        print(f"\nline {g['number']}: {g['line']}\n    read as: {g['told']}")
        if yes(input("Is that right? (y/n) ")):
            confirm(g["line"], g["told"])
            continue
        for k, other in enumerate(g["others"], 1):
            print(f"  {k}. {other}")
        while True:
            said = input("Pick a number, or type what you meant (Enter to skip): ").strip()
            if not said:
                break
            meant = g["others"][int(said) - 1] if said.isdigit() and 0 < int(said) <= len(g["others"]) else said
            problem = correct(text, g["number"], meant, words)
            if not problem:
                print("Kept: brick will read it that way from now on.")
                break
            print(problem)


def fix_here(text, words):
    """'Not what I meant', in the terminal: which line, and what it should be."""
    lines = text.split("\n")
    for k, line in enumerate(lines, 1):
        if line.strip() and not line.strip().startswith("#"):
            print(f"  {k}: {line.strip()}")
    said = input("Which line went wrong? (its number, or Enter to skip) ").strip()
    if not said.isdigit() or not 0 < int(said) <= len(lines):
        return
    while True:
        meant = input("What did you mean, in brick's words? ").strip()
        if not meant:
            return
        problem = correct(text, int(said), meant, words)
        if not problem:
            print("Kept: brick will read it that way from now on.")
            return
        print(problem)


def yes(answer):
    return answer.strip().lower() in ("y", "yes", "yeah", "yep", "ok", "sure", "right", "")


def desktop():
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))


def panel(source):
    """Open the review panel for this program: in brick gui if it's open, or a brick gui of its own that
    closes once the review is done."""
    import gui
    with socket.socket() as s:
        open_already = s.connect_ex(("127.0.0.1", gui.PORT)) == 0
    if open_already:
        webbrowser.open(f"http://127.0.0.1:{gui.PORT}/?file={quote(os.path.abspath(source))}&review=1")
    else:
        subprocess.Popen([sys.executable, os.path.join(HERE, "brick.py"), "gui", os.path.abspath(source), "--review"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


# ---------------- a correction, made general ----------------

def generalise(line, meant, words_file="mywords.txt"):
    """'bg red' = 'set the background colour to red' -> 'bg a colour = set the background colour to a colour':
    a dictionary line that fixes lines like it, not just this one. The colour, number or words the two share
    become gaps. Kept only if it reads the line exactly as meant, and a variation too (another colour, number
    or words) -> the dictionary line, or None."""
    import dictionary
    import universe
    from actions import STARTERS
    said, means = line.strip(), meant.strip()
    swaps, pattern, meaning = [], said, means
    colours = [w for w in dict.fromkeys(re.findall(r"[a-z-]+", said.lower()))
               if w in dictionary.colour_table() or w in universe.universe().words and
               "colour" in universe.universe().words[w]]
    colours = [c for c in colours if re.search(rf"\b{c}\b", means.lower())]
    numbers = [n for n in dict.fromkeys(re.findall(r"\b\d+\b", said)) if re.search(rf"\b{n}\b", means)]
    if len(colours) == 1:
        swaps.append(("a colour", colours[0], "green" if colours[0] != "green" else "red"))
    if len(numbers) == 1:
        swaps.append(("a number", numbers[0], str(int(numbers[0]) + 1)))
    shared = shared_words(said, means)
    if shared:
        swaps.append(("something", shared, "something else entirely"))
    if not swaps:
        return None
    for gap, value, _ in swaps:
        pattern = re.sub(rf"\b{re.escape(value)}\b", gap, pattern, flags=re.IGNORECASE)
        meaning = re.sub(rf"\b{re.escape(value)}\b", gap, meaning, flags=re.IGNORECASE)
    pattern = pattern.lower().strip(" .!?")
    first = pattern.split()[0] if pattern.split() else ""
    if first in ("a", "something") or pattern == meaning.lower() or len(pattern.split()) > 12:
        return None                            # a pattern must start with a word of its own
    entry = f"{pattern} = {meaning}"
    variant_line, variant_meant = said, means
    for _, value, other in swaps:
        variant_line = re.sub(rf"\b{re.escape(value)}\b", other, variant_line, flags=re.IGNORECASE)
        variant_meant = re.sub(rf"\b{re.escape(value)}\b", other, variant_meant, flags=re.IGNORECASE)
    import factory
    builder = factory.Builder()
    with builder.trying(dictionary.PATH, entry) as trial:
        if trial.build(said, by_itself=True, words=words_file) != builder.build(means, by_itself=True, words=words_file):
            return None
        if trial.build(variant_line, by_itself=True) != builder.build(variant_meant, by_itself=True):
            return None
    return entry


def shared_words(said, means):
    """The longest run of plain words the line and its meaning share ('hello there' in 'hi there in blue
    hello there' / 'write hello there in blue'): the words to show, which a pattern leaves as a gap."""
    import universe
    world = universe.universe()
    a, b = said.lower().split(), means.lower().split()
    best = []
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i + k < len(a) and j + k < len(b) and a[i + k] == b[j + k] and not world.words.get(a[i + k]) \
                    and not a[i + k].isdigit():
                k += 1
            if k > len(best):
                best = a[i:i + k]
    return " ".join(best)

