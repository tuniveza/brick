"""Making your own words: "to greet someone means write hi someone in green".

Placeholder words (someone, somebody, something, a number, a word) become holes that are
filled in each time the new word is used: "greet Dominic" -> write hi Dominic in green.
Each hole is named by its word, so "introduce someone to somebody" has two.
Your words are kept in mywords.txt, one definition per line, so they're there next time.
"""
import os
import re

HOLES = {"someone": "someone", "somebody": "somebody", "something": "something",
         "a number": "number", "a word": "word"}
DROP_IN_FRONT = ("to", "a", "an", "the", "do")
PATTERNS = [
    r"(?:to\s+)?(?P<head>.+?)\s+(?:means|is when)\s+(?P<body>.+)",
    r"(?:teach|define)\s+(?:(?:me|us|you|it|the computer)\s+(?:how\s+)?to\s+)?"      # teach me to dance: ...
    r"(?P<head>.+?)\s*(?::|\s+as\s+|\s+to mean\s+)\s*(?P<body>.+)",
    r"(?P<body>.+?),?\s+call it\s+(?P<head>.+)",
    r"(?:when|whenever)\s+i\s+(?:say|type)\s+(?P<head>.+?)\s*,\s*(?P<body>.+)",   # when I say hi, write hello
]


class Definition:
    def __init__(self, line, head, body):
        self.line = line              # exactly as it was typed
        self.body = body
        self.pattern = pattern_of(head)
        self.key = " ".join(part if kind == "word" else "_" for kind, part in self.pattern)

    def first_word(self):
        return next((part for kind, part in self.pattern if kind == "word"), None)


def outside_quotes(line):
    """The line with anything in quotes blanked out, so 'means' inside a text doesn't count."""
    return re.sub(r'"[^"]*"', lambda m: "_" * len(m.group()), line)


def read_definition(line):
    """Return a Definition if this line teaches a new word, else None."""
    plain = outside_quotes(line.strip().rstrip("."))
    for pattern in PATTERNS:
        found = re.fullmatch(pattern, plain, re.IGNORECASE)
        if found and "call it" in pattern and names_an_answer(found.group("body")):
            continue
        if found:
            head = line.strip()[found.start("head"):found.end("head")]
            body = line.strip()[found.start("body"):found.end("body")]
            return Definition(line.strip(), head, body)
    return None


def unfinished(line):
    """'to greet someone means' with nothing after it -> 'greet someone'; else None."""
    found = re.fullmatch(r"(?:to\s+)?(.+?)\s+means\s*:?", outside_quotes(line.strip().rstrip(".")), re.IGNORECASE)
    return found.group(1) if found else None


def opens_block(line):
    """'to greet someone means:', 'teach me to dance:', 'when I say hi:': the actions are on the lines below."""
    plain = outside_quotes(line.strip())
    return bool(re.fullmatch(r"(?:to\s+)?.+?\s+(?:means|is when)\s*:?|(?:teach|define)\s+.+:|"
                             r"(?:when|whenever)\s+i\s+(?:say|type)\s+.+?[:,]", plain, re.IGNORECASE))


def with_body(line, lines):
    """The definition and the lines indented under it as one line: each word is kept on one line in mywords.txt."""
    head = line.strip().rstrip(":,").rstrip()
    joiner = " " if re.search(r"(?:means|is when)$", head, re.IGNORECASE) else \
        ", " if re.match(r"when", head, re.IGNORECASE) else ": "
    return head + joiner + " then ".join(lines)


def names_an_answer(body):
    """'ask for a number and call it guess' names the answer; it doesn't teach a word."""
    actions = [a.strip() for a in re.split(r"[,.;:]|\bthen\b|\band\b", body, flags=re.IGNORECASE) if a.strip()]
    return bool(actions) and re.match(r"(ask|load|open|read)\b", actions[-1], re.IGNORECASE) is not None


def pattern_of(head):
    """'greet someone' -> [('word', 'greet'), ('hole', 'someone')]."""
    words = head.lower().replace('"', "").split()
    while words and words[0] in DROP_IN_FRONT and len(words) > 1:
        words = words[1:]
    pattern, i = [], 0
    while i < len(words):
        two = " ".join(words[i:i + 2])
        if two in HOLES:
            pattern.append(("hole", HOLES[two]))
            i += 2
        elif words[i] in HOLES:
            pattern.append(("hole", HOLES[words[i]]))
            i += 1
        else:
            pattern.append(("word", words[i]))
            i += 1
    return pattern


def how_to_use(definition):
    """'greet someone' -> 'greet someone. For example: greet Sam'."""
    examples = {"someone": "Sam", "somebody": "Sam", "something": "hello", "number": "3", "word": "hello"}
    shape = " ".join(part for kind, part in definition.pattern)
    example = " ".join(part if kind == "word" else examples[part] for kind, part in definition.pattern)
    return f"{shape}. For example: {example}"


def match(definition, words):
    """If the action's words use this definition, return {hole: [words]}; else None.
    Each hole takes one word, except the last one, which takes the rest."""
    while len(words) > 1 and words[0].word in DROP_IN_FRONT:
        words = words[1:]
    filled, i = {}, 0
    pattern = definition.pattern
    for n, (kind, part) in enumerate(pattern):
        if i >= len(words):
            return None
        if kind == "word":
            if words[i].word != part:
                return None
            i += 1
        elif n == len(pattern) - 1:
            filled[part], i = words[i:], len(words)
        else:
            filled[part], i = words[i:i + 1], i + 1
    return filled if i == len(words) else None


def load(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [d for d in (read_definition(line) for line in f if line.strip()) if d]


def save(path, definitions):
    with open(path, "w") as f:
        f.write("".join(d.line + "\n" for d in definitions))
