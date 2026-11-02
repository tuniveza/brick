"""Reading values out of loose English ("length of word plus 1", "a random number from 1 to 5"),
then turning them into machine code. A value always ends up in rax.

Kinds of value:
  number    whole number
  decimal   number with a point, shown to 2 places
  quotient  the result of a divide: shown whole if it divided evenly, else to 2 places
  text, timer (a stopwatch start), yes/no, and "list of <kind>"
"""
import difflib
import re

import dictionary
from asm import ABOVE, BELOW, EQUAL, GREATER, LESS, NOT_EQUAL, NOT_LESS, RAX, RCX, RDX, R8, XMM0, XMM1
from reader import Word, read_number
from runtime import LIST_SIZE


class Problem(Exception):
    """Something in the English we can't turn into a program. The message says what to do."""


DECIMALS = ("decimal", "quotient")
FILE_NAME = r"[\w .-]*[\w-]\.[A-Za-z]\w*"     # best.txt, "my scores.txt"


# ---------------- reading ----------------

ORDINALS = {word: n for n, word in enumerate("second third fourth fifth sixth seventh eighth ninth tenth".split(), 2)}
ORDINALS.update({f"{n}{'st' if n % 10 == 1 and n != 11 else 'nd' if n % 10 == 2 and n != 12 else 'rd' if n % 10 == 3 and n != 13 else 'th'}": n
                 for n in range(1, 21)})


def ordinal_atoms():
    """'the second', '2nd', 'the 3rd' ... -> read what's after them as item, letter or word number n."""
    return [([f"the {word}", word], lambda p, n=n: p.nth(("number", n))) for word, n in ORDINALS.items()]



def both_ways(words, after=""):
    """'biggest largest' -> 'the biggest', 'biggest', 'the largest', ... each followed by a word in after, if any."""
    ends = [" " + word for word in after.split()] or [""]
    return [f"{the}{word}{end}" for word in words.split() for the in ("the ", "") for end in ends]


class Parser:
    def __init__(self, words, names):
        self.words = words
        self.at = 0
        self.names = names     # a function: name -> its kind, or None if it doesn't exist

    # helpers

    def done(self):
        return self.at >= len(self.words)

    def peek(self, offset=0):
        i = self.at + offset
        return self.words[i].word if i < len(self.words) else None

    def take(self, *phrases):
        """If the next words are one of the phrases, step past them and return True."""
        for phrase in phrases:
            parts = phrase.split()
            if all(self.peek(n) == p for n, p in enumerate(parts)):
                self.at += len(parts)
                return True
        return False

    def need(self, *phrases):
        if not self.take(*phrases):
            got = self.peek() or "the end"
            raise Problem(f"I expected '{phrases[0]}' but found '{got}'.")

    def kind_of(self, word):
        return self.names(word) if word else None

    def respell(self, kind):
        """A dictionary word of this kind just here ('greatest', 'exceeds', 'doubled') -> its meaning, put in
        place of it. A name in the program comes first. Returns True if there was one."""
        starts = (self.at, self.at + 1) if kind == "value" and self.peek() == "the" else (self.at,)
        for at in starts:
            if self.kind_of(self.peek(at - self.at)) or self.long_name(at - self.at):
                return False
            found = dictionary.respell(self.words, kind, start=at)
            if found:
                self.words = found[0]
                return True
        return False

    # conditions

    def condition(self):
        left = self.condition_and()
        while self.take("or"):
            left = ("or", left, self.shared(left, self.condition_and))
        return left

    def condition_and(self):
        left = self.condition_not()
        while self.take("and"):
            left = ("and", left, self.shared(left, self.condition_not))
        return left

    def shared(self, left, read):
        """After 'and' / 'or' a check can leave out what it's about:
        'guess is 7 or 8', 'age is over 12 and under 20', 'answer is yes or y'."""
        last = left
        while last[0] in ("and", "or"):
            last = last[2]
        if last[0] != "compare" or last[1] == "empty":
            return read()
        self.respell("check")                           # "score exceeds 5 and falls below 10"
        for name, phrases in self.COMPARISONS:          # "is 1 or more than 5", "is 1 or is more than 5"
            short = [p[3:] for p in phrases if p.startswith("is ") and not p.startswith("is not")]
            if name != "empty" and (short and self.take(*short) or self.take(*phrases)):
                return ("compare", name, last[2], self.right_side())
        start = self.at
        if self.take("not"):                            # "x is not 1 and not 2"
            value = self.right_side()
            if self.done() or self.peek() in ("and", "or"):
                return ("compare", "!=", last[2], value)
            self.at = start
        try:
            right = read()
        except Problem:
            self.at = start
            return ("compare", last[1], last[2], self.right_side())
        if right[0] == "truth" and not (right[1][0] == "name" and self.kind_of(right[1][1]) == "yes/no"):
            return ("compare", last[1], last[2], right[1])
        return right

    def condition_not(self):
        if self.take("not"):
            return ("not", self.condition_not())
        return self.comparison()

    COMPARISONS = [
        ("not in", ["is not in", "isn't in", "is not one of"]),
        ("in", ["is in", "is inside", "is one of", "is part of"]),
        ("not contains", ["does not contain", "doesn't contain", "does not have", "doesn't have",
                          "do not contain", "don't contain"]),
        ("contains", ["contains", "has", "includes", "contain", "include"]),
        ("starts", ["starts with", "begins with"]),
        ("ends", ["ends with"]),
        (">=", ["is at least", "is more than or equal to", "is greater than or equal to",
                "is bigger than or equal to", "is not less than", ">="]),
        ("<=", ["is at most", "is less than or equal to", "is smaller than or equal to",
                "is not more than", "<="]),
        (">", ["is more than", "is greater than", "is bigger than", "is higher than", "is over",
               "is above", "is larger than", "is longer than", ">"]),
        ("<", ["is less than", "is smaller than", "is lower than", "is under", "is below",
               "is shorter than", "<"]),
        ("empty", ["is empty"]),
        ("!=", ["is not equal to", "is not the same as", "is not", "isn't", "!="]),
        ("=", ["is equal to", "is the same as", "equals", "is", "=", "=="]),
    ]

    def file_check(self):
        """'shopping.txt exists', "the file notes.txt doesn't exist" -> a check; else None."""
        start = self.at
        self.take("the file called", "the file named", "the file", "a file called", "file")
        w = self.words[self.at] if not self.done() else None
        if w is not None and re.fullmatch(FILE_NAME, w.text):
            self.at += 1
            if self.take("exists", "is there", "exist"):
                return ("file exists", w.text)
            if self.take("doesn't exist", "does not exist", "isn't there", "is not there"):
                return ("not", ("file exists", w.text))
        self.at = start
        return None

    def comparison(self):
        found = self.file_check()
        if found:
            return found
        left = self.expression()
        if self.peek() in ("are", "aren't"):            # "lives are more than 0" reads like "is"
            plain = "is" if self.peek() == "are" else "isn't"
            self.words = self.words[:self.at] + [Word(plain)] + self.words[self.at + 1:]
        self.respell("check")                           # "if score exceeds 10"
        for name, phrases in self.COMPARISONS:
            if self.take(*phrases):
                if name == "empty":
                    return ("compare", "empty", left, None)
                if name in ("contains", "not contains", "starts", "ends"):
                    return ("compare", name, left, self.contained())
                return ("compare", name, left, self.right_side())
        return ("truth", left)

    def contained(self):
        """What 'contains' looks for: 'the letter a', 'an a in it', '"nan"'."""
        self.take("the letter", "the letters", "the word", "the words")
        if self.peek() in ("a", "an") and len(self.peek(1) or "") == 1:
            self.at += 1                                # "has an a in it"
        tail = [w.word for w in self.words[-2:]]
        if tail in (["in", "it"], ["inside", "it"], ["in", "them"]) and len(self.words) - self.at > 2:
            self.words = self.words[:-2]
        return self.right_side()

    def right_side(self):
        """What a check compares with. Unknown words are plain text: 'if answer is yes'."""
        start = self.at
        try:
            return self.expression()
        except Problem:
            self.at = start
        words = []
        while not self.done() and self.peek() not in ("and", "or"):
            words.append(self.words[self.at].text)
            self.at += 1
        if not words:
            raise Problem("Compare it with what? Like: if answer is yes")
        if len(words) > 1 and words[1].lower() in self.MISSPELT:     # "if 3 is mroe than 2"
            close = difflib.get_close_matches(words[0].lower(), self.MISSPELT[words[1].lower()], n=1, cutoff=0.7)
            if close:
                raise Problem(f"I don't understand '{words[0]} {words[1]}'. Did you mean '{close[0]} {words[1]}'?")
        return ("text", " ".join(words))

    MISSPELT = {"than": ["more", "less", "greater", "bigger", "smaller", "higher", "lower", "larger",
                         "longer", "shorter"],
                "to": ["equal"]}

    # values

    def expression(self):
        left = self.rounded(self.sum())
        while self.take("followed by", "together with", "joined to"):
            left = ("join", left, self.rounded(self.sum()))
        return left

    def rounded(self, value):
        """'7 divided by 2 rounded' rounds the whole sum before it."""
        if self.take("rounded up"):
            return ("round", 2, value)
        if self.take("rounded down"):
            return ("round", 1, value)
        if self.take("rounded"):
            return ("round", 0, value)
        return value

    def sum(self):
        left = self.product()
        while True:
            self.respell("value")                       # "10 take away 3"
            if self.take("plus", "+"):
                right = self.product()
                joining = is_words(left) or is_words(right)       # '"Score: " + score' joins them
                left = ("join", left, right) if joining else ("maths", "add", left, right)
            elif self.take("minus", "-"):
                left = ("maths", "sub", left, self.product())
            else:
                return left

    def product(self):
        left = self.unary()
        while True:
            self.respell("value")                       # "score doubled", "6 shared between 2"
            if self.take("times", "multiplied by", "*") or self.times_x():
                left = ("maths", "mul", left, self.unary())
            elif self.take("divided by", "/"):
                left = ("maths", "div", left, self.unary())
            else:
                return left

    def times_x(self):
        """'7 x 6' means times, unless the program has a name called x."""
        return self.peek() == "×" and self.take("×") or not self.kind_of("x") and self.take("x")

    def unary(self):
        self.respell("value")                           # "the greatest of a and b", "a dozen"
        if self.take("minus", "-", "negative"):
            return ("maths", "sub", ("number", 0), self.unary())
        value = self.atom()
        while True:
            self.respell("value")                       # "word in caps", "name back to front"
            if self.take("as a number", "as number", "as a whole number"):
                value = ("as number", value)
            elif self.take("as words", "as a word", "as text"):
                value = ("as text", value)
            elif self.take("in capitals", "in capital letters", "in uppercase", "in upper case"):
                value = ("case", "upper", value)
            elif self.take("in lowercase", "in lower case", "in small letters"):
                value = ("case", "lower", value)
            elif self.take("backwards", "backward", "reversed", "in reverse"):
                value = ("reverse", value)
            else:
                return value

    def atom(self):
        if self.done():
            raise Problem("Something is missing at the end.")
        w = self.words[self.at]
        if w.quoted:
            self.at += 1
            return ("text", w.text)
        number, after = read_number(self.words, self.at)
        if number is not None:
            self.at = after
            return ("decimal", number) if isinstance(number, float) else ("number", number)
        if self.peek() == "all":                       # "all the names" is just the list
            skip = 1 + (self.peek(1) == "of")
            skip += self.peek(skip) in ("the", "my", "your", "our")
            name = self.long_name(skip)
            if (self.kind_of(name[0] if name else self.peek(skip)) or "").startswith("list"):
                self.at += skip
        if self.peek() in ("the", "a", "an", "my", "your") and self.long_name(1):
            self.at += 1
        if self.long_name(0):
            name, size = self.long_name(0)
            self.at += size
            return ("name", name)
        start, problem = self.at, None
        for phrases, read in self.ATOMS:
            if self.take(*phrases):
                try:
                    return read(self)
                except Problem as found:
                    self.at = start
                    if self.kind_of(self.words[start].word) or (
                            self.words[start].word in ("the", "a", "an", "my", "your")
                            and self.kind_of(self.peek(1))):
                        break               # it was a name after all, like "number" or "first"
                    problem = problem or found      # "the number of pets": try the next reading
        if problem:
            raise problem
        if self.peek() in ("the", "a", "an", "my", "your") and self.kind_of(self.peek(1)):
            self.at += 1
        name = self.peek()
        if self.kind_of(name):
            self.at += 1
            return ("name", name)
        w = self.words[self.at]
        if w.word in ("the", "a", "an", "my", "your") and self.at + 1 < len(self.words):
            w = self.words[self.at + 1]          # name the real word, not "the"
        raise Problem(f"I don't know what '{w.text}' is yet.")

    def long_name(self, offset):
        """A name made of 2 or 3 words, like 'high score' (kept as high_score) -> (name, size)."""
        for size in (3, 2):
            parts = [self.peek(offset + n) for n in range(size)]
            if all(parts) and self.kind_of("_".join(parts)):
                return "_".join(parts), size
        return None

    # each of these runs after its words have been read

    def random(self):
        self.take("from", "between")
        low = self.sum()
        self.need("to", "and")
        return ("random", low, self.sum())

    def random_item(self):
        self.at += 1                     # "item", "name", "one", ...: any word
        self.need("from", "in", "of", "on")
        return ("random item", self.unary())

    def since(self):
        return ("since", self.unary())

    def elapsed(self):
        return ("since", ("name", self.names("last timer") and "last timer"))

    def round_up(self):
        return ("round", 2, self.unary())

    def round_down(self):
        return ("round", 1, self.unary())

    def round_nearest(self):
        return ("round", 0, self.unary())

    def whole(self):
        self.take("part of", "number of", "of")
        return ("round", 3, self.unary())

    def first(self):
        return self.nth("first")

    def last(self):
        return self.nth("last")

    def nth(self, which):
        """After 'the first', 'the second', 'the 3rd': '... letter of word', '... word in sentence',
        '... item in list', '... in list'."""
        if self.take("letter", "character"):
            self.need("of", "in")
            return ("letter", which, self.unary())
        if self.take("word"):
            self.need("of", "in")
            return ("item", which, ("split", "words", self.unary()))
        self.take("item", "one", "thing")
        self.need("in", "of", "on")
        return ("item", which, self.unary())

    def word_n(self):
        n = self.unary()
        self.need("of", "in")
        return ("item", n, ("split", "words", self.unary()))

    def item_n(self):
        n = self.unary()
        self.need("of", "in", "on")
        return ("item", n, self.unary())

    def count(self):
        unit = self.peek() if self.peek() in ("items", "things", "letters", "words", "names", "lines") else None
        after = [w.word for w in self.words[self.at + 1:]]
        if unit and self.kind_of(unit) and after in ([], ["there", "are"], ["are", "there"]):
            unit = None                     # "how many items" when items is the list itself
        self.at += bool(unit)
        self.take("are")
        self.take("in", "of", "on")         # "length of" has already used its "of"
        w = self.words[self.at] if not self.done() else None
        if w is not None and not w.quoted and re.fullmatch(FILE_NAME, w.text):
            self.at += 1                    # "how many lines in notes.txt"
            value = ("count", ("file", w.text), unit)
        else:
            value = ("count", self.unary(), unit)
        self.take("there are", "are there")   # "how many pets there are"
        return value

    def first_letter(self):
        return ("letter", "first", self.unary())

    def last_letter(self):
        return ("letter", "last", self.unary())

    def letter_n(self):
        n = self.unary()
        self.need("of", "in")
        return ("letter", n, self.unary())

    def join(self):
        left = self.unary()
        self.need("with", "and", "to")
        return ("join", left, self.unary())

    def upper(self):
        self.take("of")
        return ("case", "upper", self.unary())

    def lower(self):
        self.take("of")
        return ("case", "lower", self.unary())

    def file(self):
        """'the contents of notes.txt', "what's in notes.txt", 'the file called notes.txt'."""
        self.take("the file called", "the file named", "the file", "file")
        w = self.words[self.at] if not self.done() else None
        if w is None or not re.fullmatch(FILE_NAME, w.text):
            raise Problem("Which file? Like: the contents of notes.txt")
        self.at += 1
        return ("file", w.text)

    def gather(self, how):
        """After 'the biggest': '... in scores', '... of scores', '... number in scores'.
        'the total of' has used its 'of' already. Two or more values work too: 'the biggest of a and b',
        'the total of a, b and c'."""
        if how not in ("sum", "average"):
            if self.peek() not in ("in", "of", "on") and self.peek(1) in ("in", "of", "on"):
                self.at += 1
            self.need("in", "of", "on")
        values = [self.unary()]
        if values[0][0] == "name" and (self.kind_of(values[0][1]) or "").startswith("list"):
            return ("gather", how, values[0])
        while not self.done() and (self.words[self.at - 1].after.endswith(",") or self.peek() == "and"):
            start = self.at
            self.take("and")
            try:
                values.append(self.unary())
            except Problem:
                self.at = start
                break
        if len(values) == 1:
            return ("gather", how, values[0])
        if how in ("max", "min"):
            return ("pick", how, values)
        total = values[0]
        for value in values[1:]:
            total = ("maths", "add", total, value)
        return total if how == "sum" else ("maths", "div", total, ("number", len(values)))

    def words_in(self):
        return ("split", "words", self.unary())

    def letters_in(self):
        return ("split", "letters", self.unary())

    ATOMS = [
        (["a random number", "random number", "a random whole number", "a number at random"], random),
        (["a random", "random", "any random"], random_item),
        (["how long since", "how long has it been since", "time since", "the time since",
          "seconds since", "how long it's been since"], since),
        (["elapsed", "the elapsed time", "time elapsed", "the time elapsed"], elapsed),
        (["what time is it", "the time now", "the current time", "time now", "the time"],
         lambda p: ("time now",)),
        (["round up", "round up of"], round_up),
        (["round down", "round down of"], round_down),
        (["round", "the rounded"], round_nearest),
        (["the whole", "whole"], whole),
        (["the first letter of", "first letter of", "the first letter in", "first letter in"], first_letter),
        (["the last letter of", "last letter of", "the last letter in", "last letter in"], last_letter),
        (["letter", "the letter"], letter_n),
        (["word", "the word"], word_n),
        (["the first", "first"], first),
        (["the last", "last"], last),
        (["item", "the item", "number", "the number"], item_n),
        (["how many", "the number of", "number of", "the size of", "size of", "the length of",
          "length of", "the count of", "count of"], count),
        (["join", "combine"], join),
        (["capitals", "uppercase", "shout", "the capitals of"], upper),
        (["lowercase", "small", "the lowercase of"], lower),
        (["each word in", "the words in", "the words of", "every word in", "split"], words_in),
        (["each letter in", "the letters in", "the letters of", "every letter in"], letters_in),
        (["the width of the console", "the width of the screen", "the width of the window",
          "the console width", "the screen width", "console width", "screen width",
          "how wide the console is", "how wide the screen is", "the number of columns"],
         lambda p: ("console", "columns")),
        (["the height of the console", "the height of the screen", "the height of the window",
          "the console height", "the screen height", "console height", "screen height",
          "how tall the console is", "how tall the screen is", "the number of rows"],
         lambda p: ("console", "rows")),
        (["the contents of", "contents of", "what's in", "whats in", "what is in", "everything in",
          "the file"], file),
        (["the backwards of", "backwards of", "the reverse of", "reverse of", "reverse", "reversed"],
         lambda p: ("reverse", p.unary())),
        (both_ways("biggest largest highest maximum max"), lambda p: p.gather("max")),
        (both_ways("smallest lowest minimum min"), lambda p: p.gather("min")),
        (both_ways("total sum", "of in"), lambda p: p.gather("sum")),
        (both_ways("average mean", "of in"), lambda p: p.gather("average")),
        (["nothing", "empty", "blank", "an empty text"], lambda p: ("text", "")),
        (["it", "that", "the answer", "the result"], lambda p: ("name", "it")),
    ] + ordinal_atoms()


def is_words(node):
    """Typed text that isn't a number, or text joined up: + puts these together instead of adding."""
    if node[0] == "join":
        return True
    if node[0] != "text":
        return False
    try:
        float(node[1])
        return False
    except ValueError:
        return True


def read_value(words, names):
    """Read all the words as one value. Raises Problem if that isn't possible."""
    p = Parser(words, names)
    value = p.expression()
    if not p.done():
        raise Problem(f"I don't understand '{' '.join(w.raw for w in p.words[p.at:])}' here.")
    return value


def read_condition(words, names):
    p = Parser(words, names)
    value = p.condition()
    if not p.done():
        raise Problem(f"I don't understand '{' '.join(w.raw for w in p.words[p.at:])}' in that check.")
    return value


def try_value(words, names):
    try:
        return read_value(words, names)
    except Problem:
        return None


# ---------------- turning values into machine code ----------------

class Emitter:
    """Turns a value tree into code. `compiler` gives: a (the Asm), find(name) -> Var."""

    def __init__(self, compiler):
        self.c = compiler
        self.a = compiler.a

    def emit(self, node):
        """Code that leaves the value in rax. Returns its kind."""
        return getattr(self, "emit_" + node[0].replace(" ", "_"))(*node[1:])

    def emit_number(self, n):
        self.a.set(RAX, n)
        return "number"

    def emit_decimal(self, n):
        self.a.address(RAX, self.a.number(n))
        self.a.load(RAX, RAX)
        return "decimal"

    def emit_text(self, s):
        self.a.address(RAX, self.a.text(s))
        return "text"

    def emit_name(self, name):
        var = self.c.find(name)
        if var is None:
            raise Problem(f"I don't know what '{name}' is yet.")
        if var.kind.startswith("list"):
            self.a.address(RAX, var.place)
        else:
            self.a.address(RAX, var.place)
            self.a.load(RAX, RAX)
        return var.kind

    def emit_maths(self, op, left, right):
        a = self.a
        kind_left = self.numeric(self.emit(left))
        a.push(RAX)
        kind_right = self.numeric(self.emit(right))
        a.mov(RCX, RAX)
        a.pop(RAX)
        if op != "div" and kind_left == kind_right == "number":
            if op == "mul":
                a.multiply(RAX, RCX)
            else:
                a.op(op, RAX, RCX)
            return "number"
        for xmm, reg, kind in ((XMM0, RAX, kind_left), (XMM1, RCX, kind_right)):
            if kind == "number":
                a.whole_to_decimal(xmm, reg)
            else:
                a.to_xmm(xmm, reg)
        a.decimal_maths(op, XMM0, XMM1)
        a.from_xmm(RAX, XMM0)
        return "decimal" if "decimal" in (kind_left, kind_right) else "quotient"

    def emit_pick(self, how, values):
        """The biggest ('max') or smallest ('min') of a few values."""
        a = self.a
        kinds = []
        for value in values:
            kinds.append(self.numeric(self.emit(value)))
            a.push(RAX)
        decimal = any(kind != "number" for kind in kinds)
        for n in range(len(values) - 1, -1, -1):        # the answer so far ends up in rax
            a.pop(RCX)
            if decimal and kinds[n] == "number":
                a.whole_to_decimal(XMM1, RCX)
                a.from_xmm(RCX, XMM1)
            if n == len(values) - 1:
                a.mov(RAX, RCX)
                continue
            keep = a.new_label("pick_keep")
            if decimal:
                a.to_xmm(XMM0, RAX)
                a.to_xmm(XMM1, RCX)
                a.compare_decimals(XMM0, XMM1)
                a.jump_if(ABOVE if how == "max" else BELOW, keep)
            else:
                a.op("cmp", RAX, RCX)
                a.jump_if(GREATER if how == "max" else LESS, keep)
            a.mov(RAX, RCX)
            a.label(keep)
        return "decimal" if "decimal" in kinds else "quotient" if decimal else "number"

    def emit_join(self, left, right):
        self.text(self.emit(left))
        self.a.push(RAX)
        self.text(self.emit(right))
        self.a.mov(RCX, RAX)
        self.a.pop(RAX)
        self.a.call("join")
        return "text"

    def emit_random(self, low, high):
        self.whole(self.emit(low))
        self.a.push(RAX)
        self.whole(self.emit(high))
        self.a.mov(RCX, RAX)
        self.a.pop(RAX)
        self.a.call("random")
        return "number"

    def emit_random_item(self, list_value):
        a = self.a
        kind = self.emit(list_value)
        if not kind.startswith("list"):
            raise Problem("A random item needs a list. Make one first: make a list called pets")
        a.push(RAX)
        a.load(RCX, RAX)
        a.set(RAX, 1)
        a.call("random")
        a.mov(RCX, RAX)
        a.pop(R8)
        a.push(RCX)
        self.emit_default(item_kind(kind))
        a.mov(RDX, RAX)
        a.pop(RCX)
        a.mov(RAX, R8)
        a.call("item")
        return item_kind(kind)

    def emit_since(self, timer):
        if timer == ("name", None):
            raise Problem("There's no timer yet. Start one first: start a timer as t")
        kind = self.emit(timer)
        if kind != "timer":
            raise Problem("'how long since' needs a timer. Start one first: start a timer as t")
        self.a.call("elapsed")
        return "decimal"

    def emit_console(self, which):
        self.a.call("console_size")
        if which == "columns":
            self.a.mov(RAX, RCX)
        return "number"

    def emit_time_now(self):
        self.a.call("time_text")
        return "text"

    def emit_file(self, name):
        """Everything in the file, as text; empty if there's no such file."""
        a = self.a
        found = a.new_label("file_found")
        a.address(RAX, a.text(name))
        a.call("file_load")
        a.op("test", RAX, RAX)
        a.jump_if(NOT_EQUAL, found)
        self.emit_text("")
        a.label(found)
        return "text"

    def emit_file_exists(self, name):
        self.a.address(RAX, self.a.text(name))
        self.a.call("file_load")
        return self.flag_if(lambda: self.a.op("test", RAX, RAX), NOT_EQUAL)

    def emit_round(self, mode, value):
        kind = self.numeric(self.emit(value))
        if kind == "number":
            return "number"
        a = self.a
        a.to_xmm(XMM0, RAX)
        if mode == 0:                                   # nearest: add a half, then round down
            a.address(RAX, a.number(0.5))
            a.load(RAX, RAX)
            a.to_xmm(XMM1, RAX)
            a.decimal_maths("add", XMM0, XMM1)
            mode = 1
        a.round_decimal(XMM0, XMM0, mode)
        a.decimal_to_whole(RAX, XMM0)
        return "number"

    def emit_item(self, which, list_value):
        a = self.a
        if which not in ("first", "last"):
            self.whole(self.emit(which))
            a.push(RAX)
        kind = self.emit(list_value)
        if not kind.startswith("list"):
            raise Problem("That only works on a list. Make one first: make a list called names")
        if which == "first":
            a.set(RCX, 1)
        elif which == "last":
            a.load(RCX, RAX)
        else:
            a.pop(RCX)
        item = item_kind(kind)
        a.mov(R8, RAX)
        self.emit_default(item)
        a.mov(RDX, RAX)
        a.mov(RAX, R8)
        a.call("item")
        return item

    def emit_default(self, kind):
        if kind == "text":
            self.emit_text("")
        else:
            self.a.set(RAX, 0)

    def emit_count(self, value, unit=None):
        kind = self.emit(value)
        if unit in ("words", "lines") and not kind.startswith("list"):
            self.text(kind)
            kind = self.split_rax(unit)      # "how many words are in sentence"
        if kind != "text" and not kind.startswith("list"):
            self.text(kind)
        self.a.load(RAX, RAX)            # texts and lists both keep their size first
        return "number"

    def emit_letter(self, which, value):
        a = self.a
        if which not in ("first", "last"):
            self.whole(self.emit(which))
            a.push(RAX)
        self.text(self.emit(value))
        if which == "first":
            a.set(RCX, 1)
        elif which == "last":
            a.load(RCX, RAX)
        else:
            a.pop(RCX)
        a.call("letter")
        return "text"

    def emit_case(self, which, value):
        self.text(self.emit(value))
        self.a.call(which)
        return "text"

    def emit_as_number(self, value):
        self.whole(self.emit(value))
        return "number"

    def emit_as_text(self, value):
        self.text(self.emit(value))
        return "text"

    def emit_reverse(self, value):
        """A text with its letters the other way round, or a new list with its items the other way round."""
        kind = self.emit(value)
        if kind.startswith("list"):
            self.a.address(RCX, self.a.reserve(LIST_SIZE, "reversed_list"))
            self.a.call("reverse_list")
            return kind
        self.text(kind)
        self.a.call("reverse_text")
        return "text"

    def emit_gather(self, how, list_value):
        """'the biggest in scores' (max), 'the smallest' (min), 'the total of' (sum), 'the average of'.
        Goes through the list once, keeping the answer so far. Texts are read as numbers."""
        a = self.a
        kind = self.emit(list_value)
        if not kind.startswith("list"):
            said = {"max": "biggest in", "min": "smallest in", "sum": "total of", "average": "average of"}[how]
            raise Problem(f"That needs a list of numbers, like: the {said} scores")
        item = item_kind(kind)
        decimal = item in DECIMALS
        v = a.reserve(24, "gather")            # 0 the list, 8 position, 16 the answer so far
        top, end, keep = a.new_label("gather"), a.new_label("gather_end"), a.new_label("gather_keep")
        a.address(RCX, v)
        a.store(RCX, 0, RAX)
        a.set(RDX, 0)
        a.store(RCX, 8, RDX)
        a.store(RCX, 16, RDX)
        a.label(top)
        a.address(RCX, v)
        a.load(RAX, RCX, 0)
        a.load(RDX, RCX, 8)
        a.load(R8, RAX)
        a.op("cmp", RDX, R8)
        a.jump_if(NOT_LESS, end)
        a.shift_left(RDX, 3)
        a.op("add", RAX, RDX)
        a.load(RAX, RAX, 8)                    # the item
        if not decimal:
            self.whole(item)
        a.address(RCX, v)
        a.load(R8, RCX, 8)
        a.load(RDX, RCX, 16)
        if how in ("max", "min"):
            a.op("test", R8, R8)
            a.jump_if(EQUAL, keep)             # the first item is the answer so far
        if decimal:
            a.to_xmm(XMM0, RAX)
            a.to_xmm(XMM1, RDX)
        if how in ("sum", "average") and decimal:
            a.decimal_maths("add", XMM0, XMM1)
            a.from_xmm(RAX, XMM0)
        elif how in ("sum", "average"):
            a.op("add", RAX, RDX)
        else:
            if decimal:
                a.compare_decimals(XMM0, XMM1)
                a.jump_if(ABOVE if how == "max" else BELOW, keep)
            else:
                a.op("cmp", RAX, RDX)
                a.jump_if(GREATER if how == "max" else LESS, keep)
            a.mov(RAX, RDX)
        a.label(keep)
        a.store(RCX, 16, RAX)
        a.op_n("add", R8, 1)
        a.store(RCX, 8, R8)
        a.jump(top)
        a.label(end)
        a.address(RCX, v)
        a.load(RAX, RCX, 16)
        if how != "average":
            return item if decimal else "number"
        done = a.new_label("average_done")
        a.load(R8, RCX, 0)
        a.load(R8, R8)                         # how many
        a.op("test", R8, R8)
        a.jump_if(EQUAL, done)
        if decimal:
            a.to_xmm(XMM0, RAX)
        else:
            a.whole_to_decimal(XMM0, RAX)
        a.whole_to_decimal(XMM1, R8)
        a.decimal_maths("div", XMM0, XMM1)
        a.from_xmm(RAX, XMM0)
        a.label(done)
        return "decimal" if decimal else "quotient"

    def emit_split(self, how, value):
        self.text(self.emit(value))
        return self.split_rax(how)

    def split_rax(self, how):
        """The text in rax split into a list of its words, lines or letters."""
        a = self.a
        place = a.reserve(LIST_SIZE, "split_list")
        a.address(RCX, place)
        if how in ("words", "lines"):
            a.set(RDX, ord(" ") if how == "words" else ord("\n"))
            a.set(R8, 0)
            a.call("split")
        else:
            a.call("letters")
        a.address(RAX, place)
        return "list of text"

    # conditions: leave 1 (yes) or 0 (no) in rax

    def emit_truth(self, value):
        kind = self.emit(value)
        if kind == "yes/no":
            return kind
        raise Problem("I need a check here, like: if score is more than 10")

    def emit_not(self, value):
        self.emit(value)
        self.a.op_n("xor", RAX, 1)
        return "yes/no"

    def emit_and(self, left, right):
        return self.both(left, right, "and")

    def emit_or(self, left, right):
        return self.both(left, right, "or")

    def both(self, left, right, op):
        self.emit(left)
        self.a.push(RAX)
        self.emit(right)
        self.a.pop(RCX)
        self.a.op(op, RAX, RCX)
        return "yes/no"

    def emit_compare(self, how, left, right):
        a = self.a
        if how == "empty":
            self.emit_count(left)
            return self.flag_if(lambda: a.op("test", RAX, RAX), EQUAL)
        if how in ("not in", "not contains"):
            self.emit_compare(how[4:], left, right)
            a.op_n("xor", RAX, 1)
            return "yes/no"
        if how == "in":
            left, right, how = right, left, "contains"
        kind_left = self.emit(left)
        a.push(RAX)
        kind_right = self.emit(right)
        if how == "contains" and kind_left.startswith("list"):
            item = item_kind(kind_left)
            self.convert(kind_right, item)
            a.mov(RCX, RAX)
            a.pop(RAX)
            a.set(RDX, 1 if item == "text" else 0)
            a.call("list_has")
            return "yes/no"
        if how in ("contains", "starts", "ends"):
            self.text(kind_right)
            a.mov(RCX, RAX)
            a.pop(RAX)
            self.text_in_rax_keeping_rcx(kind_left)
            a.call({"contains": "contains", "starts": "starts_with", "ends": "ends_with"}[how])
            return "yes/no"
        if kind_left == kind_right == "text" and how in ("=", "!="):
            a.mov(RCX, RAX)
            a.pop(RAX)
            a.call("text_equal")
            if how == "!=":
                a.op_n("xor", RAX, 1)
            return "yes/no"
        return self.compare_numbers(how, kind_left, kind_right)

    def compare_numbers(self, how, kind_left, kind_right):
        a = self.a
        kind_right = self.numeric(kind_right)
        a.mov(RCX, RAX)
        a.pop(RAX)
        a.push(RCX)
        kind_left = self.numeric(kind_left)
        a.pop(RCX)
        if kind_left == kind_right == "number":
            jumps = {"=": 0x4, "!=": 0x5, ">": 0xF, "<": 0xC, ">=": 0xD, "<=": 0xE}
            return self.flag_if(lambda: a.op("cmp", RAX, RCX), jumps[how])
        for xmm, reg, kind in ((XMM0, RAX, kind_left), (XMM1, RCX, kind_right)):
            if kind == "number":
                a.whole_to_decimal(xmm, reg)
            else:
                a.to_xmm(xmm, reg)
        jumps = {"=": 0x4, "!=": 0x5, ">": 0x7, "<": 0x2, ">=": 0x3, "<=": 0x6}
        return self.flag_if(lambda: a.compare_decimals(XMM0, XMM1), jumps[how])

    def flag_if(self, check, condition):
        """rax = 1 if the check meets the condition, else 0."""
        a = self.a
        done = a.new_label("flag")
        check()
        a.set(RAX, 1)
        a.jump_if(condition, done)
        a.set(RAX, 0)
        a.label(done)
        return "yes/no"

    def text_in_rax_keeping_rcx(self, kind):
        if kind != "text":
            self.a.push(RCX)
            self.text(kind)
            self.a.pop(RCX)

    # changing one kind into another, in rax

    def numeric(self, kind):
        """Make sure rax holds something maths can use. Returns the new kind."""
        if kind == "text":
            self.a.call("text_to_number")
            return "number"
        if kind == "timer":
            self.a.call("elapsed")
            return "decimal"
        if kind == "yes/no":
            return "number"
        if kind.startswith("list"):
            raise Problem("I can't do maths with a whole list. Try: how many in the list, or the first in it.")
        return kind

    def whole(self, kind):
        kind = self.numeric(kind)
        if kind in DECIMALS:
            self.a.to_xmm(XMM0, RAX)
            self.a.decimal_to_whole(RAX, XMM0)
        return "number"

    def text(self, kind, places=None):
        """Turn rax into a text, ready to show."""
        a = self.a
        if kind == "text":
            return "text"
        if kind == "number":
            a.call("number_to_text")
        elif kind == "timer":
            a.call("elapsed")
            self.text("decimal", places)
        elif kind in DECIMALS:
            a.set(RCX, places if places is not None else (2 if kind == "decimal" else -1))
            a.call("decimal_to_text")
        elif kind == "yes/no":
            a.mov(RCX, RAX)
            a.address(RAX, a.text("yes"))
            done = a.new_label("yes")
            a.op("test", RCX, RCX)
            a.jump_if(NOT_EQUAL, done)
            a.address(RAX, a.text("no"))
            a.label(done)
        elif kind.startswith("list"):
            a.set(RCX, {"number": 0, "decimal": 1, "quotient": 1}.get(item_kind(kind), 2))
            a.address(RDX, a.text(", "))
            a.call("list_to_text")
        return "text"

    def convert(self, kind, wanted):
        """Turn rax from one kind into another (for storing in a name that already has a kind)."""
        if kind == wanted or wanted is None:
            return
        if wanted == "text":
            self.text(kind)
        elif wanted == "number":
            self.whole(kind)
        elif wanted in DECIMALS:
            kind = self.numeric(kind)
            if kind == "number":
                self.a.whole_to_decimal(XMM0, RAX)
                self.a.from_xmm(RAX, XMM0)
        elif wanted == "timer":
            raise Problem("Only 'start a timer' can make a timer.")
        else:
            raise Problem(f"That doesn't fit: it holds {wanted}, not {kind}.")


def item_kind(kind):
    """'list of text' -> 'text'. A list with nothing added yet holds texts."""
    return kind[len("list of "):] if kind.startswith("list of ") else "text"
