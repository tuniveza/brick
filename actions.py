"""Every built-in action: the first word picks it, the rest of the words fill it in.

The Compiler class builds on this; these methods use its a (assembler), emitter,
value(), store(), set_it(), find(), kind_of() and leave_loop().
"""
import difflib
import re

import dictionary
import runtime
from asm import ABOVE, EQUAL, R8, RAX, RCX, RDI, RDX, XMM0, XMM1
from expressions import DECIMALS, FILE_NAME, Problem, item_kind, read_value
from reader import Word, read_number
from window import WINDOW_HELP, about_window, read_spot, spot_at_end

def paint_code(paint):
    """The terminal code for an exact shade like '#00c000'. Exact, so the terminal's theme can't
    turn green into some other green."""
    return "38;2;" + ";".join(str(int(paint.lstrip("#")[k:k + 2], 16)) for k in (0, 2, 4))


COLOURS = {name: paint_code(paint) for name, paint in {
    "black": "#000000", "red": "#ff0000", "green": "#00c000", "yellow": "#ffff00", "blue": "#0000ff",
    "purple": "#a020f0", "magenta": "#ff00ff", "cyan": "#00ffff", "white": "#ffffff", "grey": "#808080",
    "gray": "#808080", "orange": "#ffa500", "pink": "#ff80c0", "brown": "#8b4513", "lime": "#00ff00",
    "gold": "#ffd700"}.items()}


def mixed(code, toward, amount=0.4):
    """'light blue', 'dark green': the colour mixed part way toward white (255) or black (0)."""
    red, green, blue = (int(c) for c in code.split(";")[2:])
    return "38;2;" + ";".join(str(round(c + (toward - c) * amount)) for c in (red, green, blue))
STYLES = {"bold": "1", "italic": "3", "italics": "3", "underlined": "4", "underline": "4"}
BIG = ("big", "large", "huge", "giant")      # "in big red letters": a console can only make it bold
TEXT_WORDS = {"text", "writing", "words", "message", "note", "letters", "label"}     # "red text saying hi"
SAYING = ("that says", "that reads", "which says", "which reads", "saying", "reading", "says", "reads")
ON_IT = {"on", "in", "inside", "into", "onto", "it", "the", "window", "screen", "console", "terminal", "there"}
CASES = {"in capitals": "upper", "in capital letters": "upper", "in uppercase": "upper", "in upper case": "upper",
         "in lowercase": "lower", "in lower case": "lower", "in small letters": "lower"}


def colour_at(w, j, named=True):
    """'red', 'light blue', 'dark green', 'crimson' or 'sea green' at w[j] (w ends with None)
    -> (code, words used), or None. The dictionary's colours come after the built-in ones;
    named: a colour word is nearby, so colours that are also things (salmon, peru) count too."""
    if w[j] in ("light", "bright", "dark") and w[j + 1] in COLOURS:
        return mixed(COLOURS[w[j + 1]], 0 if w[j] == "dark" else 255), 2
    found = dictionary.colour_at(w, j, named)
    if found and (found[1] > 1 or w[j] not in COLOURS):
        return found
    if w[j] in COLOURS:
        return COLOURS[w[j]], 1
    if w[j] in ("light", "bright", "dark"):             # "light crimson"
        found = dictionary.colour_at(w, j + 1, named)
        return (mixed(found[0], 0 if w[j] == "dark" else 255), found[1] + 1) if found else None
    return None


def colour_words():
    """Every one-word colour name, for spotting slips like 'in gren'."""
    return set(COLOURS) | {name for name in dictionary.colour_table() if " " not in name}


def background(colour):
    """The code for a colour behind the text instead of the text itself."""
    return "48" + colour[2:]
RESET = "\x1b[0m"
REPLACE_FILE, ADD_TO_FILE = 0o1101, 0o2101     # write-only + create, then empty it / add at the end
LIST_WORDS = ("list", "collection", "group", "set")
CHANGES = {"as a number": ("a number", "a whole number", "number", "numbers", "an integer", "digits"),
           "as words": ("words", "a word", "text", "a string", "writing"),
           "in capitals": ("capitals", "capital letters", "uppercase", "upper case", "caps", "all caps",
                           "block capitals"),
           "in lowercase": ("lowercase", "lower case", "small letters"),
           "backwards": ("backwards", "reverse", "the reverse")}
ARTICLES = ("the", "a", "an", "my", "your", "our")
AUDIENCE = ("the user", "the player", "the person", "everyone", "them", "me", "us", "him", "her")

EXAMPLES = {
    "write": ['write hello', 'write "Score:" score in green', 'write in bold red GAME OVER',
              'write x to 3 places', 'write hi on the same line', 'write a blank line',
              'write GAME OVER in big red letters', 'write the numbers from 1 to 10', 'show shopping.txt'],
    "ask": ['ask "What is your name?" as name', 'ask a number as guess', 'ask your age',
            'ask the user for their name'],
    "set": ['set score to 0', 'set high score to 10', 'let price be 2.5', 'set pet to a random item from pets',
            'set the colour to red', 'set the background colour to blue'],
    "add": ['add 1 to score', 'add it to names', 'add name to the end of names.txt'],
    "take": ['take 1 from lives', 'take from names', 'take the first from names'],
    "put": ['put name on the end of names', 'put "Zed" at the front of names', 'put score in best.txt',
            'put hello in the middle of the screen'],
    "remove": ['remove the first from names', 'remove the last from names', 'remove best.txt'],
    "make": ['make a list called names', 'make score 0', 'make a list called colours with red, green and blue',
             'make a variable called lives set to 3'],
    "wait": ['wait 2 seconds', 'after 5 seconds write hi', 'wait a random number from 1 to 5 seconds',
             'wait for a key', 'wait 500 milliseconds', '2 seconds later write hi'],
    "start": ['start a timer as t', 'start timing as lap'],
    "save": ['save score to best.txt', 'save names to names.txt'],
    "load": ['load best.txt as best', 'load names.txt as names', 'load names.txt as a list called names'],
    "delete": ['delete best.txt'],
    "move": ['move left', 'move down 3', 'move to the middle of the screen', 'move to row 3 column 10'],
    "window": ['put the window on the left side of the screen', 'make the window full screen',
               'make the window bigger', 'move the window right 200', 'make the window 800 by 600',
               'centre the window', 'set the title to My Game'],
    "placing text": ['write GO in the middle of the screen', 'write score at the top right',
                     'write hi at row 2 column 10', 'the width of the console',
                     'add "hi" in red to the right of the window and make it disappear after 5 seconds'],
    "clear": ['clear the screen', 'clear the list names'],
    "stop": ['stop', 'stop the game', 'leave the loop'],
    "if": ['if score is more than 10, write wow, otherwise write ok', 'if names contains "Bob" write hi Bob',
           'if score is more than 10:  (then the lines below it, indented)', 'if shopping.txt exists, write yes'],
    "repeat": ['write hi 3 times', 'repeat 3 times: write hi', 'ask a number as guess until guess is 7',
               'while lives is more than 0, ...', 'repeat forever: ... (leave the loop to get out)',
               'repeat 3 times:  (then the lines below it, indented)'],
    "count": ['count to 10', 'count from 1 to 10', 'count down from 10 to 1', 'count down from 10'],
    "for each": ['for each name in names write hello name', 'for each letter in word write letter',
                 'for each line in names.txt write line'],
    "teach": ['to greet someone means write hi someone in green', 'a turn means move left then beep',
              'when I say hi, write hello', 'to greet someone means:  (then the lines below it, indented)'],
}
for verb, same in {"write": "say show print display tell output", "set": "let change", "take": "subtract",
                   "make": "create remember", "wait": "pause sleep press", "save": "store keep",
                   "load": "open read get", "delete": "erase", "move": "go", "stop": "end quit exit",
                   "window": "place resize maximise maximize centre center shrink grow name call",
                   "add": "push increase decrease append", "clear": "empty"}.items():
    for word in same.split():
        EXAMPLES.setdefault(word, EXAMPLES[verb])


def ends_with(words, *phrases):
    """How many words a matching phrase covers at the end, or 0."""
    for phrase in phrases:
        parts = phrase.split()
        if len(words) >= len(parts) and [w.word for w in words[-len(parts):]] == parts:
            return len(parts)
    return 0


def starts_with(words, *phrases):
    for phrase in phrases:
        parts = phrase.split()
        if [w.word for w in words[:len(parts)]] == parts:
            return len(parts)
    return 0


def split_at(words, *markers, last=False):
    """Split at the first (or last) marker word -> (before, after), or (words, None)."""
    spots = [i for i, w in enumerate(words) if w.word in markers]
    if not spots:
        return words, None
    i = spots[-1] if last else spots[0]
    return words[:i], words[i + 1:]


def file_name(words):
    """'best.txt', 'the file best.txt', 'a file called best.txt' or "my scores.txt" -> the name;
    None if it isn't a file."""
    if not words:
        return None
    words = words[starts_with(words, "a file called", "a file named", "the file called", "the file named",
                              "file called", "file named", "the file", "a file", "file", "the"):]
    if len(words) != 1:
        return None
    name = words[0].text
    return name if re.fullmatch(FILE_NAME, name) else None


def plain_name(words):
    """The name something is kept under: 'the score' -> score, 'high score' -> high_score."""
    words = words[starts_with(words, *ARTICLES):] if len(words) > 1 else words
    if not 1 <= len(words) <= 3 or not all(w.word and re.fullmatch(r"[a-z_]\w*", w.word) for w in words):
        said = " ".join(w.raw for w in words) or "nothing"
        raise Problem(f"'{said}' should be a name of one to three words, like score, names or high score.")
    return "_".join(w.word for w in words)


LIST_PATTERNS = (r"(?:a |an )?(?:new |empty )*(?:LIST)(?: of| called| named)? (\w+(?: \w+){0,2})",
                 r"(\w+) (?:into )?(?:a |an )?(?:new |empty )*(?:LIST)")


def list_words():
    """'list', 'collection', ... and the dictionary's words for a list: 'inventory', 'deck' ..."""
    return LIST_WORDS + tuple(sorted(dictionary.first_words("list")))
STARTING_AT = ("set to", "equal to", "equals", "=", "with the value", "with value", "starting at",
               "starting from", "that starts at", "which starts at", "to", "as")


def list_name(words):
    """'a list called names', 'a new list of high scores', 'names a list' -> the list's name, else None."""
    text = " ".join(w.word or "" for w in words)
    for pattern in LIST_PATTERNS:
        found = re.fullmatch(pattern.replace("LIST", "|".join(list_words())), text)
        if found:
            return found.group(1).replace(" ", "_")
    return None


def list_items(words):
    """'red, green and blue' -> the words of each item: [[red], [green], [blue]]."""
    items, item = [], []
    for w in words:
        if w.word == "and" and item:
            items.append(item)
            item = []
            continue
        ends = w.after[-1:] in (",", ".", ";")
        item.append(Word(w.raw[:-1]) if ends else w)
        if ends:
            items.append(item)
            item = []
    return [i for i in items + [item] if i]


def said(name):
    return name.replace("_", " ")


def case_at(words, start, end=None):
    """'in capitals' or 'in lowercase' (or a dictionary way of saying it, like 'in caps') from words[start]
    -> ('upper' or 'lower', words used), else None. end: it must finish there."""
    for n in range(4, 1, -1):
        if end is not None and start + n != end or start + n > len(words):
            continue
        part = words[start:start + n]
        found = dictionary.respell(part, "value", whole=True)
        part = found[0] if found else part
        case = CASES.get(" ".join(w.word or "" for w in part))
        if case:
            return case, n
    return None


def case_at_end(words):
    """'... in capitals' at the end, with something before it -> ('upper' or 'lower', words used), else None."""
    return next((case_at(words, k, len(words)) for k in range(max(1, len(words) - 4), len(words) - 1)
                 if case_at(words, k, len(words))), None)


def cased(pieces, case):
    """The pieces of a sentence, all in capitals or all in small letters."""
    if case is None:
        return pieces
    return [(kind, getattr(piece, case)() if kind == "text" else ("case", case, piece)) for kind, piece in pieces]


class Actions:
    def handler_for(self, words):
        return getattr(self, "do_" + (words[0].word or ""), None) if words[0].word in STARTERS else None

    def show(self, s):
        self.a.address(RAX, self.a.text(s))
        self.a.call("write_text")

    # ---- the screen ----

    def do_write(self, words):
        self.written = True
        body = words[1:]
        if words[0].word in ("tell", "show"):
            audience = starts_with(body, *AUDIENCE)             # "tell me the time"
            body = body[audience:]
            if audience and len(body) > 1 and body[0].word == "that":
                body = body[1:]                                 # "tell the user that the game is over"
        if self.text_saying(body):                              # "write text on it that says hi"
            return self.do_write([words[0]] + self.text_saying(body))
        before, after = split_at(body, "to", "into", last=True)
        if not (after and file_name(after)) and not self.reads_as_value(body):
            before, after = split_at(body, "in", last=True)       # "write the time in log.txt", but not
        if after and file_name(after) and before:                 # "write what's in log.txt"
            return self.save_file(before, file_name(after), REPLACE_FILE, written=True)
        body, codes, newline, places, spot, case = self.take_modifiers(body)
        if spot:
            self.write_placed(body, codes, places, spot, case)
            if newline:
                self.show("\n")
            return
        for k in range(max(1, len(body) - 3), len(body)):       # "in gren"
            if body[k - 1].word in ("in", "bold", "light", "dark", "bright", "a", "an"):
                self.note_slip(body[k].text, colour_words())
        numbers, shown = self.numbers_from(body), self.file_shown(body)
        if codes:
            self.show("".join(f"\x1b[{code}m" for code in codes))
        if numbers:                                         # "write the numbers from 1 to 3"
            self.count_aloud(*numbers, same_line=not newline)
            if codes:
                self.end_style()
            return None if newline else self.show("\n")       # on one line, then the line ends
        if shown:                                           # "show shopping.txt"
            return self.show_file(shown, codes, "\n" if newline else "")
        if [w.word for w in body] not in (["a", "blank", "line"], ["a", "new", "line"], ["nothing"], []):
            self.write_words(body, places, case)
            self.last_shown = "line" if newline else None
        if codes:
            self.end_style()
        if newline:
            self.show("\n")

    def end_style(self):
        """Back to normal after 'write hi in green', then back to the writing colours, if any were set."""
        a = self.a
        self.show(RESET)
        for which in ("text", "background"):
            skip = a.new_label("no_colour")
            a.address(RAX, self.colour_slot(which))
            a.load(RAX, RAX)
            a.op("test", RAX, RAX)
            a.jump_if(EQUAL, skip)
            a.call("write_text")
            a.label(skip)

    def colour_slot(self, which):
        """Where the colour from 'set the colour to red' (or the background colour) is kept while
        the program runs: 0 if there isn't one."""
        if not getattr(self, "colour_places", None):
            self.colour_places = {"text": self.a.reserve(8, "writing_colour"),
                                  "background": self.a.reserve(8, "background_colour")}
        return self.colour_places[which]

    def set_writing(self, code, which="text"):
        """Change the writing (or background) colour from now on. code None puts it back to normal:
        the background alone, or for the writing colour, both."""
        for slot in ("text", "background") if code is None and which == "text" else (which,):
            self.a.address(RCX, self.colour_slot(slot))
            if code:
                self.a.address(RAX, self.a.text(f"\x1b[{code}m"))
            else:
                self.a.set(RAX, 0)
            self.a.store(RCX, 0, RAX)
        if code:
            self.show(f"\x1b[{code}m")
        elif which == "text":
            self.show(RESET)
        else:
            self.end_style()

    do_say = do_show = do_print = do_display = do_tell = do_output = do_write

    def file_shown(self, body):
        """'shopping.txt', 'the file shopping.txt', "what's in shopping.txt" -> the file's name; else None."""
        if file_name(body):
            return file_name(body)
        try:
            node = read_value(body, self.kind_of)
        except Problem:
            return None
        return node[1] if node[0] == "file" else None

    def show_file(self, name, codes, newline):
        """Show what's in a file, or say it isn't there yet."""
        a = self.a
        missing, done = a.new_label("no_file"), a.new_label("file_shown")
        a.address(RAX, a.text(name))
        a.call("file_load")
        a.op("test", RAX, RAX)
        a.jump_if(EQUAL, missing)
        a.call("write_text")
        if codes:
            self.end_style()
        if newline:
            self.show(newline)
        a.jump(done)
        a.label(missing)
        self.show(f"({name} doesn't exist yet.)\n")
        if codes:
            self.end_style()
        a.label(done)

    def numbers_from(self, body):
        """'the numbers from 1 to 3', 'all the numbers 1 to 10' -> (low, high); else None."""
        n = starts_with(body, "all the numbers from", "all the numbers", "the numbers from", "the numbers",
                        "numbers from", "every number from", "each number from")
        back = ends_with(body, "backwards", "backward", "in reverse", "reversed")
        loop = self.read_range("number", body[n:len(body) - back]) if n and len(body) > n + back else None
        if not loop or loop[2]:
            return None
        return loop[1][:0:-1] if back else loop[1][1:]

    def reads_as_value(self, words):
        try:
            read_value(words, self.kind_of)
            return True
        except Problem:
            return False

    def take_modifiers(self, body):
        """Pull how-to-show words off the start and end:
        'in green', 'in bold red', 'on a blue background', 'on the same line', 'to 3 places',
        'in the middle of the screen', 'at row 2 column 10', 'in capitals'.
        Returns (what's left, style codes, newline?, places, spot on the screen, 'upper' / 'lower' or None)."""
        codes, newline, places, spot, case = [], True, None, None, None
        changed = True
        while changed and body:
            changed = False
            found = self.style_at(body, 0)
            if found and found[1] < len(body):
                codes, body, changed = codes + found[0], body[found[1]:], True
                continue
            n = ends_with(body, "on the same line", "without a new line", "without a newline",
                          "with no new line", "on one line")
            if n:
                newline, body, changed = False, body[:-n], True
                continue
            if self.places_at_end(body):
                places, n = self.places_at_end(body)
                body, changed = body[:-n], True
                continue
            if case_at(body, 0) and case_at(body, 0)[1] < len(body):       # "write in capitals hello"
                case, n = case_at(body, 0)
                body, changed = body[n:], True
                continue
            if case_at_end(body) and not self.ends_cased(body):         # "write hello in capitals"
                case, n = case_at_end(body)
                body, changed = body[:-n], True
                continue
            for i in range(max(1, len(body) - 6), len(body)):
                found = self.style_at(body, i)
                if found and i + found[1] == len(body):
                    codes, body, changed = found[0] + codes, body[:i], True
                    break
            if not changed and spot is None:
                body, spot = spot_at_end(body, self.kind_of)
                changed = spot is not None
        if body and body[-1].after.endswith(","):           # "ten, in green"
            body = body[:-1] + [Word(body[-1].raw[:-1])]
        return body, codes, newline, places, spot, case

    def ends_cased(self, body):
        """Does 'in capitals' at the end belong to the value just before it, as in
        'write the first letter of name in capitals'? Then only that value is in capitals."""
        pieces = self.word_pieces(body)
        return bool(pieces) and pieces[-1][0] == "value"

    def style_at(self, words, i):
        """A style phrase starting at words[i] -> (codes, how many words), or None."""
        w = [x.word for x in words] + [None]
        j = i
        if w[j] in ("coloured", "colored") and colour_at(w, j + 1):
            return [colour_at(w, j + 1)[0]], 1 + colour_at(w, j + 1)[1]
        if w[j] in ("on", "with"):
            j += 2 if w[j + 1] in ("a", "an") else 1
            colour = colour_at(w, j)
            if colour and w[j + colour[1]] == "background":
                return [background(colour[0])], j + colour[1] + 1 - i
            return None
        if w[j] not in ("in", "using"):
            return None
        j += 1
        named = starts_with(words[j:], "the colour", "the color", "colour", "color")
        j += named
        codes, big, thing = [], False, False
        while True:
            if w[j] == "and" and codes and (colour_at(w, j + 1) or w[j + 1] in STYLES):
                j += 1
            if colour_at(w, j):
                code, used = colour_at(w, j)
                thing = thing or not colour_at(w, j, named=False)     # salmon, peru: also everyday things
            elif w[j] in STYLES:
                code, used = STYLES[w[j]], 1
            elif w[j] in BIG and not big:
                code, used, big = STYLES["bold"], 1, True
            else:
                break
            codes.append(code)
            j += used
        if not codes:
            return None
        if w[j] in ("colour", "color"):     # "in salmon colour"
            named, j = True, j + 1
        if w[j] in ("letters", "text", "writing", "type"):
            named, j = True, j + 1
        elif big:
            return None                     # "in big trouble" isn't a style; "in big letters" is
        if thing and not named:
            return None                     # "write I live in peru" stays as typed
        return codes, j - i

    def places_at_end(self, body):
        """'... to 3 places' or '... to 3 decimal places' -> (3, words used), else None."""
        n = ends_with(body, "decimal places", "decimal place", "places", "place")
        if not n or len(body) < n + 2 or body[-n - 2].word != "to":
            return None
        places, _ = read_number(body, len(body) - n - 1)
        return (places, n + 2) if isinstance(places, int) else None

    def word_pieces(self, body):
        """Split the words into plain text and values to fill in -> [("text", s) or ("value", v)].
        A value if the words make one ("length of word"); otherwise the words, with any values
        inside them filled in ("hello name"). Plain numbers and quoted text stay exactly as typed."""
        if len(body) > 1 and body[0].raw in ("-", "*", "•"):              # "write - item": a bullet point
            return [("text", body[0].raw + " ")] + self.word_pieces(body[1:])
        try:
            node = read_value(body, self.kind_of)
        except Problem:
            node = None
        if node and node[0] not in ("number", "decimal", "text"):
            return [("value", node)]
        pieces, typed, i = [], "", 0
        while i < len(body):
            end, node = self.value_inside(body, i)
            if node:
                space = " " if i else ""
                if typed + space + body[i].before:
                    pieces.append(("text", typed + space + body[i].before))
                pieces.append(("value", node))
                typed, i = body[end - 1].after, end
                continue
            for w in body[i:max(end, i + 1)]:                   # words that stay as typed
                typed += (" " if i else "") + (w.text + w.after if w.quoted else w.raw)
                if not w.quoted and w.word:
                    self.note_slip(w.text, self.own_names())
                i += 1
        if typed:
            pieces.append(("text", typed))
        return pieces

    def write_words(self, body, places, case=None):
        for kind, piece in cased(self.word_pieces(body), case):
            if kind == "text":
                self.show(piece)
            else:
                self.emitter.text(self.emitter.emit(piece), places)
                self.a.call("write_text")

    def text_value(self, body, places, case=None):
        """Code that leaves the words as one text in rax."""
        for n, (kind, piece) in enumerate(cased(self.word_pieces(body), case) or [("text", "")]):
            if kind == "text":
                self.emitter.emit_text(piece)
            else:
                self.emitter.text(self.emitter.emit(piece), places)
            if n:
                self.a.mov(RCX, RAX)
                self.a.pop(RAX)
                self.a.call("join")
            self.a.push(RAX)
        self.a.pop(RAX)

    def value_inside(self, body, start):
        """The longest run of words from start that makes a value worth filling in
        ("how many in names", "score", "first letter of word") -> (end, value); else (start, None).
        Plain numbers, quoted text and 'it' stay as typed."""
        if body[start].quoted or body[start].word in ("it", "a", "i", "that"):
            return start, None
        for end in range(len(body), start, -1):
            try:
                node = read_value(body[start:end], self.kind_of)
            except Problem:
                continue
            if self.stays_words(body, start, end):
                return end, None
            before = body[start - 1] if start else None
            if node == ("name", body[start].word) and before and before.word == node[1] and not before.after:
                return end, None                # "you took tries tries": the second one is the word
            if any(w.word in ("x", "×") and not w.quoted for w in body[start:end]) and not self.find("x"):
                continue                        # "write what is 7 x 6?" asks it; "write 7 x 6" works it out
            if body[-1].after.endswith("?") and any(w.word == "times" for w in body[start:end]):
                continue                        # "write what is 7 times 6?" asks it too
            if node[0] in ("number", "decimal", "text") or node == ("name", "it"):
                return start, None
            return end, node
        return start, None

    def stays_words(self, body, start, end):
        """'the total' in 'write the total is total' is just words: a name straight after 'the'
        that's followed by is/was/are/were, or that's used on its own elsewhere in the sentence.
        So is 'score' in 'write your final score is score': a name followed by is/was that's used again later."""
        the = body[start].word == "the"
        lead = body[start].word in ("the", "your", "my", "our")
        name = [w.word for w in body[start + lead:end]]
        if not name or not self.find("_".join(name)):
            return False
        said = [w.word for w in body]
        named = (end < len(body) and said[end] in ("is", "was", "are", "were", "equals")
                 or body[end - 1].after.endswith(":"))
        again = [k for k in range(len(said)) if said[k:k + len(name)] == name and not start <= k < end
                 and (k == 0 or said[k - 1] != "the")]
        if the:
            return named or bool(again)
        return named and any(k >= end for k in again) and self.opens_sentence(body, start)

    def opens_sentence(self, body, start):
        """Does the sentence start here, or with 'the' and a word or two, like 'the final' or 'your best'?"""
        k = start - 1
        while k >= max(0, start - 2) and body[k].word not in ("the", "your", "my", "our") and \
                body[k].word.isalpha() and not self.find(body[k].word) and body[k].word not in ("x", "times"):
            k -= 1
        return start == 0 or k >= 0 and body[k].word in ("the", "your", "my", "our")

    def do_blank(self, words):
        self.show("\n")

    do_new = do_blank

    def do_beep(self, words):
        self.show("\a")

    def do_clear(self, words):
        rest = words[1:]
        if [w.word for w in rest] in ([], ["the", "screen"], ["screen"], ["everything"], ["the", "console"],
                                      ["the", "terminal"], ["the", "window"]):
            return self.show("\x1b[2J\x1b[H")
        rest = rest[starts_with(rest, "the list", "the"):]
        self.empty_list(plain_name(rest))

    def do_empty(self, words):
        rest = words[1:]
        self.empty_list(plain_name(rest[starts_with(rest, "the list", "the"):]))

    def empty_list(self, name):
        var = self.find(name)
        if var is None or not var.kind.startswith("list"):
            raise Problem(f"'{said(name)}' isn't a list. Make one first: make a list called {said(name)}")
        self.a.address(RAX, var.place)
        self.a.set(RCX, 0)
        self.a.store(RAX, 0, RCX)

    def do_move(self, words):
        rest = [w.word for w in dictionary.respell_all(words[1:2], "place") + words[2:]]     # "move upwards"
        if about_window(words):
            return self.window_action(words)
        if rest[:1] == ["to"]:
            return self.move_to_spot(words[2:])
        directions = {"up": "A", "down": "B", "right": "C", "forward": "C", "left": "D", "back": "D"}
        if not rest or rest[0] not in directions:
            raise Problem("Move which way? Try: move left, move down 3, or move to the middle of the screen")
        steps = 1
        if len(rest) > 1:
            steps, _ = read_number(words, len(words) - len(rest) + 1)
            if not isinstance(steps, int):
                raise Problem("How far? Use a whole number, like: move down 3")
        self.show(f"\x1b[{steps}{directions[rest[0]]}")

    do_go = do_move

    def do_place(self, words):
        return self.window_action(words) if about_window(words) else self.do_put(words)

    def do_resize(self, words):
        if not about_window(words):
            raise Problem("Resize what? Try: resize the window to 800 by 600")
        self.window_action(words)

    do_maximise = do_maximize = do_centre = do_center = do_shrink = do_grow = do_resize

    def do_name(self, words):
        """'name the window My Game', 'call the window My Game'."""
        rest = words[1:]
        if len(rest) > 1 and rest[0].word in ("it", "that", "this"):    # "ask a number and call it guess"
            return self.assign(plain_name(rest[1:]), rest[:1])
        n = starts_with(words[1:], "the window", "the console", "the terminal", "this window", "the game")
        if not n:
            raise Problem("Name what? Try: name the window My Game")
        self.set_title(words[1 + n:])

    do_call = do_name

    def do_colour(self, words, behind=False):
        """'colour red', 'set the colour to red'; behind: it's the background colour."""
        name = words[-1].word
        if name in ("normal", "plain"):
            return self.set_writing(None, "background" if behind else "text")
        w = [x.word for x in words] + [None]
        colour = None
        for k in range(max(1, len(words) - 4), len(words)):         # the longest colour name at the end
            found = colour_at(w, k)
            if found and k + found[1] == len(words):
                colour = found
                break
        if not colour:
            raise Problem(f"I don't know the colour '{name}'. Try one of: {', '.join(COLOURS)}, "
                          "or one from: brick help dictionary colours.")
        self.coloured = True
        if behind:
            self.set_writing(background(colour[0]), "background")
            if not self.written:
                self.show("\x1b[2J\x1b[H")              # nothing shown yet: the whole screen turns that colour
            return None
        self.set_writing(colour[0])

    do_color = do_colour

    def is_colour(self, words):
        """Do these words name a colour (or 'normal')? For dictionary phrases like 'turn a colour'."""
        w = [x.word for x in words] + [None]
        found = colour_at(w, 0)
        return w[:-1] in (["normal"], ["plain"]) or bool(found) and found[1] == len(words)

    def do_bold(self, words):
        self.coloured = True
        self.set_writing("1")

    def do_plain(self, words):
        self.set_writing(None)

    def do_stop(self, words):
        rest = {w.word for w in words[1:]}
        if rest & {"loop", "repeating", "looping"}:
            return self.leave_loop()
        if rest - {"the", "program", "game", "app", "now", "here", "everything", "whole", "thing",
                   "it", "playing", "running", "please", "this", "window", "console", "terminal"}:
            raise Problem("'stop' ends the program. To leave a loop instead, say: leave the loop")
        self.show(RESET)
        runtime.finish(self.a)

    do_end = do_quit = do_exit = do_stop

    def do_leave(self, words):
        self.leave_loop()

    do_break = do_leave

    # ---- the keyboard ----

    def do_ask(self, words):
        self.written = True
        body = words[1:]
        body = body[starts_with(body, *AUDIENCE):]
        target = None
        spots = [i for i, w in enumerate(body) if w.word in ("as", "into", "called", "named") and 0 < i < len(body) - 1]
        if spots:
            target, body = plain_name(body[spots[-1] + 1:]), body[:spots[-1]]
        body = body[:len(body) - ends_with(body, "and save it", "and keep it", "and store it",
                                           "and remember it")]
        body, codes, _, _, _, _ = self.take_modifiers(body)
        body = body[starts_with(body, "for", "what"):]
        if len(body) > 2 and body[0].word in ARTICLES + ("their",) and (body[1].word or "").endswith("'s"):
            body = [Word("their")] + body[2:]                 # "ask the player's name" -> Name?
        if body and body[0].quoted:
            prompt, noun = body[0].text, None
        else:
            article = body[0].word if body and body[0].word in ARTICLES + ("their", "his", "her", "you're",
                                                                         "youre", "ur") else None
            nouns = body[1:] if article else body
            noun = " ".join(w.word for w in nouns if w.word) or "answer"
            prompt = noun[0].upper() + noun[1:] + "?"
            if target is None and article not in ("a", "an") and 1 <= len(nouns) <= 2:
                target = plain_name(nouns)
        is_number = noun in ("number", "whole number", "age") or \
            (target and self.kind_of(target) in ("number",) + DECIMALS)
        prompt = prompt if prompt.endswith(" ") else prompt + " "
        self.show("".join(f"\x1b[{code}m" for code in codes) + prompt)
        if codes:
            self.end_style()
        self.a.call("read_number" if is_number else "read_line")
        kind = "number" if is_number else "text"
        if target:
            self.store(target, kind)
        self.set_it(kind)

    def do_wait(self, words):
        rest = [w.word for w in words[1:]]
        if set(rest) & {"enter", "return"}:
            self.a.call("read_line")
            return
        if set(rest) & {"key", "keypress", "button"}:
            return self.wait_key()
        if not rest or starts_with(words[1:], "for a key", "for any key", "for a keypress", "any key",
                                   "for a key press", "for the user", "for someone", "for me"):
            return self.wait_key()
        if rest in (["for", "enter"], ["for", "return"], ["enter"], ["return"]):
            self.a.call("read_line")
            return
        body = words[1:]
        body = body[starts_with(body, "for"):]
        found = dictionary.respell(body, "time", whole=True)       # "wait a while" -> wait 3 seconds
        body = found[0] if found else body
        scale = 1_000_000_000
        n = ends_with(body, "seconds", "second", "secs", "sec", "s")
        if not n:
            n = ends_with(body, "milliseconds", "millisecond", "ms")
            scale = 1_000_000 if n else scale
        if not n:
            n = ends_with(body, "minutes", "minute", "mins", "min")
            scale = 60_000_000_000 if n else scale
        if not n and body and dictionary.respell(body[-1:], "time", whole=True):     # "wait 2 hours"
            amount, unit = dictionary.respell(body[-1:], "time", whole=True)[0]
            n, scale = 1, round(float(amount.word) * dictionary.TIME_UNITS[unit.word] * 1_000_000_000)
        body = body[:len(body) - n]
        if [w.word for w in body] in (["a"], ["an"], ["one"], [], ["a", "moment"], ["a", "bit"]):
            node = ("number", 1)
        elif [w.word for w in body] in (["half", "a"], ["a", "half"]):
            node = ("decimal", 0.5)
        else:
            try:
                node = read_value(body, self.kind_of)
            except Problem:
                close = difflib.get_close_matches(body[-1].word or "", ["seconds", "minutes", "milliseconds"], n=1)
                if close:                                       # "wait 2 secnds"
                    raise Problem(f"I don't understand '{body[-1].raw}'. Did you mean '{close[0]}'? "
                                  f"Like: wait 2 {close[0]}")
                raise
        kind = self.emitter.numeric(self.emitter.emit(node))
        if kind == "number":
            self.a.set(RCX, scale)
            self.a.multiply(RAX, RCX)
        else:
            self.a.to_xmm(XMM0, RAX)
            self.a.address(RAX, self.a.number(scale))
            self.a.load(RAX, RAX)
            self.a.to_xmm(XMM1, RAX)
            self.a.decimal_maths("mul", XMM0, XMM1)
            self.a.decimal_to_whole(RAX, XMM0)
        self.a.call("sleep")

    do_pause = do_sleep = do_wait

    def do_press(self, words):
        if [w.word for w in words[1:]] in (["enter"], ["return"]):
            self.a.call("read_line")
        else:
            self.wait_key()

    def wait_key(self):
        self.a.call("wait_key")
        self.set_it("text")

    # ---- the clock ----

    def do_start(self, words):
        rest = words[1:]
        if not any(w.word in ("timer", "timing", "stopwatch", "clock") for w in rest):
            raise Problem("Start what? Try: start a timer as t")
        before, after = split_at(rest, "as", "called", "named")
        name = plain_name(after) if after else "timer"
        self.a.set(RDI, 1)              # the stopwatch clock
        self.a.call("now")
        if self.find(name) is None:
            self.new_var(name, "timer")
        if self.find(name).kind != "timer":
            raise Problem(f"'{said(name)}' already holds something else. Pick another name for the timer.")
        self.store(name, "timer")
        self.last_timer = self.find(name)

    # ---- names and values ----

    def do_set(self, words):
        body = words[1:]
        title = starts_with(body, "the title to", "the title of the window to", "the window title to",
                            "the title as", "title to", "the console title to")
        if title:
            return self.set_title(body[title:])
        colour = starts_with(body, "the text colour to", "the text color to", "text colour to", "text color to",
                             "the text colour back to", "the text color back to",
                             "the colour of the text to", "the color of the text to", "the writing colour to",
                             "the writing color to", "the font colour to", "the font color to")
        colour = colour or self.writing_colour(body, "the colour", "the color")
        if colour:
            return self.do_colour(words[:1] + body[colour:])
        behind = self.writing_colour(body, "the background colour", "the background color", "the background")
        if behind:
            return self.do_colour(words[:1] + body[behind:], behind=True)
        if body[:1] and body[0].word == "it" and self.made_before:      # "make a variable called x and set it to 5"
            body = [Word(self.made_before)] + body[1:]
        into = next((i for i, w in enumerate(body) if w.word == "into" and i), None)
        if into and not any(w.word in ("to", "be", "=") for w in body[:into]):
            return self.change_into(body[:into], body[into + 1:])
        for i, w in enumerate(body):
            if i and w.word in ("to", "be", "=", "as", "equals", "equal"):
                skip = 2 if w.word == "equal" and i + 1 < len(body) and body[i + 1].word == "to" else 1
                return self.assign(plain_name(body[:i]), body[i + skip:])
        raise Problem("Set it to what? Try: set score to 0")

    do_let = do_change = do_set

    def change_into(self, thing, kind):
        """'change score into words', 'turn name into capitals', 'turn "42" into a number'.
        A name is changed where it's kept; the answer is also 'it', for typed text like "42"."""
        said = " ".join(w.word or "" for w in kind)
        how = next((how for how, ways in CHANGES.items() if said in ways), None)
        if how is None:
            ways = ", ".join(ways[0] for ways in CHANGES.values())
            raise Problem(f"I can't change something into '{' '.join(w.raw for w in kind)}'. "
                          f"I can change it into: {ways}.")
        node = read_value(thing + [Word(w) for w in how.split()], self.kind_of)
        kind = self.emitter.emit(node)
        name = "_".join(w.word or "" for w in thing[starts_with(thing, *ARTICLES):])
        var = self.find(name) if all(w.word for w in thing) else None
        if var and not var.kind.startswith("list"):
            self.store(name, kind)
        self.set_it(kind)

    def writing_colour(self, body, *things):
        """'the colour to red' -> how many words come before the colour; 0 if it isn't a colour,
        or if the program has its own name for the thing (colour, background)."""
        n = starts_with(body, *[f"{thing} {to}" for thing in things for to in ("to", "back to")])
        if not n or self.find("_".join(w.word for w in body[1:n] if w.word not in ("to", "back"))):
            return 0
        rest = [w.word for w in body[n:]]
        found = colour_at(rest + [None], 0)
        if len(rest) == 1 and not found:
            self.note_slip(body[n].text, colour_words())     # "set the colour to gren"
        return n if rest in (["normal"], ["plain"]) or found and found[1] == len(rest) else 0

    def assign(self, name, value_words):
        words = [w.word for w in value_words]
        if words and words[-1] in list_words() and len(words) <= 3:
            return self.new_list(name)
        if not value_words:
            raise Problem(f"Set {said(name)} to what?")
        self.store(name, self.emitter.emit(self.value_or_text(value_words)))

    def do_make(self, words):
        if about_window(words[1:3]) or about_window(words[1:2]):
            return self.window_action(words)
        name = list_name(words[1:])
        if name:
            return self.new_list(name)
        if self.list_with_items(words[1:]) or self.new_variable(words[1:]):
            return
        if any(w.word in ("to", "be", "=", "equal") for w in words[1:]):
            return self.do_set(words)
        if len(words) > 2:
            return self.assign(plain_name(words[1:2]), words[2:])
        raise Problem("Make what? Try: make a list called names")

    do_create = do_make

    def do_remember(self, words):
        text = " ".join(w.word or "" for w in words[1:])
        found = re.fullmatch(rf"(?:a |an )?(?:{'|'.join(list_words())}) (?:of |called |named )?(\w+)", text)
        if found:
            return self.new_list(found.group(1))
        before, after = split_at(words[1:], "as", last=True)
        if not after:
            raise Problem("Remember it as what? Try: remember 10 as score")
        self.assign(plain_name(after), before)

    def list_with_items(self, words):
        """'a list called colours with red, green and blue', 'a list of fruits: apple, pear'.
        Returns True if that's what it was."""
        for i, w in enumerate(words):
            if w.word in ("with", "containing", "holding") or w.after.endswith(":"):
                name = list_name(words[:i] if w.word in ("with", "containing", "holding")
                                 else words[:i] + [Word(w.raw.rstrip(":"))])
                items = list_items(words[i + 1:])
                if not name or not items:
                    return False
                self.new_list(name)
                for item in items:
                    self.add_to(item, name)
                return True
        return False

    def new_variable(self, words):
        """'a variable called score' (it starts at 0), 'a number named lives set to 3'.
        Returns True if that's what it was."""
        i = starts_with(words, "a new", "a", "an", "new")
        if [w.word for w in words[i:i + 2]] not in [[noun, how] for noun in ("variable", "number", "counter", "value")
                                                    for how in ("called", "named")]:
            return False
        rest = words[i + 2:]
        start = next((k for k in range(1, len(rest)) if starts_with(rest[k:], *STARTING_AT)), len(rest))
        name = plain_name(rest[:start])
        value = rest[start + starts_with(rest[start:], *STARTING_AT):] or [Word("0")]
        self.assign(name, value)
        self.made_just_now = name
        return True

    def new_list(self, name):
        var = self.find(name)
        if var is None:
            self.new_var(name, "list")
        elif var.kind.startswith("list"):
            self.empty_list(name)
        else:
            raise Problem(f"'{said(name)}' already holds something that isn't a list. Pick another name.")

    def do_add(self, words):
        if self.text_saying(words[1:]):                         # "add a message saying hi"
            return self.do_write([words[0]] + self.text_saying(words[1:]))
        left, spot = spot_at_end(words[1:], self.kind_of)
        if spot and left and not about_window(left):            # "add hi in red to the right of the window"
            return self.write_described(words[0], words[1:], left)
        before, after = split_at(words[1:], "to", "onto", "into", last=True)
        if not after or not before:
            raise Problem("Add what to what?")
        front = starts_with(after, "the front of", "the start of", "the beginning of", "the top of")
        end = starts_with(after, "the end of", "the back of", "the bottom of")
        after = after[front or end:]
        if file_name(after):
            return self.save_file(before, file_name(after), ADD_TO_FILE)
        self.add_to(before, plain_name(after), at_front=bool(front))

    do_append = do_add

    def add_to(self, value_words, name, at_front=False):
        var = self.find(name)
        if var is None:
            raise Problem(f"I don't know '{said(name)}' yet. Make it first: make a list called {said(name)}, "
                          f"or set {said(name)} to 0")
        node = self.value_or_text(value_words) if var.kind.startswith("list") or var.kind == "text" \
            else self.amount(value_words)
        if var.kind.startswith("list"):
            kind = self.emitter.emit(node)
            if kind == "timer":
                self.a.call("elapsed")
                kind = "decimal"
            if kind == "yes/no":
                kind = "number"
            if kind.startswith("list"):
                raise Problem("I can only add one thing at a time to a list.")
            if var.kind == "list":
                var.kind = "list of " + kind
            self.emitter.convert(kind, item_kind(var.kind))
            self.a.mov(RCX, RAX)
            self.a.address(RAX, var.place)
            self.a.call("push_front" if at_front else "push")
        elif var.kind == "text" and self.is_amount(node):
            self.add_to_text(name, node)
        elif var.kind == "text":
            self.store(name, self.emitter.emit(("join", ("name", name), node)))
        else:
            self.store(name, self.emitter.emit(("maths", "add", ("name", name), node)))

    def is_amount(self, node):
        """A number, or a name holding one: what 'add 1 to best' adds."""
        if node[0] == "name":
            return self.kind_of(node[1]) in ("number",) + DECIMALS
        return node[0] in ("number", "decimal", "maths", "random", "round", "count")

    def add_to_text(self, name, node):
        """'add 1 to best' when best is text (from a file or an answer): if it holds a number,
        add to it ('5' becomes '6'); otherwise put the number on the end ('hi' becomes 'hi1')."""
        a = self.a
        join, number, done = a.new_label("add_join"), a.new_label("add_number"), a.new_label("add_done")
        self.emitter.emit(("name", name))
        a.load(RCX, RAX)                       # how long it is
        a.op("test", RCX, RCX)
        a.jump_if(EQUAL, join)
        a.load_byte(RDX, RAX, 8)               # its first letter: a digit or a minus sign?
        a.op_n("cmp", RDX, ord("-"))
        a.jump_if(EQUAL, number)
        a.op_n("sub", RDX, ord("0"))
        a.op_n("cmp", RDX, 9)
        a.jump_if(ABOVE, join)
        a.label(number)
        self.store(name, self.emitter.emit(("maths", "add", ("name", name), node)))
        a.jump(done)
        a.label(join)
        self.store(name, self.emitter.emit(("join", ("name", name), node)))
        a.label(done)

    def amount(self, words):
        """How much to add or take away: '5', 'bonus times 2', or '5 points' (the word after is a label)."""
        try:
            return read_value(words, self.kind_of)
        except Problem:
            number, end = read_number(words, 0)
            if number is None or end != len(words) - 1 or self.kind_of(words[-1].word):
                raise
            return ("decimal", number) if isinstance(number, float) else ("number", number)

    def do_put(self, words):
        rest = words[1:]
        if self.text_saying(rest):                              # "put text on it that says hi"
            return self.do_write([words[0]] + self.text_saying(rest))
        left, spot = spot_at_end(rest, self.kind_of)
        if spot and left and not about_window(left):            # "put purple at the right side of the screen"
            return self.write_described(words[0], rest, left)
        if about_window(rest):
            return self.window_action(words)
        for spot, front in (("at the front of", True), ("on the front of", True), ("at the start of", True),
                            ("at the beginning of", True), ("at the top of", True),
                            ("on the end of", False), ("at the end of", False), ("on the back of", False),
                            ("at the bottom of", False), ("onto", False), ("on", False)):
            parts = spot.split()
            for i in range(1, len(rest)):
                if [w.word for w in rest[i:i + len(parts)]] == parts:
                    return self.add_to(rest[:i], plain_name(rest[i + len(parts):]), at_front=front)
        before, after = split_at(rest, "in", "into", last=True)
        if after and file_name(after):
            return self.save_file(before, file_name(after), REPLACE_FILE)
        if after and before:
            var = self.find(plain_name(after))
            if var and var.kind.startswith("list"):            # "put apple in fruits"
                return self.add_to(before, var.name)
            return self.assign(plain_name(after), before)
        raise Problem("Put it where?")

    def write_described(self, verb, rest, what):
        """Write what's said at the spot in rest. 'red text saying hi' -> 'hi in red'; just 'red text'
        asks what it says."""
        if rest[:len(what)] != what:                            # "put at the top hello"
            return self.do_write([verb] + rest)
        spot = rest[len(what):]
        said = [w.word for w in what]
        for i, w in enumerate(said):
            if w in TEXT_WORDS and i + 1 < len(said) and said[i + 1] in ("saying", "reading", "that"):
                says = i + 2 + (said[i + 1] == "that" and i + 2 < len(said) and said[i + 2] in ("says", "reads"))
                if says < len(said):
                    style = [x for x in what[:i] if x.word not in ("a", "an", "some", "the")]
                    return self.do_write([verb] + what[says:] + ([Word("in")] + style if style else []) + spot)
        style = [x for x in what[:-1] if x.word not in ("a", "an", "some", "the")]
        if said[-1] in TEXT_WORDS and self.only_style(style):
            colour = " ".join(x.text for x in style)
            raise Problem(f"What should the {colour + ' ' if colour else ''}{said[-1]} say? Try: "
                          f"{verb.text} \"hello\" in {colour or 'red'} {' '.join(x.raw for x in spot)}")
        return self.do_write([verb] + what + spot)

    def text_saying(self, words):
        """'red text on it that says hi' -> the words to write: 'hi in red'. None if it isn't that.
        Where it goes may come before the saying: 'text at the top saying hi', 'a note in the window that reads hi'."""
        said = [w.word for w in words]
        i = next((i for i, w in enumerate(said) if w in TEXT_WORDS), None)
        if i is None:
            return None
        style = [x for x in words[:i] if x.word not in ARTICLES + ("some",)]
        if not self.only_style(style):
            return None
        for j in range(i + 1, len(said)):
            n = starts_with(words[j:], *SAYING)
            if not n:
                continue
            where, what = words[i + 1:j], words[j + n:]
            spot = read_spot(where, self.kind_of) if where else None
            if not what or not (spot or all(w.word in ON_IT for w in where)):
                return None
            return what + ([Word("in")] + style if style else []) + (where if spot else [])
        return None

    def only_style(self, words):
        """Are these words nothing but colours and styles: 'bold red', 'light blue'?"""
        w, j = [x.word for x in words] + [None], 0
        while j < len(words):
            found = colour_at(w, j) or ((None, 1) if w[j] in STYLES or w[j] in BIG else None)
            if not found:
                return False
            j += found[1]
        return True

    def do_push(self, words):
        before, after = split_at(words[1:], "onto", "on", "to", "into", last=True)
        if not after or not before:
            raise Problem("Push what onto which list? Try: push name onto names")
        self.add_to(before, plain_name(after))

    def do_take(self, words):
        before, after = split_at(words[1:], "from", last=True)
        if after is None:
            raise Problem("Take it from where?")
        before = before[:len(before) - ends_with(before, "away")]
        before = before[starts_with(before, "away"):]          # "take away 1 from lives"
        name = plain_name(after)
        var = self.find(name)
        if var and var.kind.startswith("list"):
            first = any(w.word == "first" for w in before)
            return self.remove_item("first" if first else "last", name)
        self.subtract(before, name)

    def do_subtract(self, words):
        before, after = split_at(words[1:], "from", last=True)
        if not after or not before:
            raise Problem("Subtract what from what? Try: subtract 1 from lives")
        self.subtract(before, plain_name(after))

    def subtract(self, value_words, name):
        if self.find(name) is None:
            raise Problem(f"I don't know '{said(name)}' yet. Set it first: set {said(name)} to 10")
        node = self.amount(value_words)
        self.store(name, self.emitter.emit(("maths", "sub", ("name", name), node)))

    def do_increase(self, words):
        before, after = split_at(words[1:], "by")
        name = plain_name(before)
        if self.find(name) is None:
            raise Problem(f"I don't know '{said(name)}' yet. Set it first: set {said(name)} to 0")
        node = ("maths", "add" if words[0].word == "increase" else "sub",
                ("name", name), self.amount(after) if after else ("number", 1))
        self.store(name, self.emitter.emit(node))

    do_decrease = do_increase

    def do_remove(self, words):
        rest = words[1:]
        if file_name(rest):
            return self.delete_file(file_name(rest))
        before, after = split_at(rest, "from", "of", last=True)
        which = [w.word for w in before or []]
        if after and ("first" in which or "last" in which):
            return self.remove_item("first" if "first" in which else "last", plain_name(after))
        if after and before:
            var = self.find("_".join(w.word or "" for w in after[starts_with(after, *ARTICLES):]))
            if var and var.kind in ("number",) + DECIMALS:      # "remove 3 from score"
                return self.subtract(before, var.name)
            if var and var.kind.startswith("list"):
                raise Problem(f"I can only remove the first or the last from a list, like: "
                              f"remove the first from {said(var.name)}")
        raise Problem("Remove what?")

    def remove_item(self, which, name):
        var = self.find(name)
        if var is None or not var.kind.startswith("list"):
            raise Problem(f"'{said(name)}' isn't a list. Make one first: make a list called {said(name)}")
        kind = item_kind(var.kind)
        self.emitter.emit_default(kind)
        self.a.mov(RCX, RAX)
        self.a.address(RAX, var.place)
        self.a.call("remove_first" if which == "first" else "remove_last")
        self.set_it(kind)

    # ---- files ----

    def do_save(self, words):
        before, after = split_at(words[1:], "to", "in", "into", last=True)
        if after and file_name(after) and before:
            return self.save_file(before, file_name(after), REPLACE_FILE)
        if words[0].word in ("store", "keep") and after and before:
            return self.assign(plain_name(after), before)
        before, after = split_at(words[1:], "as", last=True)
        if after and before:                                   # "ask a number and save it as guess"
            if file_name(after):
                return self.save_file(before, file_name(after), REPLACE_FILE)
            return self.assign(plain_name(after), before)
        if len(words) > 2 and words[1].word in ("to", "in", "into") and file_name(words[2:]):
            raise Problem(f"Save what? Try: save score to {file_name(words[2:])}")
        if len(words) == 1:
            raise Problem("Save what, and where? Try: save score to best.txt")
        raise Problem("Save it where?")

    do_store = do_keep = do_save

    def save_file(self, value_words, name, how, written=False):
        """Save a value, or plain words ('save hello world to notes.txt'), in a file.
        written: it came from 'write ... to a file', so names in the words are filled in, as write does."""
        a = self.a
        try:
            node = read_value(value_words, self.kind_of)
        except Problem:
            if [w.word for w in value_words] in (["everything"], ["all"], ["them"], ["this"], ["stuff"],
                                                 ["all", "of", "it"], ["the", "game"], ["my", "game"]):
                raise Problem(f"Save which thing? Name it, like: save score to {name}")
            node = None if written else self.value_or_text(value_words)
        if node is None:
            self.text_value(value_words, None)
            kind = "text"
        else:
            kind = self.emitter.emit(node)
        if kind.startswith("list"):
            a.set(RCX, {"number": 0, "decimal": 1, "quotient": 1}.get(item_kind(kind), 2))
            a.address(RDX, a.text("\n"))
            a.call("list_to_text")
        else:
            self.emitter.text(kind)
        a.mov(RCX, RAX)
        a.address(RAX, a.text(name))
        a.set(RDX, how)
        a.call("file_save")

    def do_load(self, words):
        rest = words[1:]
        spot = next((i for i, w in enumerate(rest) if file_name([w])), None)
        if spot is None:
            raise Problem("Load which file? Try: load best.txt as best")
        name = file_name(rest[spot:spot + 1])
        before, after = rest[:spot], rest[spot + 1:]
        before = before[:len(before) - ends_with(before, "from the file", "from file", "from", "the file", "file")]
        after = after[starts_with(after, "as", "into", "called", "named"):]
        target = self.load_target(after) if after else self.load_target(before) if before else "it"
        self.load_file(name, target)

    def load_target(self, words):
        """Where a file goes: 'best', 'high score', or a list: 'a list called names', 'the list names'."""
        name = list_name(words[starts_with(words, "the"):])
        if name:
            self.new_list(name)
            return name
        return plain_name(words)

    do_open = do_read = do_get = do_load

    def load_file(self, name, target):
        a = self.a
        var = self.find(target) if target != "it" else None
        if var is None and target != "it":
            var = self.new_var(target, "text")
        kind = var.kind if var else "text"
        missing, done, keep = a.new_label("no_file"), a.new_label("loaded"), a.new_label("keep")
        a.address(RAX, a.text(name))
        a.call("file_load")
        a.op("test", RAX, RAX)
        a.jump_if(EQUAL, missing)
        if kind.startswith("list"):
            a.address(RCX, var.place)
            a.set(RDX, 10)
            a.set(R8, 1 if item_kind(kind) == "number" else 0)
            a.call("split")
            a.jump(done)
        else:
            self.emitter.convert("text", kind)
            a.jump(keep)
        a.label(missing)
        starts = "at 0" if kind in ("number",) + DECIMALS else "empty"
        self.show(f"({name} doesn't exist yet, so {said(target)} starts {starts}.)\n")
        if kind.startswith("list"):
            self.empty_list(target)
            a.jump(done)
        else:
            self.emitter.emit_default(kind)
        a.label(keep)
        if var:
            self.store(target, kind)
        self.set_it(kind)
        a.label(done)

    def do_delete(self, words):
        name = file_name(words[1:])
        if not name:
            raise Problem("Delete which file? Try: delete best.txt")
        self.delete_file(name)

    do_erase = do_delete

    def delete_file(self, name):
        self.a.address(RAX, self.a.text(name))
        self.a.call("file_delete")

    def do_count(self, words):
        self.written = True
        """'count to 10', 'count from 1 to 10', 'count down from 10 to 1': shows each number."""
        rest = words[1:]
        down = any(w.word in ("down", "backwards", "backward") for w in rest)
        rest = [w for w in rest if w.word not in ("down", "up", "backwards", "backward")]
        if down and rest[:1] and rest[0].word == "from" and not any(w.word == "to" for w in rest):
            rest = rest + [Word("to"), Word("1")]              # "count down from 10"
        elif down and rest[:1] and rest[0].word == "to":
            rest = rest[1:] + [Word("to"), Word("1")]          # "count to 10 backwards"
        if rest[:1] and rest[0].word == "to":
            rest = [Word("1")] + rest
        elif rest[:1] and rest[0].word == "from":
            rest = rest[1:]
        loop = self.read_range("number", rest)
        if not loop or loop[2]:
            raise Problem("Count how? Try: count to 10, or count from 1 to 10")
        self.count_aloud(loop[1][1], loop[1][2])

    def count_aloud(self, low, high, same_line=False):
        """Show each number from low to high (or down to it), one per line, or on one line with spaces between
        (and no new line after the last)."""
        a = self.a
        first = a.reserve(8, "first_number")

        def show_number():
            if same_line:                       # a space before each number but the first
                skip = a.new_label("first")
                a.address(RCX, first)
                a.load(RAX, RCX)
                a.op("test", RAX, RAX)
                a.jump_if(EQUAL, skip)
                self.show(" ")
                a.label(skip)
                a.set(RAX, 1)
                a.address(RCX, first)
                a.store(RCX, 0, RAX)
            self.emitter.text(self.emitter.emit(("name", "number")))
            a.call("write_text")
            if not same_line:
                self.show("\n")
        if same_line:
            a.set(RAX, 0)
            a.address(RCX, first)
            a.store(RCX, 0, RAX)
        self.count_through("number", low, high, show_number)

    def do_repeat(self, words):
        raise Problem("Repeat how many times, and what?")


STARTERS = sorted(name[3:] for name in dir(Actions) if name.startswith("do_")) + \
    ["if", "for", "each", "every", "otherwise", "else", "while", "until", "forever", "loop"]


def help_text():
    """Every phrase pattern, as text for 'brick help'."""
    lines = ["Things you can say (one or more per line; join them with commas, 'then' or 'and'):", ""]
    shown = set()
    for verb, examples in EXAMPLES.items():
        if id(examples) in shown:
            continue
        shown.add(id(examples))
        same = [v for v, e in EXAMPLES.items() if e is examples and v != verb]
        lines.append(f"{verb}" + (f"  (also: {', '.join(same)})" if same else ""))
        lines += [f"    {example}" for example in examples]
    lines += ["", "Values: plus, minus, times (or x: 7 x 6), divided by, round x, length of x, first letter of x,",
              "    how many in list, first in list, item 2 of list, a random number from 1 to 6,",
              "    a random item from list, how long since t, the time, shout x, x as a number,",
              "    the second letter of x, the first word of x, how many words in x, the contents of notes.txt,",
              "    word backwards, the biggest in scores, the smallest in scores, the total of scores,",
              "    the average of scores, the biggest of a and b, name in capitals",
              "Checks: is, is not, is more than, is less than, is at least, contains, is in,",
              "    starts with, ends with, is empty, notes.txt exists, and, or, not",
              "Blocks: a line ending in ':' (repeat, if, for each, otherwise) takes the lines indented under it",
              "Colours: " + ", ".join(sorted(set(COLOURS))) + "  (in green, in light blue, on a blue background, in bold red)",
              f"    and {len(dictionary.of_kind('colour'))} more from the dictionary, like crimson, navy, teal and sea green",
              "Tips: put text in quotes to keep it exactly as typed: write \"high score\" score",
              "",
              f"The dictionary: {len(dictionary.entries())} more everyday words, each taken to its nearest meaning here:",
              "    scribble hello (write)  |  inquire your name (ask)  |  linger 2 seconds (wait)  |  halt (stop)",
              "    write hi in crimson  |  if score exceeds 10, ...  |  write hi at the top-left  |  wait 2 hours",
              "    turn green  |  turn the background blue  |  turn left  |  turn score into words  |  turn word backwards",
              "    each turn, ask a number ...  |  take 5 turns: ...  |  beep over and over  |  write hi thrice",
              "    Words inside what you write stay as typed. Your own words come first.",
              "    See them all: brick help dictionary   (or one group: brick help dictionary colours)"]
    return "\n".join(lines)
