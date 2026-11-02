"""The factory: brick's dictionary and textual universe, learning by themselves while brick runs.

Each round (every 5 seconds) it:
  makes      one made-up direction for a console program, often as loosely as people really type them
             ('bg red', 'type at left of the screen the words hi in teal'), into the sentence pool
             (texts/sentences.txt, which the dictionary feeder also reads)
  watches    for new or changed .brick files (from Save .brick in brick gui, or brick export) and takes
             every line of their programs as more directions to learn from
  proves     each direction by building it, and teaches the universe's memory the reading that built
             (see synchronicity.py): which idea each word was, and which ideas came together
  learns     words brick doesn't know: a WordNet synonym brick does know becomes a dictionary line
             (restate = repeat) or a universe link (backdrop is about the background). Each one must build
             the same program as its synonym, then every test must pass, or it's taken out again.
  practises  on broken, errored paragraphs from the scrambler (scrambler.py), whose right answer it
             knows: what brick reads right strengthens the memory; what it misreads steers the memory
             toward the reading that's right; what it refuses, it tries to learn the missing words for,
             kept only if the mess then builds exactly the right program
  leaves     what it couldn't settle for a person to decide: the Decisions tab in brick gui (outliers.py,
             texts/factory/unsure.txt)

It runs while brick runs (brick gui, or a program running in the terminal) and stops with it.
brick factory always keeps it running all the time instead; brick factory off stops that.

    python3 factory.py                        run here and show what it does (Ctrl+C to stop)
    python3 factory.py make 200               add 200 directions to the sentence pool, then stop
    python3 factory.py learn game.brick       learn from these files now, then stop
"""
import fcntl
import glob
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import conceptnet  # noqa: E402
import dictionary  # noqa: E402
import outliers  # noqa: E402
import scrambler  # noqa: E402
import synchronicity  # noqa: E402
import universe  # noqa: E402
from actions import STARTERS  # noqa: E402
from compiler import Compiler  # noqa: E402
from expressions import Problem  # noqa: E402

POOL = os.path.join(HERE, "texts", "sentences.txt")
EXAMPLES = os.path.join(HERE, "texts", "examples")
FOLDER = os.path.join(HERE, "texts", "factory")
from wordnet import WORDNET  # noqa: E402
LEARNED = "# Learned\n# Added by the factory and the dictionary feeder: each one was checked to build exactly " \
          "the same program as its meaning.\n"
LINKS = ("show", "placing", "make", "clear", "wait", "text", "window", "background", "screen", "place", "size", "style")


from wordnet import FILES, senses, synonyms, synset  # noqa: E402


# ---------------- making directions ----------------

# Each slot is filled from these WordNet senses: (word, part of speech, which senses to take).
# Only senses that fit console programs; "show" sense 0 gives demo/exhibit/present, not "prove".
SEEDS = {
    'show': [('write', 'v', [0, 1]), ('show', 'v', [0, 3]), ('display', 'v', [0]), ('print', 'v', [0, 1]),
             ('type', 'v', [0]), ('echo', 'v', []), ('announce', 'v', [0])],
    'ask': [('ask', 'v', [0, 2])],
    'wait': [('wait', 'v', [0, 1]), ('pause', 'v', [0, 1]), ('linger', 'v', [0])],
    'read': [('read', 'v', [0, 3]), ('load', 'v', [0])],
    'save': [('save', 'v', [1]), ('store', 'v', [0]), ('record', 'v', [0])],
    'delete': [('delete', 'v', [0, 1]), ('remove', 'v', [0, 2]), ('erase', 'v', [0])],
    'repeat': [('repeat', 'v', [0, 1, 3])],
    'stop': [('stop', 'v', [1]), ('quit', 'v', [0]), ('finish', 'v', [0, 2])],
    'clear': [('clear', 'v', [0, 4]), ('wipe', 'v', [0])],
    'count': [('count', 'v', [0, 3])],
    'sort': [('sort', 'v', [1]), ('arrange', 'v', [0])],
    'add': [('add', 'v', [0, 1, 3]), ('append', 'v', [0])],
    'total': [('add', 'v', [4])],
    'exceed': [('exceed', 'v', [0, 1, 2])],
    'greet': [('greet', 'v', [0]), ('welcome', 'v', [0])],
    'start': [('start', 'v', [0, 1]), ('begin', 'v', [0])],
    'vanish': [('disappear', 'v', [0, 1, 3]), ('fade', 'v', [0])],
    'put': [('put', 'v', [0]), ('place', 'v', [0]), ('move', 'v', [1])],
    'screen': [('screen', 'n', [2]), ('display', 'n', [0]), ('monitor', 'n', [0])],
    'file': [('file', 'n', [0]), ('document', 'n', [0])],
    'list': [('list', 'n', [0]), ('inventory', 'n', [0])],
    'message': [('message', 'n', [0]), ('note', 'n', [0]), ('greeting', 'n', [0])],
    'number': [('number', 'n', [0, 1, 4])],
    'word': [('word', 'n', [0]), ('term', 'n', [0])],
    'line': [('line', 'n', [4])],
    'name': [('name', 'n', [0])],
    'score': [('score', 'n', [0, 2]), ('tally', 'n', [0])],
    'menu': [('menu', 'n', [2])],
    'error': [('error', 'n', [0, 5])],
    'program': [('program', 'n', [0]), ('application', 'n', [3])],
    'big': [('big', 'a', [0])],
    'small': [('small', 'a', [0])],
    'quickly': [('quickly', 'r', [0])],
    'slowly': [('slowly', 'r', [0])],
    'carefully': [('carefully', 'r', [0])],
}

# Synonyms that fit the sense on paper but read badly in a direction to a program.
AWKWARD = {'indite', 'shew', 'ingeminate', 'numerate', 'enquire', 'drop a line', 'lay off', 'give up',
           'summate', 'tot', 'tote up', 'unclutter', 'intermit', 'class', 'assort', 'eviscerate',
           'figure', 'numeral', 'textual matter', 'mark', 'grade', 'CRT screen', 'data file',
           'computer menu', 'computer error', 'programme', 'set about', 'get down', 'get',
           'compose', 'denote', 'publish', 'expose', 'oppugn', 'call into question', 'break', 'lade',
           'laden', 'load up', 'hive away', 'lay in', 'put down', 'put in', 'salt away', 'stack away',
           'enter', 'take', 'withdraw', 'double', 'duplicate', 'reduplicate', 'replicate', 'pass over',
           'separate', 'set up', 'supply', 'affix', 'supplement', 'recognise', 'recognize', 'lead off',
           'set out', 'start out', 'proctor', 'show', 'papers', 'run', 'plan', 'applications programme',
           'easy', 'tot up', 'add on', 'add together', 'transcend', 'surmount', 'outgo', 'overstep',
           'displace', 'lay', 'pose'}

# Never put these in a sentence, whatever the dictionary says.
UNWANTED = set('''rape sex sexy kill killer murder suicide bitch whore slut bastard cock dick ass arse
damn hell drug drugs gun porn nude naked piss crap shit fag fuck bomb corpse death dead die penis
breast nigger negro jew gay lesbian queer homo'''.split())

PLACES = ['at the top', 'at the bottom', 'in the middle', 'at the top-left', 'at the bottom-right',
          'on the left side', 'on the right side', 'in the centre', 'near the top-right corner']
FILENAMES = ['notes.txt', 'scores.txt', 'names.txt', 'log.txt', 'todo.txt', 'words.txt', 'save.txt',
             'diary.txt', 'shopping.txt', 'results.txt']
VARIABLES = ['score', 'count', 'lives', 'total', 'level', 'guess', 'answer', 'age', 'points', 'steps']
SIDES = ['left', 'right', 'top', 'bottom', 'top-left', 'top-right', 'bottom-left', 'bottom-right']
WINDOW_SIZES = ['bigger', 'smaller', 'full screen', 'wider', '800 by 600', 'half the screen']
SPOTS = ['to the right of the window', 'to the left of the window', 'at the top of the window',
         'at the bottom of the window', 'in the middle of the window', 'in the corner of the screen']
LINKS_WORDS = ['First', 'Then', 'After that', 'Next', 'Now', 'Once that is done', 'Straight after']
# How people really type: short forms, extra words, and none of the small words
SHORT = {'seconds': 'secs', 'second': 'sec', 'minutes': 'mins', 'background': 'bg', 'please': 'pls',
         'you': 'u', 'message': 'msg', 'number': 'num', 'colour': 'color', 'centre': 'center'}
BEFORE = ['ok', 'now', 'just', 'can you', 'pls', 'quick', 'hey', 'can u', 'i want to']
AFTER = ['pls', 'ok', 'now', 'thx', 'real quick', 'rn']


def load_slots():
    slots = {}
    for slot, seeds in SEEDS.items():
        words = set()
        for word, pos, wanted in seeds:
            words.add(word)
            offsets = senses(word, pos)
            for k in wanted:
                if k < len(offsets):
                    words.update(synset(offsets[k], pos)[0])
        slots[slot] = sorted(w for w in words if w not in AWKWARD)
    return slots


def load_colours():
    """Colour names: everything under 'chromatic colour' in WordNet, three levels down."""
    colours, todo, seen = set(), [(senses('chromatic color', 'n')[0], 0)], set()
    while todo:
        offset, depth = todo.pop()
        if offset in seen:
            continue
        seen.add(offset)
        words, pointers = synset(offset, 'n')
        colours.update(w.lower() for w in words if ' ' not in w and not w.endswith('ness'))
        if depth < 3:
            todo.extend((target, depth + 1) for symbol, target, _ in pointers if symbol == '~')
    colours -= {'chromatic', 'complementary', 'pastel', 'blond', 'blonde', 'drab', 'dun'}
    return sorted(colours | {'red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'white'})


def load_plain_words(pos, limit=6000):
    """Common single words of one part of speech, for the text programs show."""
    words = []
    with open(os.path.join(WORDNET, 'index.' + FILES[pos])) as index:
        for line in index:
            if line.startswith(' '):
                continue
            fields = line.split()
            word, tagged = fields[0], int(fields[5 + int(fields[3])])
            # How often the word turned up in WordNet's tagged sample text: everyday words
            # ("lantern", "quiet") turn up, "lepidopterology" doesn't.
            if (word.isalpha() and 3 <= len(word) <= 9 and tagged >= 3 and word not in UNWANTED
                    and not (pos == 'n' and word.endswith('s'))):
                words.append(word)
    random.shuffle(words)
    return words[:limit]


def third_person(verb):
    """'top' -> 'tops', 'outmatch' -> 'outmatches', 'go past' -> 'goes past'."""
    first, _, rest = verb.partition(' ')
    if first.endswith(('s', 'x', 'z', 'ch', 'sh', 'o')):
        first += 'es'
    elif first.endswith('y') and first[-2] not in 'aeiou':
        first = first[:-1] + 'ies'
    else:
        first += 's'
    return f'{first} {rest}'.strip()


class Maker:
    def __init__(self):
        self.slots = load_slots()
        self.colours = load_colours()
        self.nouns = load_plain_words('n')
        self.adjectives = load_plain_words('a')
        self.verbs = load_plain_words('v')

    def pick(self, slot):
        return random.choice(self.slots[slot])

    def phrase(self):
        """A bit of text for a program to show: 'hello', 'quiet lantern', 'the river is open'."""
        kind = random.random()
        if kind < 0.2:
            return random.choice(['hello', 'hi there', 'good morning', 'goodbye', 'well done',
                                  'game over', 'try again', 'you win', 'welcome back', 'press enter'])
        if kind < 0.6:
            return f'{random.choice(self.adjectives)} {random.choice(self.nouns)}'
        if kind < 0.8:
            return random.choice(self.nouns)
        return f'the {random.choice(self.nouns)} is {random.choice(self.adjectives)}'

    def text(self):
        words = self.phrase()
        return f'"{words}"' if random.random() < 0.4 else words

    def colour(self):
        return random.choice(self.colours)

    def var(self):
        return random.choice(VARIABLES)

    def direction(self):
        """One direction to a console program."""
        p, t, c, v = self.pick, self.text, self.colour, self.var
        n = random.randint(1, 20)
        secs = random.choice(['1 second', f'{random.randint(2, 10)} seconds', 'half a second',
                              'a moment', 'a minute'])
        f = random.choice(FILENAMES)
        side = random.choice(['left', 'right', 'top', 'bottom'])
        templates = [
            lambda: f'{p("show")} {t()}',
            lambda: f'{p("show")} {t()} in {c()}',
            lambda: f'{p("show")} {t()} {random.choice(PLACES)} of the {p("screen")}',
            lambda: f'{p("show")} {t()} {random.choice(PLACES)} in {c()}',
            lambda: f'{p("ask")} for their {p("name")} and {p("greet")} them',
            lambda: f'{p("ask")} the user for a {p("number")} and call it {v()}',
            lambda: f'{p("wait")} {secs} and then {p("show")} {t()}',
            lambda: f'{p("wait")} {secs}',
            lambda: f'{p("clear")} the {p("screen")}',
            lambda: f'{p("clear")} the {p("screen")} and {p("show")} {t()} in {c()}',
            lambda: f'{p("repeat")} {n} times: {p("show")} {t()}',
            lambda: f'{p("repeat")} this {n} times',
            lambda: f'if {v()} {third_person(p("exceed"))} {n} then {p("show")} {t()}',
            lambda: f'when {v()} reaches {n}, {p("stop")} the {p("program")}',
            lambda: f'{p("add")} {random.randint(1, 5)} to {v()}',
            lambda: f'{p("total")} {v()} and {v()} and {p("show")} the result',
            lambda: f'{p("count")} the {p("word")}s in {f}',
            lambda: f'{p("read")} every {p("line")} of {f} and {p("show")} it {p("slowly")}',
            lambda: f'{p("save")} the {p("score")} in {f}',
            lambda: f'{p("save")} {t()} to {f}',
            lambda: f'{p("delete")} the last {p("line")} of {f}',
            lambda: f'{p("sort")} the {p("list")} and {p("show")} it',
            lambda: f'{p("add")} {t()} to the {p("list")}',
            lambda: f'{p("show")} a {p("menu")} with {random.randint(2, 6)} choices',
            lambda: f'if the {p("file")} is missing, {p("show")} an {p("error")} in {c()}',
            lambda: f'{p("show")} a {p("big")} {p("message")} {random.choice(PLACES)}',
            lambda: f'{p("show")} {t()} {p("quickly")} and then {p("wait")} {secs}',
            lambda: f'change the colour to {c()}',
            lambda: f'turn the text {c()}',
            lambda: f'{p("start")} a timer and {p("show")} it every second',
            lambda: f'every {secs}, {p("add")} 1 to {v()} and {p("show")} {v()}',
            lambda: f'{p("ask")} "what is your favourite {random.choice(self.nouns)}?" and {p("save")} the answer in {f}',
            lambda: f'{p("stop")} when the user types {random.choice(["quit", "exit", "stop", "bye"])}',
            lambda: f'{p("read")} the {p("number")} from {f} and {p("show")} it in {c()}',
            lambda: f'pick a random {p("number")} from 1 to {n * 5} and {p("show")} it',
            lambda: f'let the user guess the {p("number")}, and {p("show")} "too {p("big")}" or "too {p("small")}"',
            lambda: f'{p("show")} {t()} one letter at a time, {p("slowly")}',
            lambda: f'{p("carefully")} {p("delete")} {f} and {p("show")} {t()}',
            # the window, its background, and text that comes and goes
            lambda: f'{p("put")} the window on the {random.choice(SIDES)} side of the screen',
            lambda: f'{p("put")} window at {random.choice(SIDES)} side of screen and make the background {c()}',
            lambda: f'{p("put")} the window on the {random.choice(SIDES)} and {p("show")} {t()} in {c()}',
            lambda: f'after {secs} {p("put")} the window on the {random.choice(SIDES)} and turn the background {c()}',
            lambda: f'make the window {random.choice(WINDOW_SIZES)}',
            lambda: f'make the window {random.choice(WINDOW_SIZES)} and {p("show")} {t()} {random.choice(SPOTS)}',
            lambda: f'set the title to {t()}',
            lambda: f'make the background {c()}',
            lambda: f'turn the background {c()} and {p("show")} {t()} in {c()}',
            lambda: f'{p("put")} {t()} {random.choice(SPOTS)}',
            lambda: f'{p("put")} {t()} in {c()} {random.choice(PLACES)} of the {p("screen")}',
            lambda: f'add {c()} text saying {self.phrase()} {random.choice(SPOTS)}',
            lambda: f'add {c()} text {random.choice(SPOTS)} and make it {p("vanish")} after {secs}',
            lambda: f'{p("show")} {t()} in {c()} {random.choice(SPOTS)} and make it {p("vanish")} after {secs}',
            lambda: f'{p("show")} {t()} and then make it {p("vanish")}',
            lambda: f'{p("show")} {t()} after {secs}',
            lambda: f'hide the {p("message")} after {secs}',
            lambda: f'also {p("show")} {t()} {random.choice(PLACES)} in {c()}',
            # jumbled, the way people type when they're in a hurry
            lambda: f'{p("put")} text at {side} side of screen with {c()} color',
            lambda: f'can you {p("put")} text at the {side} side of the screen in the color {c()} and make it say {self.phrase()}',
            lambda: f'{p("show")} at {side} of the screen the words {self.phrase()} in {c()}',
            lambda: f'{self.phrase()} in {c()}',
            lambda: f'{c()} {self.phrase()}',
            lambda: f'{self.phrase()} {p("show")}',
            lambda: f'{self.phrase()} x{random.randint(2, 5)}',
            lambda: f'{random.randint(2, 9)} secs wait',
            lambda: f'wait {random.randint(2, 9)} secs then {self.phrase()}',
            lambda: f'after {random.randint(2, 9)} secs {self.phrase()}',
            lambda: f'bg {c()}',
            lambda: f'{c()} background',
            lambda: f'text {c()}',
            lambda: f'window {side}',
            lambda: f'{p("screen")} clear',
            lambda: f'{side} side of screen {p("show")} {self.phrase()} in {c()}',
        ]
        return random.choice(templates)()

    def sentence(self):
        s = self.direction()
        if random.random() < 0.5:
            return loosen(s)
        return s[0].upper() + s[1:] + random.choice(['.', '.', '.', '!', ''])

    def paragraph(self):
        """A small program told as a few directions in a row."""
        steps = [self.direction() for _ in range(random.randint(3, 6))]
        if random.random() < 0.5:
            return random.choice([' then ', '; ', ', then ']).join(loosen(step) for step in steps)
        links = random.sample(LINKS_WORDS[1:], len(steps) - 2) + ['Finally']
        out = [f'First, {steps[0]}.']
        out += [f'{link}, {step}.' for link, step in zip(links, steps[1:])]
        return ' '.join(out)

    def entry(self, paragraphs=0.25):
        return self.paragraph() if random.random() < paragraphs else self.sentence()


def loosen(direction):
    """Say it the way people type when they don't care: no small words, short forms, extra words."""
    words = []
    for word in direction.lower().split():
        if word in ('the', 'a', 'an', 'of') and random.random() < 0.5:
            continue
        words.append(SHORT.get(word, word) if random.random() < 0.5 else word)
    said = ' '.join(words)
    if random.random() < 0.3:
        said = f'{random.choice(BEFORE)} {said}'
    if random.random() < 0.2:
        said = f'{said} {random.choice(AFTER)}'
    return said


def directions_in(entry):
    """A pool entry as the lines of a small program: 'First, x. Then, y.' -> x / y."""
    if not entry.startswith('First, '):
        return [entry]
    parts = re.split(r'(?:^|\.\s+)(?:First|Then|After that|Next|Now|Once that is done|Straight after|Finally), ',
                     entry.rstrip('.'))
    return [p for p in parts if p.strip()]


# ---------------- building, as the factory sees it ----------------

class Builder:
    """Builds text with scratch copies of your words, so trying things never changes them."""

    def __init__(self):
        self.folder = tempfile.mkdtemp(prefix="brick-factory-")

    def build(self, text, by_itself=False, words=None):
        """The program's bytes, or the Problem's message (a str). by_itself: without the universe's help.
        words: a mywords.txt to start from (a copy is used)."""
        mine = os.path.join(self.folder, "mywords.txt")
        if os.path.exists(mine):
            os.remove(mine)
        if words and os.path.isfile(words):
            shutil.copy(words, mine)
        compiler = Compiler(mine, ask_user=lambda question: "no")
        try:
            return compiler.compile_text(text) if by_itself else compiler.compile(text)
        except Problem as problem:
            return str(problem)
        except Exception as error:                  # brick tripped up: that's a message too
            return f"Line 1: {text}\n    (brick tripped up: {type(error).__name__}: {error})"

    def trying(self, path, line):
        """Build with one more line in dictionary.txt or universe.txt, in scratch copies."""
        return Trial(self, path, line)


class Trial:
    def __init__(self, builder, path, line):
        self.builder, self.path, self.line = builder, path, line

    def __enter__(self):
        module = dictionary if self.path == dictionary.PATH else universe
        self.module, self.saved = module, module.PATH
        copy = os.path.join(self.builder.folder, os.path.basename(self.path))
        shutil.copy(self.path, copy)
        with open(copy, "a", encoding="utf-8") as f:
            f.write(f"\n{self.line}\n")
        module.PATH = copy
        dictionary.clear()
        return self.builder

    def __exit__(self, *problem):
        self.module.PATH = self.saved
        dictionary.clear()


# ---------------- the factory ----------------

class Factory:
    def __init__(self, quiet=False):
        os.makedirs(FOLDER, exist_ok=True)
        self.quiet = quiet
        self.builder = Builder()
        self.memory = synchronicity.Memory()
        self.state = self.load_state()
        self.maker = None
        self.added = []                  # (file, line) learned since the last check
        self.checker = scrambler.Checker()
        self.tally = {"right": 0, "wrong": 0, "refused": 0}
        with open(POOL, encoding="utf-8", errors="replace") if os.path.isfile(POOL) else open(os.devnull) as f:
            self.pool = set(line.strip() for line in f)

    def load_state(self):
        try:
            with open(os.path.join(FOLDER, "state.json"), encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = {}
        for path, line in state.get("pending", []):     # stopped before they were checked: take them out
            remove_line(path, line)
        return {"bricks": state.get("bricks", {}), "tried": set(state.get("tried", [])),
                "unsure": set(state.get("unsure", [])), "turn": state.get("turn", 0)}

    def save(self):
        with open(os.path.join(FOLDER, "state.json"), "w", encoding="utf-8") as f:
            json.dump({"bricks": self.state["bricks"], "tried": sorted(self.state["tried"])[-20000:],
                       "unsure": sorted(self.state["unsure"])[-5000:], "pending": self.added,
                       "turn": self.state.get("turn", 0)}, f)
        self.memory.save()

    def say(self, message):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {message}"
        with open(os.path.join(FOLDER, "log.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if not self.quiet:
            print(message, flush=True)

    # ---- where directions come from ----

    def make(self):
        if self.maker is None:
            self.maker = Maker()
        entry = self.maker.entry()
        self.add_to_pool([entry])
        return directions_in(entry)

    def add_to_pool(self, entries):
        new = [e for e in (e.strip() for e in entries) if e and e not in self.pool]
        if new:
            with open(POOL, "a", encoding="utf-8") as f:
                f.write("\n".join(new) + "\n")
            self.pool.update(new)

    def new_bricks(self, folders):
        """Programs in .brick files that are new or changed since last time -> [(path, source)]."""
        found = []
        for folder in folders:
            for path in sorted(glob.glob(os.path.join(folder, "*.brick"))):
                when = os.path.getmtime(path)
                if self.state["bricks"].get(path) != when:
                    self.state["bricks"][path] = when
                    found.append((path, source_of(path)))
        return found

    # ---- learning ----

    def digest(self, text, where):
        """Learn from a program (a few lines): prove what builds, learn words for what doesn't."""
        lines = [line.strip() for line in text.splitlines()]
        by_itself = self.builder.build(text, by_itself=True)
        if not isinstance(by_itself, bytes):          # brick can't read it alone (even if the universe can):
            self.learn_words(text, by_itself, where)  # learn the words, so next time it reads it directly
        result = self.builder.build(text)
        if isinstance(result, bytes):
            for line in lines:
                if line and not line.startswith("#"):
                    self.prove(line)
        else:
            failing = {int(n) for n in re.findall(r"^Line (\d+): ", result, re.MULTILINE)}
            for number in sorted(failing):
                message = message_for(result, number)
                if " first" in message:          # 'set it first', 'show something first': it needs the rest
                    continue                     # of a program, not more words
                if 0 < number <= len(lines) and lines[number - 1] not in self.state["unsure"]:
                    self.state["unsure"].add(lines[number - 1])
                    outliers.add(lines[number - 1], message, source=where)

    def prove(self, line):
        """Teach the memory the reading of this one-direction line that builds the same program as the line."""
        directions = universe.analyse(line)
        if len(directions) != 1:
            return
        want = self.builder.build(line)
        if not isinstance(want, bytes):
            return
        for reading in universe.readings(directions[0]):
            for way in universe.tell(reading):
                if self.builder.build(way, by_itself=True) == want:
                    self.memory.observe(reading.roles())
                    return

    def learn_words(self, text, problem, where):
        """Words brick couldn't read in the text: find a synonym it knows, and check it means the same."""
        unknown = re.findall(r"I don't know (?:how to |what )?'([^']+)'", problem)
        for word in dict.fromkeys(w.lower() for w in unknown):
            if word in self.state["tried"] or not re.fullmatch(r"[a-z][a-z-]*", word) or word in UNWANTED:
                continue
            self.state["tried"].add(word)
            if word in STARTERS or word in universe.universe().words or dictionary.by_first_word().get(word):
                continue
            found = []          # (the line to add, its file, the program it builds)
            for synonym in synonyms(word):
                line, path = link_for(word, synonym)
                if not line:
                    continue
                swapped = self.builder.build(re.sub(rf"\b{re.escape(word)}\b", synonym, text, flags=re.IGNORECASE))
                if not isinstance(swapped, bytes):
                    continue
                with self.builder.trying(path, line) as trial:
                    if trial.build(text) == swapped:
                        found.append((line, path, swapped))
            if not found:
                continue
            if len({program for _, _, program in found}) > 1:
                self.say(f"unsure: '{word}' could mean " + " or ".join(line for line, _, _ in found))
                outliers.add(word, "this word could mean more than one thing", could_be=[line for line, _, _ in found],
                             source=where)
                continue
            line, path, _ = found[0]
            self.added.append((path, line))
            self.save()                              # pending until checked, in case brick stops first
            add_line(path, line)
            self.say(f"learned: {line}    (from {where})")

    # ---- practice: scrambled paragraphs with known right answers ----

    def practise(self):
        mess, said, tidy = scrambler.paragraph()
        how, missed = self.checker.check(mess, said, tidy)
        if how is None:
            return
        self.tally[how] += 1
        with open(os.path.join(FOLDER, "scrambled.txt"), "a", encoding="utf-8") as f:
            f.write(f"{'✓' if how == 'right' else '✗'} {mess}\n" + ("" if how == "right" else f"    meant: {' then '.join(tidy)}\n"))
        if how == "right":
            for messy, meant in zip(said, tidy):
                self.steer(messy, meant)
        for messy, meant, what in missed:
            if self.learn_toward(messy, meant) or self.steer(messy, meant, times=3):
                continue
            if messy not in self.state["unsure"]:
                self.state["unsure"].add(messy)
                outliers.add(messy, "brick refused it" if what == "refused" else "brick read it as something else",
                             meant=meant, source="the scrambler")
        if sum(self.tally.values()) % 20 == 0:
            self.say("practised on 20 scrambled paragraphs: {right} read right, {wrong} misread, {refused} refused"
                     .format(**self.tally))
            self.tally = {"right": 0, "wrong": 0, "refused": 0}

    def revisit(self, count=2):
        """Work through what's waiting for a person anyway: a person deciding only makes it faster.
        An outlier brick now reads right (or builds, if nobody knows what it meant) leaves the list."""
        waiting = outliers.entries()
        if not waiting:
            return
        self.state["turn"] = self.state.get("turn", 0) % len(waiting)
        for entry in (waiting * 2)[self.state["turn"]:self.state["turn"] + count]:
            line, meant = entry["line"], entry.get("meant")
            if entry["could be"]:
                continue                                    # a word with two meanings: that takes a person
            if meant:
                self.learn_toward(line, meant) or self.steer(line, meant)
                settled = self.builder.build(line) == self.builder.build(meant, by_itself=True)
            else:
                settled = isinstance(self.builder.build(line), bytes)
            if settled:
                outliers.remove(entry["id"])
                outliers.note(f"settled by brick itself: '{line}'")
                self.say(f"settled by itself: '{line}'")
        self.state["turn"] += count

    def steer(self, messy, meant, times=1):
        """Teach the memory the reading of a messy direction that makes the right program. False if none does."""
        directions = universe.analyse(messy)
        want = self.builder.build(meant, by_itself=True)
        if len(directions) != 1 or not isinstance(want, bytes):
            return False
        for reading in universe.readings(directions[0]):
            for way in universe.tell(reading)[:3]:
                if self.builder.build(way, by_itself=True) == want:
                    for _ in range(times):
                        self.memory.observe(reading.roles())
                    return True
        return False

    def learn_toward(self, messy, meant):
        """Words in the mess that brick doesn't know: try what WordNet and ConceptNet say they mean, and keep
        the one that makes the mess build exactly the right program."""
        want = self.builder.build(meant, by_itself=True)
        if not isinstance(want, bytes):
            return False
        world = universe.universe()
        unknown = [w for w in dict.fromkeys(re.findall(r"[a-z][a-z-]+", messy.lower()))
                   if w not in meant.lower().split() and w not in world.words and w not in STARTERS
                   and not dictionary.by_first_word().get(w) and w not in UNWANTED]
        for word in unknown:
            if word in self.state["tried"]:
                continue
            self.state["tried"].add(word)
            candidates = synonyms(word) + [other for other, _ in conceptnet.web().stands_for(word, strong=1.0)]
            for candidate in dict.fromkeys(candidates):
                line, path = link_for(word, candidate)
                if not line:
                    continue
                with self.builder.trying(path, line) as trial:
                    if trial.build(messy) == want:
                        self.added.append((path, line))
                        self.save()
                        add_line(path, line)
                        self.say(f"learned: {line}    (from the scrambler: '{messy}')")
                        return True
        return False

    def check(self):
        """After learning: the tests and examples that passed before must still pass, or the new lines come out."""
        if not self.added:
            return
        found = broken(self.builder)
        if found:
            for path, line in self.added:
                remove_line(path, line)
            blamed = found - broken(self.builder)    # what passes without the new lines: they broke it
            if blamed:
                self.say("took back " + ", ".join(line for _, line in self.added) +
                         " (broke " + ", ".join(sorted(os.path.basename(b) for b in blamed)) + ")")
            else:                                    # it was broken already: the new lines can stay
                for path, line in self.added:
                    add_line(path, line)
        self.added = []
        self.save()

    def feed(self, rounds=20):
        """brick feeder: a batch of learning now -> a plain-English report."""
        before = sum(1 for _ in open(os.path.join(FOLDER, "log.txt"), encoding="utf-8")) \
            if os.path.isfile(os.path.join(FOLDER, "log.txt")) else 0
        for _ in range(rounds):
            self.digest("\n".join(self.make()), "the sentence maker")
            self.practise()
        self.check()
        self.save()
        with open(os.path.join(FOLDER, "log.txt"), encoding="utf-8") as f:
            news = [line.split("  ", 1)[1].rstrip() for line in list(f)[before:] if "  " in line]
        learned = [n for n in news if n.startswith("learned: ")]
        taken = [n for n in news if n.startswith("took back ")]
        lines = [f"The dictionary feeder (brick's own): {rounds} made-up directions and {rounds} scrambled paragraphs.",
                 f"Learned {len(learned)} new " + ("word." if len(learned) == 1 else "words.")]
        lines += [f"  {n[len('learned: '):]}" for n in learned]
        lines += [f"Took back: {n[len('took back '):]}" for n in taken]
        lines.append("Each was checked to build the same program as what it stands for, and every test still passes.")
        return "\n".join(lines)

    # ---- running ----

    def round(self, folders):
        for line in heard():                          # lines brick fixed (or couldn't) in your real builds
            self.add_to_pool([line])
            self.digest(line, "your programs")
        for path, text in self.new_bricks(folders):
            self.say(f"reading {path}")
            self.add_to_pool(line for line in text.splitlines() if not line.strip().startswith("#"))
            self.digest(text, os.path.basename(path))
        self.digest("\n".join(self.make()), "the sentence maker")
        self.practise()
        self.revisit()
        self.check()
        self.save()


def broken(builder):
    """The test files that fail and the examples that don't build."""
    env = dict(os.environ, BRICK_FACTORY="off", BRICK_MEMORY="off")
    found = {t for t in glob.glob(os.path.join(HERE, "tests", "test_*.py"))
             if subprocess.run([sys.executable, t], env=env, capture_output=True).returncode != 0}
    for example in glob.glob(os.path.join(EXAMPLES, "*.txt")):
        with open(example, encoding="utf-8") as f:
            words = os.path.join(os.path.dirname(example), "mywords.txt")
            if not isinstance(builder.build(f.read(), words=words), bytes):
                found.add(example)
    return found


def teach(line):
    """A person chose this line ('restate = repeat', or 'background: backcloth' for the universe): add it,
    and keep it only if every test and example that passed before still passes. -> (ok, message)."""
    path = universe.PATH if re.match(r"^[a-z ]+: ", line) and " = " not in line else dictionary.PATH
    builder = Builder()
    add_line(path, line)
    found = broken(builder)
    if found:
        remove_line(path, line)
        blamed = found - broken(builder)
        if blamed:
            return False, f"'{line}' broke {', '.join(sorted(os.path.basename(b) for b in blamed))}, so it's out again."
        add_line(path, line)
    return True, f"Taught: {line}. Every test still passes."


HEARD = os.path.join(FOLDER, "heard.txt")


def hear(lines):
    """Lines from a real build that brick had to fix, or couldn't: the factory learns from them next round."""
    os.makedirs(FOLDER, exist_ok=True)
    with open(HEARD, "a", encoding="utf-8") as f:
        f.write("".join(line.strip() + "\n" for line in lines if line.strip()))


def heard():
    """The lines heard since last time (and forget them)."""
    if not os.path.isfile(HEARD):
        return []
    os.replace(HEARD, HEARD + ".taken")
    with open(HEARD + ".taken", encoding="utf-8") as f:
        lines = list(dict.fromkeys(line.strip() for line in f if line.strip()))
    os.remove(HEARD + ".taken")
    return lines[:50]


def after_build(text, compiler, problem=None, where="your program"):
    """After a real build: what brick fixed goes to the factory to keep; what it couldn't fix goes on the
    Decisions desk too (it still works on those by itself)."""
    lines = text.split("\n")
    fixed = [lines[int(n) - 1] for n in re.findall(r"^Note: line (\d+) read as: ", "\n".join(compiler.notes),
                                                     re.MULTILINE) if 0 < int(n) <= len(lines)]
    stuck = [(int(n), message_for(problem, int(n))) for n in re.findall(r"^Line (\d+): ", problem or "", re.MULTILINE)]
    stuck = [(lines[n - 1].strip(), said) for n, said in stuck if 0 < n <= len(lines) and " first" not in said]
    for line, said in stuck:
        outliers.add(line, said, source=where)
    hear(fixed + [line for line, _ in stuck])


def source_of(path):
    """The program in a .brick file: its SOURCE section, as it was written."""
    lines, inside = [], False
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("== "):
                if inside:
                    break
                inside = line.startswith("== SOURCE")
            elif inside:
                found = re.match(r"\s*\d+ \| ?(.*)$", line.rstrip("\n"))
                if found:
                    lines.append(found.group(1))
    return "\n".join(lines)


def message_for(problem, number):
    lines = problem.split("\n")
    for k, line in enumerate(lines):
        if line.startswith(f"Line {number}: ") and k + 1 < len(lines):
            return lines[k + 1].strip()
    return ""


def link_for(word, synonym):
    """The line that would teach brick the word through this synonym -> (line, the file it goes in)."""
    if synonym in STARTERS or synonym in dictionary.colour_table():
        return f"{word} = {synonym}", dictionary.PATH
    ideas = [idea for idea in LINKS if idea in universe.universe().words.get(synonym, ())]
    if ideas:
        return f"{ideas[0]}: {word}", universe.PATH
    return None, None


class Writing:
    """One writer at a time for dictionary.txt and universe.txt (the factory, and a person deciding)."""

    def __enter__(self):
        os.makedirs(FOLDER, exist_ok=True)
        self.lock = open(os.path.join(FOLDER, "writing.lock"), "w")
        fcntl.flock(self.lock, fcntl.LOCK_EX)

    def __exit__(self, *problem):
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()


def add_line(path, line):
    with Writing():
        add_line_now(path, line)


def add_line_now(path, line):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    heading = LEARNED if path == dictionary.PATH else "# Learned\n# Added by the factory: each one built the same program as the word it stands for.\n"
    if "\n# Learned\n" not in text:
        text = text.rstrip("\n") + "\n\n" + heading
    write_whole(path, text.rstrip("\n") + "\n" + line + "\n")


def remove_line(path, line):
    with Writing():
        remove_line_now(path, line)


def remove_line_now(path, line):
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    for k in range(len(lines) - 1, -1, -1):
        if lines[k] == line:
            del lines[k]
            break
    write_whole(path, "\n".join(lines))


def write_whole(path, text):
    """Write the file in one go, so stopping brick halfway can never leave half a dictionary."""
    with open(path + ".new", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".new", path)
    dictionary.clear()


# ---------------- running alongside brick ----------------

def only_one():
    """Hold the factory's lock, so two factories never learn at once. False if one is running already."""
    os.makedirs(FOLDER, exist_ok=True)
    global _lock
    _lock = open(os.path.join(FOLDER, "lock"), "w")
    try:
        fcntl.flock(_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def running():
    """Is a factory running right now?"""
    if not os.path.isfile(os.path.join(FOLDER, "lock")):
        return False
    with open(os.path.join(FOLDER, "lock")) as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
        except OSError:
            return True


def start_alongside(folder):
    """Start the factory in the background for as long as this brick runs (brick gui, a program running
    here). Nothing happens with BRICK_FACTORY=off, or when one is running already."""
    if os.environ.get("BRICK_FACTORY") == "off" or running():
        return None
    import atexit
    os.makedirs(FOLDER, exist_ok=True)
    log = open(os.path.join(FOLDER, "output.txt"), "a")
    process = subprocess.Popen([sys.executable, os.path.abspath(__file__), "--while", str(os.getpid()),
                                "--watch", folder, "--quiet"], stdin=subprocess.DEVNULL, stdout=log,
                               stderr=log, start_new_session=True,
                               env=dict(os.environ, BRICK_NEURAL="off"))   # background practice: no graphics card
    atexit.register(process.terminate)
    return process


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main(args=None):
    args = sys.argv[1:] if args is None else list(args)
    if args[:1] == ["make"]:
        maker = Maker()
        count = int(args[1]) if len(args) > 1 else 100
        Factory(quiet=True).add_to_pool(maker.entry() for _ in range(count))
        print(f"Added up to {count} directions to {POOL}")
        return
    if not only_one():
        print("The factory is already running.")
        return
    if args[:1] == ["learn"]:
        factory = Factory()
        for path in args[1:]:
            text = source_of(path) if path.endswith(".brick") else open(path, encoding="utf-8").read()
            factory.digest(text, os.path.basename(path))
        factory.check()
        factory.save()
        return
    parent = int(args[args.index("--while") + 1]) if "--while" in args else None
    folders = [HERE, EXAMPLES]
    if "--watch" in args:
        folders.append(os.path.abspath(args[args.index("--watch") + 1]))
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))   # brick closed
    factory = Factory(quiet="--quiet" in args)
    factory.say("factory started" + (f" alongside brick (process {parent})" if parent else ""))
    try:
        while parent is None or alive(parent):
            factory.round(list(dict.fromkeys(folders)))
            time.sleep(5)
    except KeyboardInterrupt:
        pass
    factory.save()
    factory.say("factory stopped")


if __name__ == "__main__":
    main()
