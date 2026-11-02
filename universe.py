"""brick's textual universe: reads a line brick couldn't, by what its words are about, and says it again
in brick's own words.

  analyse    the line's words and phrases, and where one direction ends and the next begins
  associate  each word or phrase to an idea, and that idea to wider ones (abstract on abstract):
             pink -> colour -> look, left -> place -> where, scribble -> write -> show -> action
  relate     what goes with what: a look and a where belong to the thing being shown, 'make it say hello'
             gives it its words, and 'text' with a place straight after it (and no other words) is
             itself the word to show
  tell       it again in brick's words: write hello in pink at the right side of the screen

The words for each idea are in texts/universe.txt. brick only asks the universe about a line it can't read
itself, so every line that worked before builds exactly as it did.
"""
import difflib
import itertools
import os
import re
import shutil
import tempfile

import conceptnet
import dictionary
import neural
import review
import synchronicity

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texts", "universe.txt")
ACTIONS = ("show", "make", "clear", "wait")
UNITS = {"s": "second", "sec": "second", "secs": "second", "second": "second", "seconds": "second",
         "min": "minute", "mins": "minute", "minute": "minute", "minutes": "minute",
         "ms": "millisecond", "millisecond": "millisecond", "milliseconds": "millisecond",
         "hr": "hour", "hrs": "hour", "hour": "hour", "hours": "hour"}
ENDS = {",", ";", "then", "and then", "after that", "next"}       # where one direction ends and the next begins
MOST = 8                                                            # tellings tried for one line
STRUCTURE = {"look word", "by means of", "toward", "saying", "later", "times"}   # words that join, never shown
SIDES = {"left", "right", "top", "bottom", "middle", "centre", "center", "top-left", "top-right", "bottom-left",
         "bottom-right", "upper", "lower"}          # places that end the words to show even with no 'at' before them
THINGS = {"colour", "place", "window", "background", "screen", "size", "style"}
BORROWABLE = {"colour", "place", "show", "placing", "make", "clear", "wait", "window", "background", "screen",
              "size", "style", "time unit"}
SYMBOLS = {"colour", "style", "place", "thing", "surface", "action", "time unit", "size"}
# Any of those can also be read as plain words to show ('orange juice', 'write put', 'bg' as letters): no
# word is locked into one role. Which reading comes first is up to the bias: the universe's links, what
# the memory has seen together, and ConceptNet's weights.


# ---------------- associate: words to ideas, ideas to wider ideas ----------------

class Universe:
    def __init__(self, path=None):
        path = PATH if path is None else path
        self.words = {}            # word or phrase -> its ideas
        self.wider = {}            # idea -> the ideas it's a kind of
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                if ":" in line:
                    idea, words = (part.strip() for part in line.split(":", 1))
                    for word in filter(None, (w.strip().lower() for w in words.split(","))):
                        self.words.setdefault(word, set()).add(idea)
                elif re.search(r" is an? ", line):
                    idea, wider = re.split(r" is an? ", line, maxsplit=1)
                    self.wider.setdefault(idea.strip(), set()).add(wider.strip())
        from actions import BIG, COLOURS, STARTERS, colour_words      # here: actions uses the compiler
        for name in colour_words() | set(dictionary.colour_table()):
            self.words.setdefault(name, set()).add("colour")
        for colour in set(COLOURS) | colour_words():   # light blue, dark green, bright crimson
            for shade in ("light", "dark", "bright"):
                self.words.setdefault(f"{shade} {colour}", set()).add("colour")
        for word in BIG:                               # 'in big red letters': brick shows that as bold
            self.words.setdefault(word, set()).add("style")
        spots = {"top", "bottom", "left", "right", "middle", "centre", "center", "corner", "side"}
        for entry in dictionary.entries():             # the dictionary's places and times: 'far right', 'hrs'
            if not all(kind == "word" for kind, _ in entry.pattern):
                continue
            if entry.kind == "place" and set(entry.meaning.lower().replace("-", " ").split()) <= spots:
                self.words.setdefault(entry.key, set()).add("place")      # spots on the screen, not 'backwards'
            elif entry.kind == "time":
                self.words.setdefault(entry.key, set()).add("time unit")
        for entry in dictionary.entries():             # scribble = write: scribble is about showing too
            meant = self.words.get(entry.meaning.lower(), set()) & set(ACTIONS)
            if entry.kind == "action" and meant and all(kind == "word" for kind, _ in entry.pattern):
                self.words.setdefault(entry.key, set()).update(meant)
        for word in STARTERS:                          # ask, count, repeat ...: the universe leaves those alone
            self.words.setdefault(word, {"other action"})

    def about(self, ideas):
        """The ideas, and every wider idea they're a kind of."""
        found, todo = set(), list(ideas)
        while todo:
            idea = todo.pop()
            if idea not in found:
                found.add(idea)
                todo.extend(self.wider.get(idea, ()))
        return found


_universe, _read_when = None, None


def universe():
    global _universe, _read_when
    when = [(p, os.path.getmtime(p)) for p in (PATH, dictionary.PATH)]
    if _universe is None or when != _read_when:
        _universe, _read_when = Universe(PATH), when
    return _universe


# ---------------- analyse: the line's words and phrases ----------------

class Token:
    def __init__(self, text, ideas=(), quoted=False):
        self.text, self.word, self.ideas, self.quoted = text, text.lower(), set(ideas), quoted
        self.borrowed = set()       # ideas from a word ConceptNet says it stands for, used only as a last try
        self.spelled = None         # words brick knows that this could be a slip for ('wnidow': window)
        self.real = False           # ... though it's a real word too ('wit' for wait): only if that completes it

    def __repr__(self):
        return f"{self.text}{sorted(self.ideas)}"


_analysed = {}


def analyse(line):
    """The line as directions (see read_directions), remembered: the same line is analysed many times
    over in one build, and its analysis only changes when the universe, the dictionary or the memory do."""
    key = (line, id(universe()), synchronicity.off(), os.environ.get("BRICK_MEMORY"))
    if key not in _analysed:
        if len(_analysed) > 4000:
            _analysed.clear()
        _analysed[key] = read_directions(line)
    return [list(direction) for direction in _analysed[key]]


def read_directions(line):
    """The line as directions, each a list of tokens: a word or phrase with its ideas.
    A direction ends at a comma, semicolon, 'then', a word ending in . ! or ?, a lone '...' or '-', 'and'
    before a new action, or where a second action starts while one is under way ('wait 3 s the words hi')."""
    world = universe()
    words = []
    line = positions(line)
    for w in re.findall(r'"[^"]*"|[^\s,;]+|[,;]', line):
        if w.startswith('"'):
            words.append(w)
            continue
        bare = w.rstrip(".!?:") or w
        if bare in ("...", "..", "-", "--", "–", "—") or not bare.strip(".!?-"):
            words.append(";")                                  # '...' or '-' on its own: a new direction
            continue
        words.append("and" if bare == "&" else bare)
        if w != bare and re.search(r"[.!?]$", w) and not re.fullmatch(r"\d+\.\d+", w):
            words.append(";")                                  # 'yellow.' 'screen!': that direction ends here
    tokens, i = [], 0
    while i < len(words):
        if words[i].startswith('"'):
            tokens.append(Token(words[i], quoted=True))
            i += 1
            continue
        for n in range(min(4, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + n])
            if any(w.startswith('"') for w in words[i:i + n]):
                continue
            ideas = world.words.get(phrase.lower())
            if n == 1 and not ideas:
                count = re.fullmatch(r"x(\d+)|(\d+)x", phrase.lower())
                ideas = {"number"} if re.fullmatch(r"\d+(\.\d+)?", phrase) else {"count"} if count else set()
                if phrase in (",", ";"):
                    ideas = {"end"}
            if ideas or n == 1:
                token = Token(phrase, world.about(ideas))
                if not ideas and phrase.isalpha():
                    token.borrowed = world.about(borrowed(phrase.lower()))
                    token.spelled = spelled(phrase.lower())
                    if not token.spelled and len(phrase) >= 3 and real_word(phrase.lower()):
                        token.spelled, token.real = spelled(phrase.lower(), real=True), True
                doubled = tokens and token.word == tokens[-1].word and "end" not in (ideas or ()) and \
                    (ideas or token.spelled and not token.real) and not token.ideas & {"window", "background"}
                if not doubled:
                    tokens.append(token)                       # 'put put', 'hoold hoold': once is enough
                i += n
                break
    certain(tokens)
    merged = []
    for t in tokens:                          # 'tael tael color': once, keeping the copy that knows more
        if merged and t.word == merged[-1].word and not t.quoted and not t.ideas & {"window", "background"} and \
                (t.ideas or t.spelled and not t.real or
                                                                     merged[-1].spelled and not merged[-1].real):
            if t.spelled and not t.real and not (merged[-1].spelled and not merged[-1].real):
                merged[-1] = t
            continue
        merged.append(t)
    tokens = merged
    directions, current = [], []
    for k, token in enumerate(tokens):
        after = tokens[k + 1] if k + 1 < len(tokens) else None
        if token.word in ENDS or "end" in token.ideas or token.word == "and" and after and \
                after.ideas & {"action", "other action"}:
            directions.append(current)               # between separators, by_slots finds where one ends
            current = []
        else:
            current.append(token)
    found = []
    for d in [frame for direction in directions + [current] for frame in by_slots(direction)]:
        while d and d[0].ideas & {"chatter", "filler", "glue"} and not d[0].quoted:
            d = d[1:]                                         # 'um', 'so yeah' at the start
        while d and d[-1].ideas & {"chatter", "filler", "glue"} and not d[-1].quoted:
            d = d[:-1]                                        # 'lol', 'thanks', 'ok and' at the end
        if d:
            found.append(d)
    return found


def by_slots(tokens):
    """Cut a run-on direction where a second one starts: a direction has one action, one look, one place,
    one time, one count and one set of words to show, so a second of any of them starts the next direction
    ('on left saying hi purple put window at right': the window, after words already given, is the next).
    Lines with if, repeat, loops and the like are brick's own, and left whole."""
    if any(t.ideas & {"other action"} and not t.ideas & {"action"} for t in tokens[:1]) or \
            any(t.word in ("if", "when", "while", "until", "repeat", "each", "unless", "otherwise", "do") for t in tokens):
        return [tokens]
    world, original = universe(), tokens
    tokens = [Token(t.spelled[0], world.about(world.words[t.spelled[0]]))
              if t.spelled and len(t.spelled) == 1 and not t.real and
              world.words.get(t.spelled[0], {"other action"}) - {"other action"} else t for t in tokens]
    # cut as if slips were spelled right, when there's only one word they could be
    frames, current, filled, last = [], [], set(), None
    seen = []                                 # what's in the current direction, slips spelled right
    i = 0
    while i < len(tokens):
        slot, end = piece(tokens, i)
        if slot == "action" and not tokens[i].ideas & {"action"} and ("words" in filled or tokens[i].word == "for"
                                                                     and not (end < len(tokens) and tokens[end].word == "each")):
            slot = "words" if "words" in filled else "skip"     # 'lets go': go is a word; 'wait for 3 s': for joins
        before = [t for t in tokens[:i] if not t.ideas & {"glue"}]
        if slot == "thing" and before and "toward" in before[-1].ideas:
            slot = "skip"                     # 'in the window', 'on the screen': where, not the window to move
        kind = frame_kind(seen)
        if slot == "words" and kind == "wait" and not any(t.ideas & {"action"} for t in seen) and \
                any("wait" in universe().words.get(w, ()) for w in tokens[i].spelled or ()):
            slot = "action"                   # '1 scs wit': after a time, a slip for 'wait' is its verb
        rest = [t for t in tokens[end:] if not t.ideas & {"chatter", "filler", "glue", "end"}]
        if slot == "thing" and kind in ("window", "background") and tokens[i].ideas & {kind} and \
                (not complete(current) or not rest and seen and seen[-1].word == tokens[i].word):
            slot = "skip"                     # 'put window window right', 'gold background background': said twice
        described = kind == "colour" and slot == "words" and \
            [t for t in current if not t.ideas & {"chatter", "filler", "glue"}][-1].ideas & {"text"}
        cut = current and not described and (      # 'a blue text that says hi': the words describe that text
            slot not in ("skip",) and kind in TAKES and slot not in TAKES[kind] and
            not (kind == "wait" and "time" not in filled and slot == "words") or         # a wait has no words
                                                                                          # (but '2 secnds' may be its time)
            slot in filled and slot not in ("words", "skip", "text", "action") or
            slot == "action" and "action" in filled and not saying_since_verb(current) or
            slot == "words" and "words" in filled and last != "words" or
            slot == "thing" and "words" in filled or
            slot == "words" and "thing" in filled and last != "words" or      # 'window to right  hi there'
            slot == "words" and "words" not in filled and (verb_kind(current) == "wait" and "time" in filled or
                                                           verb_kind(current) == "clear") or   # 'wait 5 secs level up' 
            slot == "action" and "words" in filled and (clashes(tokens, end, filled) or
                                                         tokens[i].ideas & {"wait", "clear", "make"}) or
            slot == "action" and "words" not in filled and "action" not in filled and complete(current) and
            (not fits(tokens[i], current, tokens[end:]) or clashes(tokens, end, filled)))  # 'window right  make text white' 
            # 'welcome back pause 2 seconds': a wait after the words to show is the next direction
        if cut and slot == "action" and "action" not in filled and tokens[i].ideas & {"show", "placing"} and \
                not needs_verb(tokens, end):
            current += original[i:end]        # 'level up say  also text colour gold': say goes with level up
            frames.append(current)
            current, filled, last, seen = [], set(), None, []
            i = end
            continue
        if cut:
            carried = []                      # 'make bg navy x3 display hi': x3 goes with hi
            while slot == "action" and current and current[-1].ideas & {"count"} or \
                    slot == "look" and current and current[-1].ideas & {"text"}:     # 'text crimson'
                carried.insert(0, current.pop())
            if slot == "thing" and kind not in ("window", None) and "where" in filled:
                k = len(current)                   # 'text red left side window': 'left side' is the window's
                while k and (current[k - 1].ideas & {"place", "toward"} or current[k - 1].word in ("the", "of")):
                    k -= 1
                carried, current = current[k:], current[:k]
            frames.append(current)
            current, filled = carried, ({"count"} if any("count" in t.ideas for t in carried) else set())
            seen = [tokens[original.index(t)] for t in carried] if carried else []
        current += original[i:end]
        seen += tokens[i:end]
        if slot != "skip":
            filled.add(slot)
            last = slot
        i = end
    return [f for f in frames + [current] if f]


# what each kind of direction can take; anything else starts the next one ('4 secs wait in lime show hi')
TAKES = {"wait": {"time", "action"}, "clear": {"action", "text"},
         "window": {"thing", "where", "action", "size"}, "background": {"thing", "look", "action", "text"},
         "colour": {"text", "look", "action"}}


def frame_kind(current):
    """What kind of direction this is so far: 'wait', 'clear', 'window', 'background', 'colour', or None."""
    real = [t for t in current if not t.ideas & {"chatter", "filler", "glue"}]
    if not real:
        return None
    things = [t for k, t in enumerate(real) if t.ideas & {"window", "background"} and
              not (k and "toward" in real[k - 1].ideas)]                # 'in the window' is a place
    if any("window" in t.ideas for t in things) and not any(t.ideas & {"saying"} or t.quoted for t in real):
        return "window"
    if any("background" in t.ideas for t in things):
        return "background"
    kind = verb_kind(real)
    if kind in ("wait", "clear"):
        return kind
    d = relate(real)
    if not d.content and d.look and any("text" in t.ideas for t in real) and kind in (None, "make"):
        return "colour"                        # 'text red', 'make writing green'; but 'put red text' shows text
    if not d.content and d.long and not d.look and not d.where:
        return "wait"                          # '2 secs', waiting for its verb
    return None


def saying_since_verb(current):
    """Are we among the words to show, after 'saying' or 'the words' ('the words say hi': say is a word)?"""
    verbs = [k for k, t in enumerate(current) if t.ideas & {"action", "other action"}]
    return bool(verbs) and any("saying" in t.ideas for t in current[verbs[0]:])


def needs_verb(tokens, i):
    """Does what follows (up to the next verb) need a showing verb, or could it stand alone ('text colour
    gold', 'window left', 'bg red')?"""
    j = i
    while j < len(tokens) and not tokens[j].ideas & {"action", "other action"}:
        j += 1
    rest = [t for t in tokens[i:j] if not t.ideas & {"chatter", "filler", "glue"}]
    if not rest or j < len(tokens):
        return False                          # nothing, or it has a verb of its own further on
    d = relate(rest)
    return bool(d.content) or not tell(d)


def clashes(tokens, i, filled):
    """Would what follows (up to the next verb) fill a slot that's filled already, or be a window or
    background? Then a verb before it starts a new direction; otherwise it finishes this one."""
    first = True
    while i < len(tokens):
        slot, end = piece(tokens, i)
        if slot == "action":
            return False
        if slot == "thing":
            return first                      # 'put window right': the verb is the window's
        if slot in filled and slot not in ("skip", "text"):
            return True
        if slot != "skip":
            first = False
        i = end
    return False


def complete(tokens):
    """Is this a whole direction already, with nothing to show: 'window right', 'text color yellow'?"""
    real = [t for t in tokens if not t.ideas & {"chatter", "filler", "glue"}]
    if not real:
        return False
    d = relate(real)
    return not d.content and bool(tell(d))


def verb_kind(tokens):
    """What the direction's verb does: 'show', 'wait', 'clear', 'make', or None."""
    for t in tokens:
        for kind in ("wait", "clear", "make", "show"):
            if kind in t.ideas:
                return kind
    return None


def fits(verb, tokens, after=()):
    """Does this verb fit the direction so far ('put' a window, 'make' a background or colour, 'wait' a time)?
    after: what follows the verb ('make' fits a window only as 'make the window bigger')."""
    told = tell(relate([t for t in tokens if not t.ideas & {"chatter", "filler", "glue"}]))
    said = told[0] if told else ""
    if said.startswith("put the window") or said.startswith("make the window"):
        return bool(verb.ideas & {"placing"}) or bool(verb.ideas & {"make"}) and \
            any("size" in t.ideas for t in after[:3])
    if said.startswith(("set the background", "set the colour")):
        return bool(verb.ideas & {"make"})
    if said.startswith("wait"):
        return bool(verb.ideas & {"wait"})
    if said.startswith("clear"):
        return bool(verb.ideas & {"clear"})
    return bool(verb.ideas & {"show", "placing"})


def piece(tokens, i):
    """What kind of piece of a direction starts at tokens[i], and where it ends."""
    t = tokens[i]
    if t.quoted:
        return "words", i + 1
    if "saying" in t.ideas:
        j = i + 1
        while j < len(tokens) and not (j > i + 1 and stops_words(tokens, j)):
            j += 1
        return "words", j
    if "later" in t.ideas and number_and_unit(tokens, i + 1):
        return "time", number_and_unit(tokens, i + 1)[0]
    if number_and_unit(tokens, i):
        return "time", number_and_unit(tokens, i)[0]
    if "count" in t.ideas:
        return "count", i + 1
    if "number" in t.ideas and i + 1 < len(tokens) and "times" in tokens[i + 1].ideas:
        return "count", i + 2
    if look_at(tokens, i):
        end, look = look_at(tokens, i)
        return ("style" if look in ("bold", "italic", "italics", "underlined", "underline") or
                universe().words.get(look, set()) & {"style"} else "look"), end
    if where_at(tokens, i):
        return "where", where_at(tokens, i)[0]
    if t.ideas & {"action", "other action"}:
        return "action", i + 1
    if t.ideas & {"window", "background"}:
        return "thing", i + 1
    if t.ideas & {"text", "screen"}:
        return "text", i + 1
    if t.ideas & {"filler", "chatter", "glue", "it", "toward", "by means of", "becoming", "end"}:
        return "skip", i + 1
    return "words", i + 1


def stops_words(tokens, k):
    """Do the words to show (after 'saying') stop here, at a look, a place, a time, a count, a verb or quotes?"""
    t = tokens[k]
    if number_and_unit(tokens, k) or t.ideas & {"wait", "clear"} and (k + 1 == len(tokens) or
                                                                      number_and_unit(tokens, k + 1)):
        return True                           # '... welcome back pause 2 seconds': the words end at pause
    return bool(look_at(tokens, k) or where_at(tokens, k) and (t.ideas & {"toward"} or t.word in SIDES) or
                t.quoted or "count" in t.ideas or
                "later" in t.ideas and number_and_unit(tokens, k + 1) or
                "number" in t.ideas and k + 1 < len(tokens) and "times" in tokens[k + 1].ideas or
                t.ideas & {"show", "placing", "window", "background"})


def certain(tokens):
    """Slips that their place in the direction makes certain, even when they're real words or could be more
    than one word: next to 'color', 'bg' or 'text', or after 'in' or 'with', only a colour fits ('in tael
    color', 'tael bg', 'writing navvy': teal, navy); after a number, 'times' or a time ('5 ties'); the first
    word, or the last after the words to show, is the verb ('trn the bg navy': turn; '... hi there pint')."""
    if synchronicity.off():
        return
    world = universe()
    for k, t in enumerate(tokens):
        if t.ideas or t.quoted or not t.word.isalpha():
            continue
        candidates = t.spelled if t.spelled and not t.real else spelled(t.word, real=True) or []
        wanted = wanted_here(tokens, k)
        found = [w for w in candidates if world.words.get(w, set()) & wanted]
        if not wanted and any(x.ideas & {"action"} for x in tokens):    # it has its verb: not another one
            verbs = {"action", "other action"}
            found = [w for w in candidates if world.words.get(w, set()) and
                     not world.about(world.words[w]) & verbs]
            found = found if len(found) == 1 else []
        if not found and wanted & {"show"}:
            from actions import STARTERS
            found = [w for w in candidates if w in STARTERS and not world.words.get(w)]
        same = len({frozenset(world.words.get(w, ())) for w in found}) == 1    # color / colour: one meaning
        if found and same and (not t.real or wanted - {"show", "placing", "make", "clear", "wait"}
                               or k == 0 or k == len(tokens) - 1):
            t.spelled, t.real = found[:1], False


def wanted_here(tokens, k):
    """What kind of word fits at tokens[k], from its neighbours."""
    before = tokens[k - 1] if k else None
    after = tokens[k + 1] if k + 1 < len(tokens) else None
    things = {"text", "background"}
    if after and after.ideas & {"look word"} or before and before.ideas & {"look word", "by means of", "becoming"}:
        return {"colour"}
    if before and "colour" in before.ideas:
        return {"look word"}                                 # 'crimson coloor'
    if after and "colour" in after.ideas:
        return {"text", "background", "by means of", "becoming", "look word"}   # 'the wrtiing gold', 'wih orange'
    if before and "toward" in before.ideas:
        return {"place"}                                     # 'window on lfet'
    if after and after.ideas & things or before and before.ideas & things:
        return {"colour", "look word"}                       # 'bg coloor cyan', 'tael bg'
    if before and "number" in before.ideas:
        return {"times", "time unit"}
    if k == 0:
        return {"show", "placing", "make", "clear", "wait"}
    if k == len(tokens) - 1 and not any(x.ideas & {"action"} for x in tokens):
        return {"show", "placing"}                           # '... hi there pint': a showing verb, at the end
    return set()


def begins_another(current, token, after=None):
    """Does this token start a new direction, with no comma or 'then' before it? A second action while one
    is under way does ('clear screen print hi'), unless it's among the words to show ('the words say hi');
    so does an action after a direction that's complete without one ('text color white print hi'), and
    'the words' or 'saying' after a direction that isn't about showing ('wait 3 s the words hi').
    'for' only starts one as 'for each': in 'wait for 3 seconds' it belongs to the wait."""
    if token.word == "for" and not (after and after.word == "each"):
        return False
    acting = token.ideas & {"action", "other action"}
    # the direction's own action: a showing/making word anywhere, or a command word ('ask', 'go') only as
    # its first word; 'go' in 'the words lets go' is one of the words
    actions = [t for t in current if "action" in t.ideas] or \
        [t for t in current[:1] if "other action" in t.ideas]
    if not actions:
        if acting and current:                                # complete already? 'text color white', 'bg red'
            d, joined = relate(current), relate(current + [token])
            if not joined.content and tell(joined) and fits(token, current):
                return False                                  # '2 secs wait': the verb finishes this one
            return not d.content and bool(tell(d))
        return False
    showing = actions[0].ideas & {"show"}
    if any("saying" in t.ideas for t in current[current.index(actions[0]):]):
        return False                                          # in the middle of the words to show
    if acting and not (current and current[-1].ideas & {"it"}):
        return True
    return "saying" in token.ideas and not showing


_real = None


def real_word(word):
    """Is this an English word (WordNet or ConceptNet know it)? Then it isn't a slip, whatever it looks like."""
    global _real
    if _real is None:
        _real = set()
        folder = os.path.join(os.path.dirname(PATH), "sources", "wordnet")
        for kind in ("noun", "verb", "adj", "adv"):
            path = os.path.join(folder, f"index.{kind}")
            if os.path.isfile(path):
                with open(path, encoding="utf-8", errors="replace") as f:
                    _real.update(line.split(" ", 1)[0] for line in f if not line.startswith(" "))
    return word in _real                      # WordNet's everyday words; ConceptNet also knows rare ones ('wite')


def spelled(word, real=False):
    """A slip for exactly one word brick knows ('wnidow' -> window, 'piink' -> pink, 'cear' -> clear) ->
    that word, or None. Real English words are never respelled: 'good' stays good, not gold."""
    if len(word) < 3 or synchronicity.off() or real_word(word) and not real:
        return None
    from actions import STARTERS
    world = universe()
    small = {"filler", "glue", "toward", "becoming", "it", "saying", "chatter"}
    known = {w for w in world.words if " " not in w and len(w) >= 3 and world.words[w] - small} | set(STARTERS)
    most = 1 if len(word) < 7 else 2
    found = [w for w in known if abs(len(w) - len(word)) <= most and apart(word, w) <= most]
    best = min((apart(word, w) for w in found), default=None)
    core = core_words()                       # among ties, brick's own words before the dictionary's extras
    return sorted((w for w in found if apart(word, w) == best), key=lambda w: (w not in core, w))[:4] or None


_core = None


def core_words():
    """brick's own words: its built-in colours and action words, and the words written in universe.txt."""
    global _core
    if _core is None:
        from actions import COLOURS, STARTERS
        _core = set(COLOURS) | set(STARTERS)
        with open(PATH, encoding="utf-8") as f:
            for line in f:
                if ":" in line and not line.startswith("#"):
                    _core.update(w.strip().lower() for w in line.split(":", 1)[1].split(","))
    return _core


def apart(a, b):
    """How many slips apart two words are: a letter wrong, missing, extra, or two swapped."""
    d = [[i + j if not i * j else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


# ---------------- relate: what goes with what ----------------

class Direction:
    def __init__(self):
        self.action = None          # show, make, clear, wait, or other action (left as typed)
        self.things = []            # (idea, where in the tokens, the token)
        self.content = []           # the tokens of the words to show
        self.said = False           # were they given with 'saying', 'the words' or quotes?
        self.copied = False         # is the content the word 'text' itself?
        self.look = None            # 'pink', 'bold'
        self.where = None           # (the words as typed, the place words)
        self.later = None           # '5 seconds': after that long
        self.long = None            # '2 seconds': a wait that long
        self.count = None
        self.size = None
        self.starts = set()         # where each where-phrase starts, for 'text at the left ...'
        self.lost = False           # was a word like 'in' or 'to' left over? Then the line means more than this
        self.placing = False        # put, place: those need somewhere to put it
        self.follows = False        # does it come after another direction on the line ('wait 2 secs then hi')?
        self.action_word = None
        self.phrases = []           # the describing phrases as typed: 'with red color', 'at top side screen' ...

    def roles(self):
        """Each symbol in the reading as (word, the idea it was read as, was that one of the universe's links?)."""
        found = []
        if self.action:
            found.append((self.action_word, "placing" if self.placing else self.action, True))
        found += [(token.word, idea, True) for idea, _, token in self.things if not self.copied]
        if self.look:
            found.append((self.look, "style" if self.look in universe().words and "style" in
                          universe().words[self.look] else "colour", True))
        if self.where:
            found += [(place, "place", True) for place in self.where[1]]
        found += [(time.split()[1], "time unit", True) for time in (self.later, self.long) if time]
        if self.count:
            found.append(("times", "count", True))
        if self.said:
            found.append(("saying", "saying", True))
        # words to show are a plain guess, except 'text' standing for itself: that's one of the universe's rules
        found += [('"' if token.quoted else token.word, "words", self.copied) for token in self.content]
        return found


def number_and_unit(tokens, i):
    """'5 secs' at tokens[i] -> (where it ends, '5 seconds'), or None."""
    if i + 1 < len(tokens) and "number" in tokens[i].ideas and "time unit" in tokens[i + 1].ideas:
        unit = UNITS.get(tokens[i + 1].word, tokens[i + 1].word)
        return i + 2, f"{tokens[i].text} {unit}{'' if tokens[i].text == '1' else 's'}"
    return None


def look_at(tokens, i):
    """'in the color pink', 'with red color', 'pink', 'in bold' at tokens[i] -> (where it ends, the look), or None."""
    j = i
    if j < len(tokens) and tokens[j].ideas & {"by means of", "becoming"}:
        j += 1
    while j < len(tokens) and tokens[j].word in ("the", "a"):
        j += 1
    if j < len(tokens) and "look word" in tokens[j].ideas and "colour" not in tokens[j].ideas:
        j += 1
    if j < len(tokens) and tokens[j].ideas & {"colour", "style"}:
        look = tokens[j].text.lower()
        j += 1
        if j < len(tokens) and "look word" in tokens[j].ideas:
            j += 1
        return j, look
    return None


def positions(line):
    """Positions as people write them, said one way: 'x=20 y=20', 'x20 y20', '(20, 20)', 'at 20,20',
    'position 20 20' -> 'x 20 y 20' (x across, y down). Quoted words are left as they are."""
    parts = re.split(r'("[^"]*")', line)
    for k in range(0, len(parts), 2):
        p = parts[k]
        p = re.sub(r"\(\s*(\d+)\s*,\s*(\d+)\s*\)", r" x \1 y \2 ", p)                      # (20, 20)
        p = re.sub(r"\b(at|to|position|coordinates|coords|point)\s+(\d+)\s*,\s*(\d+)\b", r"\1 x \2 y \3", p, flags=re.I)
        p = re.sub(r"\b(position|coordinates|coords|point)\s+(\d+)\s+(\d+)\b", r"\1 x \2 y \3", p, flags=re.I)
        if re.search(r"\by\s*[=:]?\s*\d+", p, re.I) or re.search(r"\bx\s*[=:]\s*\d+", p, re.I):
            p = re.sub(r"\b([xy])\s*[=:]?\s*(\d+)\b", r"\1 \2", p, flags=re.I)              # x=20, x20, y: 20
        parts[k] = p
    return "".join(parts)


def coords_at(tokens, i):
    """'at the x 20 and y 20', 'y 3', 'position x 5 y 9' at tokens[i] -> (where it ends, 'at row 20 column 20'),
    or None. x is how far across (the column), y how far down (the row)."""
    j = i
    while j < len(tokens) and (tokens[j].ideas & {"toward", "glue"} and tokens[j].word != "and" or
                               tokens[j].word in ("position", "coordinates", "coords", "point")):
        j += 1
    led, found, end = j > i, {}, None
    while j + 1 < len(tokens) and tokens[j].word in ("x", "y") and tokens[j].word not in found and \
            "number" in tokens[j + 1].ideas:
        found[tokens[j].word] = tokens[j + 1].text
        j += 2
        end = j
        if j < len(tokens) and tokens[j].word in ("and", "&"):
            j += 1
    if not found or len(found) == 1 and not led:
        return None                           # '7 x 6' is maths: one axis only after 'at', 'to' or 'position'
    where = " ".join(w for w in (f"row {found['y']}" if "y" in found else "", f"column {found['x']}" if "x" in found else "") if w)
    return end, "at " + where


def where_at(tokens, i):
    """'at the right side of the screen', 'left', 'to the top' at tokens[i] -> (where it ends, words, places)."""
    if coords_at(tokens, i):                  # 'at the x 20 and y 20': a row and a column
        end, words = coords_at(tokens, i)
        return end, words, []
    j = i
    if j < len(tokens) and "toward" in tokens[j].ideas:
        j += 1
    places, end, of = [], None, False
    while j < len(tokens):
        if "place" in tokens[j].ideas:
            places.append(tokens[j].word)
            j += 1
            end = j
        elif tokens[j].word in ("the", "a") or tokens[j].word == "of" and places:
            of = of or tokens[j].word == "of"
            j += 1
        elif "surface" in tokens[j].ideas and places and (of or "window" not in tokens[j].ideas):
            # 'left side of the screen', 'top side screen'; but 'left side window' is the window to move
            j += 1
            end = j
            break
        else:
            break
    if not places:
        return None
    return end, " ".join(t.text for t in tokens[i:end]), places


def relate(tokens):
    d = Direction()
    i = 0

    def phrase_at(k):
        return look_at(tokens, k) or where_at(tokens, k) or number_and_unit(tokens, k + 1) and \
            "later" in tokens[k].ideas or "count" in tokens[k].ideas or \
            "number" in tokens[k].ideas and k + 1 < len(tokens) and "times" in tokens[k + 1].ideas or \
            d.action is None and tokens[k].ideas & {"show", "placing"}    # 'the words hi put red': put is the verb

    while i < len(tokens):
        t = tokens[i]
        later = "later" in t.ideas and number_and_unit(tokens, i + 1)
        if t.quoted:
            d.content.append(t)
            d.said = True
            i += 1
        elif "saying" in t.ideas:
            d.phrases.append(t.text)
            j = i + 1
            while j < len(tokens) and not (j > i + 1 and (phrase_at(j) or stops_words(tokens, j))):
                j += 1
            said = tokens[i + 1:j]
            while said and said[-1].ideas & {"chatter", "filler"} and not said[-1].quoted:
                said = said[:-1]                  # '... welcome back real quick': not part of the words
            d.content += said
            d.said = True
            i = j
        elif later:
            d.phrases.append(" ".join(x.text for x in tokens[i:later[0]]))
            i, d.later = later
        elif number_and_unit(tokens, i):
            i, d.long = number_and_unit(tokens, i)
        elif "number" in t.ideas and i + 1 < len(tokens) and "times" in tokens[i + 1].ideas:
            d.count = t.text
            i += 2
        elif "count" in t.ideas:
            d.count = re.sub(r"\D", "", t.word)
            d.phrases.append(t.text)          # 'x2': if brick shows that, it misread the line
            i += 1
        elif look_at(tokens, i):
            end, d.look = look_at(tokens, i)
            d.phrases.append(" ".join(x.text for x in tokens[i:end]))
            i = end
        elif where_at(tokens, i):
            d.starts.add(i)
            end, words, places = where_at(tokens, i)
            d.where = (words, places)
            if any("surface" in x.ideas for x in tokens[i:end]):       # 'at top side screen': not 'top of the hill'
                d.phrases.append(words)
            elif not places:                  # 'at the x 20 and y 20': brick showing that means it misread
                d.phrases.append(" ".join(x.text for x in tokens[i:end]))
            i = end
        elif t.ideas & {"other action"} and not t.ideas & {"action"} and d.content and not d.said:
            d.content.append(t)               # 'lets go put bottom': once the words have started, 'go' is a word
            i += 1
        elif t.ideas & {"action", "other action"} and d.action is None:
            d.action = "other action" if "other action" in t.ideas and "action" not in t.ideas else \
                next(a for a in ACTIONS if a in t.ideas)
            d.placing = "placing" in t.ideas
            d.action_word = t.word
            i += 1
        elif "thing" in t.ideas or "surface" in t.ideas:
            d.things.append((next(x for x in ("text", "window", "background", "screen") if x in t.ideas), i, t))
            i += 1
        elif "size" in t.ideas:
            d.size = t.text
            i += 1
        elif t.ideas & {"action", "other action"} and d.action and t.word != d.action_word:
            d.content.append(t)               # 'write see you soon': a second action word is one of the words
            i += 1
        elif t.ideas & {"filler", "it", "glue"} or t.ideas & {"action", "other action"} and "chatter" not in t.ideas:
            i += 1
        else:
            d.content.append(t)
            i += 1
    while d.content and not d.said and d.content[0].ideas & {"glue", "toward"}:
        gone = d.content.pop(0)               # (taken off first: 'lost or pop()' would skip the pop)
        d.lost = d.lost or "glue" not in gone.ideas
    while d.content and not d.said and d.content[-1].ideas & {"glue", "toward"}:
        gone = d.content.pop()
        d.lost = d.lost or "glue" not in gone.ideas
    if not d.content:                     # 'put text at the left side': no words given, so 'text' is the words
        for idea, k, token in d.things:
            if idea == "text" and k + 1 in d.starts:
                d.content, d.copied = [token], True
    return d


# ---------------- tell: say it again in brick's words ----------------

def tell(d):
    """Ways to say the direction in brick's words, the likeliest first. [] if it can't be told."""
    if d.action == "other action":
        return []
    before = f"after {d.later} " if d.later else ""
    after = f" {d.count} times" if d.count else ""
    things = {idea for idea, _, _ in d.things}
    if d.action == "wait" or d.long and not (d.content or things or d.look or d.action):
        return [f"{before}wait {d.long}"] if d.long else []
    if d.action == "clear" and not d.content:
        return [f"{before}clear the screen"]
    if "window" in things and not d.content:
        if d.where:
            words, places = d.where
            sides = [p for p in places if p not in ("side", "corner", "edge", "half")]
            return [before + "put the window " + w for w in
                    (f"on the {' '.join(sides)} side of the screen", at(words), f"at the {' '.join(sides)}")]
        return [f"{before}make the window {d.size}"] if d.size else []
    if "background" in things and d.look and not d.content:
        return [f"{before}set the background colour to {d.look}", f"{before}make the background {d.look}"]
    if "text" in things and d.look and not d.content and not d.where and d.action in (None, "make"):
        return [f"{before}set the colour to {d.look}"]
    if not d.content or things - {"text"} or d.action == "make" and not d.said:
        return []                     # 'set x to n plus 1', 'put the window somewhere nice': not for showing
    if d.action is None and not (d.said or d.look or d.where or d.count or d.later or d.follows) or \
            d.action is None and not d.said and slip(d.content[0].word):
        return []                     # 'wirte hello': nothing says it's words to show, so likely a slip
    if d.placing and not (d.said or d.look or d.where):
        return []                     # 'put x': put it where?
    if any(t.quoted for t in d.content) and not all(t.quoted for t in d.content):
        return []                     # 'restate 14 times: demonstrate "hi"': quoted words and loose ones
    if d.lost or "text" in things and not (d.said or d.look or d.where or d.copied):
        return []                     # 'write the biggest in word': telling it would drop words that matter
    plain = " ".join(t.text for t in d.content)
    shown = [f'"{plain}"'] if d.copied else [plain]    # quotes only for 'text' as the word itself: quoting
                                                        # anything else would hide what brick makes of it
    look = f" in {d.look}" if d.look else ""
    wheres = [""]
    if d.where:
        words, places = d.where
        wheres = [" " + at(words)] + ([f" at the {' '.join(places)} of the screen", f" at the {' '.join(places)}"]
                                      if places else [])
    told = []
    for words in shown:
        for where in wheres:
            told += [f"{before}write {words}{look}{where}{after}", f"{before}write {words}{where}{look}{after}"]
    return list(dict.fromkeys(told))


def slip(word):
    """Does this word look like a slip for an action word ('wirte' for write)?"""
    world = universe()
    actions = [w for w, ideas in world.words.items() if ideas & {"show", "make", "clear", "wait", "placing",
                                                                   "other action"} and " " not in w]
    return word not in world.words and not real_word(word) and \
        bool(difflib.get_close_matches(word, actions, n=1, cutoff=0.75))      # 'all' is a word, not a slip for 'call'


def at(words):
    """A where-phrase as brick likes it: 'to the left' -> 'at the left', 'left side' -> 'at the left side'."""
    first, _, rest = words.partition(" ")
    if first.lower() in ("at", "on", "in", "near"):
        return words
    if first.lower() in ("to", "towards", "toward", "by", "onto", "into"):
        return "at " + rest
    return "at " + words


def borrowed(word):
    """The ideas of a word ConceptNet firmly says this one is the same as, or a kind of: 'backcloth' ->
    backdrop -> background. Two steps at most: a kind of a kind of (abstract on abstract). A 'kind of'
    only lends what a thing is (a colour, a place), never an action: a monitor is a display, not 'show'."""
    if synchronicity.off():
        return set()
    world, web = universe(), conceptnet.web()
    for first, how in web.stands_for(word)[:8]:
        for other, how_again in [(first, how)] + web.stands_for(first)[:4]:
            lends = BORROWABLE if how in conceptnet.SAME and how_again in conceptnet.SAME else THINGS
            ideas = world.words.get(other, set()) & lends
            if ideas:
                return ideas
    return set()


def readings(tokens, follows=False):
    """The ways one direction can be read, the best fit first: as the universe's links say, and with each
    word that could be a symbol or plain words ('orange') taken as plain words. Synchronicity orders them:
    the reading whose symbols fit best with each other, and with what the factory has seen, comes first."""
    found, demoted = [], set()
    for k in [None] + [k for k, t in enumerate(tokens) if not t.quoted and t.ideas & SYMBOLS]:
        variant = tokens if k is None else tokens[:k] + [Token(tokens[k].text)] + tokens[k + 1:]
        d = relate(variant)
        d.follows = follows
        if k == 0 and tokens[0].ideas & {"action"}:
            demoted.add(id(d))                # directions start with their verb: 'show' first is likely 'show'
        if k is not None and any(t.ideas & STRUCTURE for t in d.content if not t.quoted):
            continue                  # 'with red color' isn't words to show: it's how they look
        found.append(d)
    if any(t.borrowed for t in tokens):                    # words read through ConceptNet
        d = relate([Token(t.text, t.borrowed) if t.borrowed else t for t in tokens])
        d.follows = follows
        found.append(d)
    slips = [k for k, t in enumerate(tokens) if t.spelled]
    if slips:                                              # slips read as the words they could be slips for:
        world = universe()                                 # each candidate, and the fit decides

        def respelled(k, word):
            return Token(word, world.about(world.words.get(word, {"other action"})))
        sure_slips = [k for k in slips if not tokens[k].real]          # true slips: 'afer', 'pirnt'
        bases = [dict(zip(sure_slips, combo)) for combo in
                 itertools.islice(itertools.product(*(tokens[k].spelled for k in sure_slips)), 16)]
        choices = [b for b in bases if b]                              # every way the true slips could go,
        choices += [{**b, k: other} for b in bases for k in slips if tokens[k].real   # each with a real word
                    for other in tokens[k].spelled]                    # respelled too: '1 scs wit' = wait 1 sec
        for choice in choices:
            d = relate([respelled(k, choice[k]) if k in choice else t for k, t in enumerate(tokens)])
            d.follows = follows
            if not any(tokens[k].real for k in choice) or not d.content and tell(d):
                found.append(d)               # a real word ('wit') only if that completes it: '1 scs wit'

    memory = synchronicity.memory()
    return sorted(found, key=lambda d: -(memory.fit(d.roles()) - (1.0 if id(d) in demoted else 0)))


def describing(line):
    """Phrases in the line that describe what to show rather than being it: 'with red color', 'the words',
    'after 5 secs', 'at the top of the screen' (a place on the screen, not 'at the top of the hill')."""
    if line.count('"') % 2:
        return []
    found = []
    for tokens in analyse(re.sub(r'"[^"]*"', '""', line)):
        phrases = relate(tokens).phrases
        for k, phrase in enumerate(phrases):
            words = phrase.lower().split()
            if (any(w in ("colour", "color", "coloured", "colored") for w in words) or words[0] == "after"
                    or len(words) == 1 and re.fullmatch(r"x\d+|\d+x", words[0])
                    or re.search(r"\b[xy] \d+", phrase.lower())                  # 'x 20', 'y 20' shown as words
                    or len(words) == 1 and next_to_quotes(words[0], tokens)
                    or k == len(phrases) - 1 and len(words) == 1 and colour_alone(words[0], tokens)
                    or any(w in ("screen", "window") for w in words)
                    or len(words) >= 2 and words[-1] in ("says", "say", "reads", "saying", "words") and words[0] != "to"):
                found.append(phrase)        # unmistakable: not 'in a red house', 'in 5 minutes' or 'the word'
    return found


def next_to_quotes(word, tokens):
    """A bare colour right before or after quoted words ('navy "lets go"'): how they look, not words."""
    for k, t in enumerate(tokens):
        if t.word == word and "colour" in t.ideas and any(
                0 <= j < len(tokens) and tokens[j].quoted for j in (k - 1, k + 1)):
            return True
    return False


def colour_alone(word, tokens):
    """A bare colour at the very end of a direction ('print hello gold'): how it should look, never words to
    show. Not colours that are also things (salmon, peru): those need the word colour."""
    table = dictionary.colour_table()
    return bool(tokens) and tokens[-1].word == word and word in universe().words and \
        "colour" in universe().words[word] and not (word in table and table[word][1])


def sure(line):
    """The universe's own telling of a line, if it can account for every word as part of a direction
    (an action, a thing, a colour, a place, a time ...) with no words left over to show. None otherwise."""
    if line.count('"') % 2:
        return None
    told = []
    for k, tokens in enumerate(analyse(line)):
        d = relate(tokens)
        d.follows = k > 0
        ways = tell(d)
        if (d.content or d.lost or not ways) and any(t.spelled and not t.real for t in tokens):
            world = universe()                # 'make bg maenta': complete once the slip is spelled right
            d = relate([Token(t.spelled[0], world.about(world.words.get(t.spelled[0], {"other action"})))
                        if t.spelled and not t.real else t for t in tokens])
            d.follows = k > 0
            ways = tell(d)
        if d.content and not all(t.quoted for t in d.content) or d.lost or not ways:
            return None                       # words to show are fine when they're in quotes: unmistakable
        told.append(ways[0])
    return " then ".join(told) if told else None


def same_meaning(tokens):
    """The direction again, with a word brick doesn't know swapped for a WordNet synonym it does:
    'discontinue the program' -> 'stop the program', 'state hello in red' -> 'say hello in red'."""
    if synchronicity.off():
        return []
    import wordnet
    from actions import STARTERS
    world, ways = universe(), []
    for k, t in enumerate(tokens):
        if t.ideas or t.quoted or not t.word.isalpha() or len(t.word) < 3:
            continue
        for other in wordnet.synonyms(t.word)[:10]:
            if " " not in other and (other in STARTERS or world.words.get(other, set()) - {"filler", "glue", "chatter"}):
                ways.append(" ".join(x.text if j != k else other for j, x in enumerate(tokens)))
                break
        if len(ways) >= 3:
            break
    return ways


def verb_first(tokens):
    """Is the direction's first word unknown, with a WordNet synonym brick knows as an action? Directions
    start with their verb, so 'state hello in red' means say hello in red."""
    import wordnet
    from actions import STARTERS
    t = tokens[0]
    if t.ideas or t.quoted or not t.word.isalpha():
        return False
    return any(o in STARTERS or universe().words.get(o, set()) & {"show", "placing", "make", "clear", "wait"}
               for o in wordnet.synonyms(t.word)[:10] if " " not in o)


def tellings(line):
    """Ways to say a whole line in brick's words, the likeliest first."""
    if line.count('"') % 2:
        return []                     # a quote mark without its partner: brick's own message says so
    directions = analyse(line)
    told = []
    for k, tokens in enumerate(directions):
        as_typed = " ".join(t.text for t in tokens)
        if tokens[0].word.startswith(("make it", "have it", "let it", "it ")):     # brick knows 'make it say'
            told.append([as_typed])
        else:
            each = [tell(d) for d in readings(tokens, k > 0)]
            ways = [w[0] for w in each if w] + [way for w in each for way in w[1:]]   # each reading's best first
            same = same_meaning(tokens)                   # a word brick doesn't know, as a synonym it does:
            leading = [w for w in same if tokens[0].word not in w.split()[:1]]
            ways = (leading[:1] + ways + same) if leading and verb_first(tokens) else ways + same   # first if it
                                                                                                    # leads, as verbs do
            told.append(list(dict.fromkeys(ways)) or [as_typed])
    first = [ways[0] for ways in told]
    found = [" then ".join(first)]
    for k, ways in enumerate(told):
        for way in ways[1:]:
            found.append(" then ".join(first[:k] + [way] + first[k + 1:]))
    found = [f for f in dict.fromkeys(found) if f.lower() != line.lower()]
    return found[:MOST]


# ---------------- the compiler asks ----------------

def retell(text, problem, failing, first=None):
    """brick couldn't read some lines: say each again in brick's words, if that makes it build.
    failing(text) -> the line numbers that still have problems. Returns (new text, notes), or None."""
    lines = text.split("\n")
    stuck = list(dict.fromkeys(int(n) for n in re.findall(r"^Line (\d+): ", problem, re.MULTILINE)))
    notes = []
    for number in stuck[:12]:
        raw = lines[number - 1]
        indent = raw[:len(raw) - len(raw.lstrip())]
        try:
            ways = tellings(raw.strip())
        except Exception:             # the universe should never stop a build
            ways = []
        heard = [] if sure(raw.strip()) else \
            neural.readings(raw.strip(), "\n".join(lines[max(0, number - 3):number - 1]))
        checked = (first or {}).get(number)
        if heard and checked and checked not in heard:         # the re-cut's reading against the neural one
            heard = judged(raw.strip(), [checked] + heard, lines, number, failing) or []
            if heard:
                first = {**first, number: heard[0]}
        if heard:                     # the universe's own readings first; the neural reader's after them,
            ways = ways + [way for way in heard if way not in ways]     # for lines the universe can't read
        if heard and ways and ways[0] not in heard:   # the universe's best and the neural reader's disagree:
            own = [way for way in ways if way not in heard][:3]  # it judges between them (the universe's best
            ways = judged(raw.strip(), own[:1] + heard, lines, number, failing, own[1:]) + ways   # that builds)
        whole = (first or {}).get(number) or sure(raw.strip())   # a checked reading, or one that accounts for
                                                                  # every word, comes before the bias
        if whole:
            ways = [whole] + [way for way in ways if way != whole]
        said = review.settled().get(raw.strip().lower())
        if said:                      # you said what this line means, after a run: that comes first of all
            ways = [said] + [way for way in ways if way != said]
        for way in ways:
            attempt = lines[:number - 1] + [indent + way] + lines[number:]
            still = failing("\n".join(attempt))
            if number not in still and not still - set(stuck):
                lines = attempt
                notes.append(f"Note: line {number} read as: {way}")
                break
    return ("\n".join(lines), notes) if notes else None


def judged(line, ways, lines, number, failing, spare=()):
    """The readings that build, one per different program, put to the neural reader to pick the meant one;
    that one first. Readings that make the same program don't need judging."""
    import review
    distinct, made = [], set()
    words = trial_words("")
    try:
        if spare and not review.build("\n".join(lines[:number - 1] + [ways[0]] + lines[number:]), words):
            ways = [next((w for w in spare if review.build("\n".join(lines[:number - 1] + [w] + lines[number:]),
                                                           words)), ways[0])] + list(ways[1:])
        for k, way in enumerate(ways[:8]):
            attempt = "\n".join(lines[:number - 1] + [way] + lines[number:])
            program = review.build(attempt, words)
            if program and program not in made:
                made.add(program)
                distinct.append(way)
            elif not program and k == 0 and len(ways) > 1 and not distinct:
                continue                      # brick's best doesn't build: the next that does stands for it
    finally:
        shutil.rmtree(os.path.dirname(words), ignore_errors=True)
    if len(distinct) < 2:
        return []
    pick = neural.choose(line, distinct, "\n".join(lines[max(0, number - 3):number - 1]))
    if pick and shown_words(distinct[pick]) < shown_words(distinct[0]) and may_overrule(line, distinct[0], distinct[pick]):
        return [distinct[pick]]       # it may only overrule with a reading that understood more of the line as
                                      # instructions (fewer words left over as text), never less
    best = min(distinct[1:], key=shown_words)
    if shown_words(best) < shown_words(distinct[0]) and prints_instructions(distinct[0], line) and \
            may_overrule(line, distinct[0], best):
        return [best]                 # brick's best prints instruction words ('minute', 'times', 'shout') as
    return []                         # text; the neural reading understood them


def may_overrule(line, own, other):
    """May the neural reading replace brick's? Not if it adds directions the person didn't give ('all done
    with lime color' -> '... then stop'). (A reading in brick's own words has one direction per 'then'.)"""
    return other.count(" then ") + 1 <= max(1, len(analyse(line)), own.count(" then ") + 1)


def prints_instructions(reading, line):
    """Does this reading print words from the line that are instructions, not words to show: words the
    universe knows as part of a direction (times, minute, half), or a verb leading the line ('shout hello')?"""
    import wordnet
    world = universe()
    first = re.findall(r"[a-z]+", line.lower())[:1]
    for word in printed_words(reading):
        if world.words.get(word, set()) - {"glue", "filler", "chatter", "it"}:
            return True
        if first and word == first[0] and wordnet.senses(word, "v"):
            return True
    return False


def printed_words(reading):
    from compiler import Compiler
    compiler = Compiler(os.devnull, ask_user=lambda question: "no")
    try:
        compiler.compile_text(reading)
    except Exception:
        return []
    shown_words(reading)                    # (fills in brick's own messages, to leave them out)
    texts = [re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b.", "", t) for t in compiler.a.texts]
    return [w.lower() for t in texts if t not in _built_in for w in re.findall(r"[A-Za-z']+", t)]


_built_in = None


def shown_words(reading):
    """How many words a reading's program prints (built and counted: brick's own messages left out)."""
    global _built_in
    from compiler import Compiler

    def printed(text):
        compiler = Compiler(os.devnull, ask_user=lambda question: "no")
        try:
            compiler.compile_text(text)
        except Exception:
            return None
        plain = [re.sub(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b.", "", t) for t in compiler.a.texts]
        return [t for t in plain if re.search(r"[A-Za-z]", t)]       # colour codes aren't words
    if _built_in is None:
        _built_in = set(printed("beep") or [])
    found = printed(reading)
    if found is None:
        return 99
    return sum(len(re.findall(r"[A-Za-z']+", t)) for t in found if t not in _built_in)


def trial_words(words_file):
    """A copy of the user's own words, so trying a line can't change them."""
    folder = tempfile.mkdtemp(prefix="brick-universe-")
    copy = os.path.join(folder, "mywords.txt")
    if os.path.isfile(words_file):
        shutil.copy(words_file, copy)
    return copy
