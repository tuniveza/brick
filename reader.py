"""Reading loose English: split a line into words, and the words into actions.

A line splits at commas, full stops, colons, "then", "and" and "otherwise", but only where
the next word starts something we know (write, ask, if, ...). So "write salt and pepper"
stays whole, while "ask a name and add it to names" becomes two actions.
"""
import re

PUNCTUATION = ".,!?;:()'"


class Word:
    def __init__(self, raw):
        self.raw = raw
        quote = re.fullmatch(r'"([^"]*)"(.*)', raw)
        self.quoted = bool(quote)
        if quote:
            self.text, self.word, self.before, self.after = quote[1], None, "", quote[2]
            return
        core = raw.strip(PUNCTUATION)
        if re.fullmatch(r"-?\d[\d,]*(\.\d+)?", core.rstrip(".")):   # keep "3.5", drop a full stop after "5."
            core = core.rstrip(".")
        start = raw.find(core) if core else len(raw)
        self.before, self.after = raw[:start], raw[start + len(core):]
        self.text, self.word = core, core.lower()

    def __repr__(self):
        return self.raw


def words_of(text):
    return [Word(raw) for raw in re.findall(r'"[^"]*"\S*|\S+', text)]


def words_text(words):
    """The words put back together as they were typed."""
    return " ".join(w.raw for w in words)


class Piece:
    """One action, and how it joins the one before: 'first', 'then' (new part), 'and' (same part), 'otherwise'."""
    def __init__(self, joined_by):
        self.joined_by = joined_by
        self.words = []


def split_line(line, starts_action):
    """Split a line into pieces. starts_action(words, i) says if words[i] begins an action."""
    words = words_of(line)
    pieces = [Piece("first")]

    def begin(joined_by):
        if pieces[-1].words:
            pieces.append(Piece(joined_by))
        elif joined_by != "then":
            pieces[-1].joined_by = joined_by

    i = 0
    while i < len(words):
        w = words[i]
        if w.word in ("otherwise", "else"):
            begin("otherwise")
        elif w.word in ("then", "and") and starts_action(words, i + 1):
            begin("then" if w.word == "then" else "and")
        else:
            breaks = w.after and w.after[-1] in ",;:.!?" and not numbered(w, pieces[-1].words)
            joins = next_is(words, i + 1, "then", "otherwise", "else") or \
                next_is(words, i + 1, "and") and starts_action(words, i + 2)     # not "is 6, and the rest"
            if breaks and (starts_action(words, i + 1) or joins):
                if w.after[-1] in ",;:":
                    w = Word(w.raw[:-1])    # only there to separate; a . ! or ? stays part of the text
                pieces[-1].words.append(w)
                begin("then")
            else:
                pieces[-1].words.append(w)
        i += 1
    return [p for p in pieces if p.words or p.joined_by == "otherwise"]


def numbered(w, before):
    """'write 2. Quit' is a menu line, not 'write 2' then 'quit'."""
    return w.after == "." and w.word is not None and re.fullmatch(r"\d+", w.word) is not None and len(before) == 1 \
        and before[0].word in ("write", "say", "show", "print", "display", "output")


def next_is(words, i, *options):
    return i < len(words) and words[i].word in options


def group_parts(pieces):
    """Group pieces into parts: each part is a list of actions joined by 'and'.
    Returns a list of (is_otherwise, [action words, ...])."""
    parts = []
    for piece in pieces:
        if piece.joined_by == "and" and parts:
            parts[-1][1].append(piece.words)
        else:
            parts.append((piece.joined_by == "otherwise", [piece.words] if piece.words else []))
    return parts


NUMBER_WORDS = {w: n for n, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
NUMBER_WORDS.update({w: 20 + 10 * n for n, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())})


def read_number(words, i):
    """Read a number written in digits or in words ("three point five") from words[i].
    Returns (value, next position), or (None, i) if there isn't one."""
    if i >= len(words) or words[i].quoted:
        return None, i
    w = words[i].word
    if re.fullmatch(r"-?\d[\d,]*", w):
        return int(w.replace(",", "")), i + 1
    if re.fullmatch(r"-?\d*\.\d+", w):
        return float(w), i + 1
    total, current, j = 0, None, i
    while j < len(words) and not words[j].quoted:
        w = words[j].word.replace("-", " ")
        parts = w.split()
        if all(p in NUMBER_WORDS for p in parts) and parts:
            current = (current or 0) + sum(NUMBER_WORDS[p] for p in parts)
        elif w == "hundred" and current is not None:
            current *= 100
        elif w == "thousand" and current is not None:
            total, current = total + current * 1000, 0
        elif w == "and" and current is not None and j + 1 < len(words) and words[j + 1].word in NUMBER_WORDS:
            pass
        else:
            break
        j += 1
    if current is None and j == i and not (i < len(words) and words[i].word == "point"):
        return None, i
    value = total + (current or 0)
    if j < len(words) and words[j].word == "point":
        digits, k = "", j + 1
        while k < len(words) and not words[k].quoted and words[k].word in NUMBER_WORDS and NUMBER_WORDS[words[k].word] < 10:
            digits += str(NUMBER_WORDS[words[k].word])
            k += 1
        if digits:
            return float(f"{value}.{digits}"), k
    return value, j
