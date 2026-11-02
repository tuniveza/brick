"""The dictionary: everyday English words, each taken to the nearest thing brick already understands.

dictionary.txt holds one word or phrase per line, like 'scribble = write', grouped under # headings.
A word only counts where its meaning fits, so 'write I scribbled a crimson note' shows exactly those words.
What kind of word it is comes from its meaning:
  an action   (write, ask, wait ...)       the first word of an action: 'scribble hello' -> write hello
  a colour    (#dc143c, a paint code)      where a colour goes: 'in crimson', 'set the colour to navy'
  a check     (is more than, contains ...) after the thing being checked: 'if score exceeds 10'
  a time      (3600 seconds)               in a wait: 'wait 2 hours', 'wait a while'
  a place     (top left, up ...)           on the screen: 'write hi at the top-left', 'move upwards'
  a list      (list)                       what's being made: 'make an inventory called items'
  a loop      (forever, 3 times, until)    how often: 'beep over and over', 'write hi thrice'
  a value     (anything else)              inside a value: 'the greatest of a and b', 'score doubled'
Gaps: 'something', 'something else' and 'a number' stand for any words; 'a colour' for a colour.
The words you teach brick, and the names in your program, always come first.
"""
import os
import textwrap

from reader import Word

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texts", "dictionary.txt")
GAPS = ("something else", "something", "a number", "a colour")
TIME_UNITS = {"seconds": 1, "second": 1, "minutes": 60, "minute": 60, "milliseconds": 0.001, "millisecond": 0.001}
PLACES = {"top", "bottom", "left", "right", "middle", "centre", "center", "up", "down", "forward", "back",
          "row", "column", "line"}
THINGS = "need the word colour"       # in a heading: colours that are also everyday things (salmon, peru)


class Entry:
    def __init__(self, key, meaning, group, needs_colour_word):
        self.key, self.meaning, self.group = key, meaning, group
        self.pattern = pattern_of(key)
        self.literals = sum(kind == "word" for kind, _ in self.pattern)
        self.needs_colour_word = needs_colour_word
        meaning = pattern_of(meaning)
        self.complete = len(meaning) > 1 and all(kind == "word" for kind, _ in self.pattern + meaning)
        self.kind = None                # worked out once brick's own words are known: see kind_of


def pattern_of(phrase):
    """'turn something into something else' -> [('word', 'turn'), ('gap', 'something'), ('word', 'into'), ...]."""
    words, pattern, i = phrase.lower().split(), [], 0
    while i < len(words):
        gap = next((g for g in GAPS if words[i:i + len(g.split())] == g.split()), None)
        pattern.append(("gap", gap) if gap else ("word", words[i]))
        i += len(gap.split()) if gap else 1
    return pattern


_entries = None


def entries():
    """Every entry in dictionary.txt, in order, each with its kind."""
    global _entries
    if _entries is None:
        _entries = read(PATH)
    return _entries


def read(path):
    """The entries in a dictionary file. The first # line after a blank line or an entry is a heading;
    the # lines straight after it are notes."""
    found, group, needs, after_entry = [], "", False, True
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                after_entry = True
            elif line.startswith("#"):
                if after_entry:
                    group, needs = line.lstrip("# ").strip(), False
                needs = needs or THINGS in line.lower()
                after_entry = False
            elif "=" in line:
                key, meaning = (part.strip() for part in line.split("=", 1))
                if key and meaning:
                    found.append(Entry(key.lower(), meaning, group, needs))
                after_entry = True
    colours = {e.key for e in found if e.meaning.startswith("#")}
    for entry in found:
        entry.kind = kind_of(entry, colours)
    return found


def kind_of(entry, colours):
    """What kind of word an entry is, from its meaning (see the top of this file).
    colours: the names of the colours in the file, which other colours can be said to mean."""
    from actions import COLOURS, STARTERS         # here, not at the top: actions uses this file
    from expressions import Parser
    meaning = entry.meaning.lower().split()
    if entry.meaning.startswith("#") or entry.meaning.lower() in colours | set(COLOURS):
        return "colour"
    if meaning in (["forever"], ["until"], ["while"], ["times"]) or \
            len(meaning) == 2 and meaning[0].isdigit() and meaning[1] in ("times", "time"):     # thrice = 3 times
        return "loop"
    if all(w in PLACES for w in meaning):         # before actions: "centre" is a place here, not the window word
        return "place"
    if meaning[0] in STARTERS:
        return "action"
    said = " ".join(meaning)
    if any(said == p or said.startswith(p + " ") for _, phrases in Parser.COMPARISONS for p in phrases if p[0].isalpha()):
        return "check"
    if meaning[-1] in TIME_UNITS:
        return "time"
    if meaning == ["list"]:
        return "list"
    return "value"


def of_kind(*kinds):
    return [e for e in entries() if e.kind in kinds]


# ---------------- finding words ----------------

def match(pattern, words, start, fits=None, whole=False, complete=False):
    """Do the words from start begin with this pattern? -> (where it ends, {gap: words}), or None.
    A gap in the middle takes as few words as it can; one at the end takes as many as fit.
    fits(gap, words): may these words fill this gap? ('a colour' must be a colour).
    whole: it must take all the words; complete: all the words of one action (up to a comma, 'and' or 'then')."""
    def go(p, i, filled):
        if p == len(pattern):
            if whole and i < len(words) or complete and not ends_action(words, i):
                return None
            return i, filled
        kind, part = pattern[p]
        if kind == "word":
            return go(p + 1, i + 1, filled) if i < len(words) and words[i].word == part else None
        ends = range(len(words), i, -1) if p == len(pattern) - 1 else range(i + 1, len(words) + 1)
        for end in ends:
            if part == "a colour" and (end - i > 4 or not (fits and fits(part, words[i:end]))):
                continue
            found = go(p + 1, end, {**filled, part: words[i:end]})
            if found:
                return found
        return None
    return go(0, start, {})


def ends_action(words, i):
    return i == len(words) or words[i - 1].after[-1:] in tuple(",;:.!?") or \
        words[i].word in ("and", "then", "otherwise", "else")


def respell(words, kinds, start=0, fits=None, whole=False):
    """If a dictionary word of one of these kinds starts at words[start], the words with it put in
    its meaning: 'scribble hi' -> 'write hi'. The meaning's words are marked, so they aren't looked up
    again. Returns (new words, the entry), or None.
    An action whose meaning is a few words with no gap ('skip a line' = write a blank line) must be the whole
    action, so 'add a blank line to notes.txt' still adds those words to the file."""
    kinds = (kinds,) if isinstance(kinds, str) else kinds
    if start >= len(words) or words[start].word is None or getattr(words[start], "meant", False):
        return None
    for entry in by_first_word().get(words[start].word, ()):
        if entry.kind not in kinds:
            continue
        found = match(entry.pattern, words, start, fits, whole, entry.complete and entry.kind == "action")
        if found:
            end, filled = found
            return words[:start] + meaning_words(entry, filled) + words[end:], entry
    return None


def meaning_words(entry, filled):
    out = []
    for kind, part in pattern_of(entry.meaning):
        if kind == "gap" and part in filled:
            out += filled[part]
        else:
            word = Word(part)
            word.meant = True
            out.append(word)
    return out


def respell_all(words, kinds):
    """Every dictionary word of these kinds, anywhere in the words, put in its meaning (no gaps)."""
    i = 0
    while i < len(words):
        found = respell(words, kinds, i)
        words = found[0] if found else words        # its meaning's words are marked, so they're passed over
        i += 1
    return words


_first = None


def by_first_word():
    """Each first word -> its entries, the most particular first ('turn the text a colour' before 'turn a colour')."""
    global _first
    if _first is None:
        _first = {}
        for entry in entries():
            if entry.pattern[0][0] == "word":
                _first.setdefault(entry.pattern[0][1], []).append(entry)
        for found in _first.values():
            found.sort(key=lambda e: -e.literals)
    return _first


def first_words(*kinds):
    return {e.pattern[0][1] for e in entries() if e.kind in kinds and e.pattern[0][0] == "word"}


def ending(words, kinds):
    """A dictionary word of these kinds that the words end with -> (how many words it covers, its meaning words)."""
    for n in range(min(5, len(words)), 0, -1):
        found = respell(words[-n:], kinds, whole=True)
        if found:
            return n, found[0]
    return None


# ---------------- colours ----------------

def colour_at(said, j, named=True):
    """A dictionary colour starting at said[j] (lower-case words; None for a quoted word or the end)
    -> (terminal code, how many words), or None. Two-word names can also be written as one ('seagreen').
    named: a colour word is nearby ('in the colour salmon'), so colours that are also things count too."""
    table = colour_table()
    for n in range(4, 0, -1):
        phrase = said[j:j + n]
        if len(phrase) == n and None not in phrase and " ".join(phrase) in table:
            code, thing = table[" ".join(phrase)]
            if named or not thing:
                return code, n
    return None


_colours = None


def colour_table():
    """'sea green' (and 'seagreen') -> ('38;2;46;139;87', is it also an everyday thing?)."""
    global _colours
    if _colours is None:
        from actions import COLOURS, paint_code
        _colours = {}
        for entry in of_kind("colour"):
            if entry.meaning.startswith("#"):
                code = paint_code(entry.meaning)
            else:
                known = COLOURS.get(entry.meaning.lower()) or _colours.get(entry.meaning.lower(), (None,))[0]
                if known is None:
                    continue
                code = known
            for phrase in {entry.key, entry.key.replace(" ", "")}:
                _colours.setdefault(phrase, (code, entry.needs_colour_word))
    return _colours


# ---------------- for brick help ----------------

def examples_for(word):
    """Ways to use a dictionary word, for a message: 'turn green', 'turn left' ..."""
    fill = {"something": "score", "something else": "words", "a number": "3", "a colour": "green"}
    shown = []
    for entry in sorted(by_first_word().get(word, ()), key=lambda e: e.literals):
        said = " ".join(part if kind == "word" else fill[part] for kind, part in entry.pattern)
        if said not in shown:
            shown.append(said)
    return shown


def listing(only=None):
    """The whole dictionary, grouped as in dictionary.txt: each meaning, then the words that mean it.
    only: a word from a heading, to show just those groups ('colours')."""
    groups = {}
    for entry in entries():
        groups.setdefault(entry.group, []).append(entry)
    lines = [f"brick's dictionary: {len(entries())} everyday words, each taken to its nearest meaning here.",
             f"They're in {PATH} (you can add your own there).",
             "Words you teach brick, and names in your program, always come first."]
    for group, items in groups.items():
        if only and not any(word.lower() in group.lower() for word in only):
            continue
        lines += ["", group]
        if items[0].needs_colour_word:
            lines.append("    (these need the word colour nearby: in salmon colour, set the colour to salmon)")
        if items[0].kind == "colour":
            lines += textwrap.wrap(", ".join(e.key for e in items), 100, initial_indent="    ",
                                   subsequent_indent="    ")
            continue
        meanings = {}
        for e in items:
            meanings.setdefault(e.meaning, []).append(e.key)
        for meaning, keys in meanings.items():
            lines += textwrap.wrap(f"{meaning}: " + ", ".join(keys), 100, initial_indent="    ",
                                   subsequent_indent="        ")
    if only and len(lines) == 3:
        lines.append(f"\nNo group called {' '.join(only)}. The groups are: " + ", ".join(groups))
    return "\n".join(lines)


def clear():
    """Forget what was read, so the next look reads dictionary.txt again (for tests)."""
    global _entries, _first, _colours
    _entries = _first = _colours = None
