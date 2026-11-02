"""Bricks: brick's words as tiles to click or drag (the tray in brick gui), and a line shown as bricks,
coloured by what brick reads each word as.

Everything comes from what brick knows: the universe's words (texts/universe.txt), the dictionary, the
colours and brick's own actions. A word the factory learns turns up as a brick by itself.
"""
import dictionary
import universe
from actions import COLOURS, STARTERS

CORE_ACTIONS = ["write", "say", "show", "put", "place", "type", "make", "turn", "set", "clear", "wait", "ask"]
PLACES = ["at the top", "at the bottom", "on the left", "on the right", "in the middle", "at the top-left",
          "at the top-right", "at the bottom-left", "at the bottom-right", "of the screen", "left", "right",
          "top", "bottom", "middle"]
TIME = ["after 2 seconds", "wait 2 seconds", "for 3 seconds", "seconds", "minutes", "every second"]
COUNT = ["3 times", "x3", "forever", "until", "twice"]
SAYING = ["saying", "that says", "the words", "make it say", "text"]
JOINING = ["then", "and", ",", ";", "if", "otherwise", "is", "is more than", "is less than"]
READY = ["write ___ in ___ at the ___", "write ___ in ___", "put text at the ___ that says ___",
         "put the window on the ___ side of the screen", "make the window ___", "set the background colour to ___",
         "set the colour to ___", "clear the screen", "wait ___ seconds", "after ___ seconds write ___",
         "ask ___ as ___", "repeat ___ times: write ___", "if ___ is ___, write ___", "make it say ___",
         "make it disappear after ___ seconds", "set ___ to ___", "add ___ to ___", "beep"]


def hex_of(code):
    """'38;2;255;0;0' -> '#ff0000'."""
    parts = code.split(";")
    return "#" + "".join(f"{int(p):02x}" for p in parts[2:5]) if len(parts) >= 5 else None


def palette():
    """The tray: groups of bricks -> [{"name", "kind", "bricks": [{"text", "hint", "swatch"}]}]."""
    world = universe.universe()
    showing = sorted(w for w, ideas in world.words.items() if ideas & {"show", "placing", "make", "clear", "wait"}
                     and " " not in w and w not in CORE_ACTIONS)
    more = sorted(w for w in STARTERS if w not in CORE_ACTIONS and w not in showing)
    colours = [{"text": name, "swatch": hex_of(code)} for name, code in COLOURS.items()]
    extra = sorted((name, code) for name, (code, _) in dictionary.colour_table().items()
                   if name not in COLOURS and " " in name or name not in COLOURS and len(name) < 14)
    colours += [{"text": name, "swatch": hex_of(code), "more": True} for name, code in extra]
    words = sorted({e.key for e in dictionary.entries() if e.kind not in ("colour",)})
    meanings = {e.key: e.meaning for e in dictionary.entries()}
    groups = [
        ("Do", "do", [{"text": w} for w in CORE_ACTIONS] + [{"text": w, "more": True} for w in showing + more]),
        ("Things", "thing", [{"text": w} for w in ["text", "the window", "the background", "the screen", "it"]]),
        ("Colours", "colour", colours),
        ("Places", "place", [{"text": w} for w in PLACES]),
        ("Time", "time", [{"text": w} for w in TIME]),
        ("Count", "count", [{"text": w} for w in COUNT]),
        ("Saying", "saying", [{"text": w} for w in SAYING]),
        ("Joining", "glue", [{"text": w} for w in JOINING]),
        ("Ready-made", "ready", [{"text": w} for w in READY]),
        ("Dictionary", "dictionary", [{"text": w, "hint": f"means: {meanings[w]}", "more": True} for w in words]),
    ]
    return [{"name": name, "kind": kind, "bricks": bricks} for name, kind, bricks in groups]


def read_line(line):
    """A line as bricks, coloured by what brick reads each word as -> [[{"text", "kind", "hint"}], ...]:
    one list per direction, so you can see where brick thinks each direction ends."""
    out = []
    for tokens in universe.analyse(line):
        best = universe.readings(tokens)
        shown = {id(t) for t in best[0].content} if best else set()
        bricks = []
        for t in tokens:
            kind = kind_of(t, id(t) in shown)
            hint = {"do": "what to do", "thing": "a thing", "colour": "how it looks", "place": "where it goes",
                    "time": "when, or how long", "count": "how many times", "saying": "the words to show come next",
                    "glue": "a joining word", "words": "words to show"}.get(kind, "")
            if t.spelled and not t.real:
                hint = f"probably '{t.spelled[0]}' (a slip)"
            bricks.append({"text": t.text, "kind": kind, "hint": hint})
        out.append(bricks)
    return out


def kind_of(token, shown):
    if token.quoted or shown:
        return "words"
    ideas = token.ideas
    for kind, wanted in (("do", {"action", "other action"}), ("thing", {"thing", "surface"}), ("colour", {"colour", "style"}),
                         ("place", {"place"}), ("time", {"time unit", "later"}), ("count", {"count", "times"}),
                         ("saying", {"saying", "look word"}), ("glue", {"glue", "filler", "chatter", "toward",
                                                                       "by means of", "becoming", "it", "number"})):
        if ideas & wanted:
            return kind
    return "words"
