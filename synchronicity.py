"""Synchronicity bias: symbols that turn up together belong together.

The factory watches what you write (your .brick files, the sentence pool) and, for every direction it
has proved by building it, counts which idea each word was read as (pink as a colour, orange as words
to show) and which ideas turned up together (a colour with a place, words with a colour ...).
When the universe can read a line more than one way, it tries first the reading whose symbols fit best
with each other and with what was said before. brick still builds each reading to check it.

The counts are kept in texts/factory/memory.txt, plain text: delete it to start again. Old counts fade,
so what's said now counts for more than what was said long ago. With no counts at all, the readings
keep the order the universe's own links give them.
"""
import itertools
import math
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texts", "factory", "memory.txt")
FADE_AT = 200_000            # when the counts add up to this, every count halves


class Memory:
    def __init__(self, path=None):
        self.path = PATH if path is None else path
        self.read_as = {}        # (word, idea) -> how often the word was read as that idea
        self.together = {}       # (idea, idea), in order -> how often they were in one direction
        self.directions = 0
        if os.path.isfile(self.path):
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if parts[0] == "read" and len(parts) == 4:
                        self.read_as[(parts[1], parts[2])] = float(parts[3])
                    elif parts[0] == "together" and len(parts) == 4:
                        self.together[(parts[1], parts[2])] = float(parts[3])
                    elif parts[0] == "directions" and len(parts) == 2:
                        self.directions = float(parts[1])
        self.tally()

    def tally(self):
        self.word_seen, self.idea_seen = {}, {}
        for (word, idea), n in self.read_as.items():
            self.word_seen[word] = self.word_seen.get(word, 0) + n
            self.idea_seen[idea] = self.idea_seen.get(idea, 0) + n

    # ---- the factory teaches it ----

    def observe(self, roles):
        """One direction that built: roles = [(word, idea, linked), ...]."""
        for word, idea, _ in roles:
            self.read_as[(word, idea)] = self.read_as.get((word, idea), 0) + 1
        for a, b in pairs(roles):
            self.together[(a, b)] = self.together.get((a, b), 0) + 1
        self.directions += 1
        if self.directions + sum(self.read_as.values()) > FADE_AT:
            self.read_as = {k: n / 2 for k, n in self.read_as.items() if n >= 1}
            self.together = {k: n / 2 for k, n in self.together.items() if n >= 1}
            self.directions /= 2
        self.tally()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        lines = ["# brick's universe memory: which idea each word was read as, and which ideas turned up",
                 "# together, in directions the factory proved by building them. Delete it to start again.",
                 f"directions\t{self.directions:g}"]
        lines += [f"read\t{w}\t{i}\t{n:g}" for (w, i), n in sorted(self.read_as.items())]
        lines += [f"together\t{a}\t{b}\t{n:g}" for (a, b), n in sorted(self.together.items())]
        with open(self.path + ".new", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(self.path + ".new", self.path)

    # ---- the universe asks it ----

    def fit(self, roles):
        """How well a reading's symbols fit: each word as its idea, and its ideas with each other."""
        score = 0.0
        for word, idea, linked in roles:     # a link from universe.txt starts stronger than plain words
            score += math.log((self.read_as.get((word, idea), 0) + (2 if linked else 1)) /
                              (self.word_seen.get(word, 0) + 3))
        if not off():                        # ConceptNet's bias: words that belong together, kept together
            import conceptnet
            web = conceptnet.web()
            shown = [word for word, idea, _ in roles if idea == "words"]
            import universe
            colours = {w for w, ideas in universe.universe().words.items() if "colour" in ideas}
            score += sum(math.log1p(4 * web.together(a, b)) + (1.0 if f"{a} {b}" in web.links else 0)
                         for a, b in zip(shown, shown[1:])      # 'orange juice' is a thing of its own; but a colour
                         if b not in colours)                   # after a word ('go green') is how it looks
        found = list(pairs(roles))
        if found:
            seen = self.directions + 1
            score += sum(math.log((self.together.get(p, 0) + 1) * seen /
                                  ((self.idea_seen.get(p[0], 0) + 1) * (self.idea_seen.get(p[1], 0) + 1)))
                         for p in found) / len(found)        # more often together than apart: a better fit
        return score


def pairs(roles):
    ideas = sorted({idea for _, idea, _ in roles})
    return itertools.combinations(ideas, 2)


_memory, _read_when = None, None


def off():
    return os.environ.get("BRICK_MEMORY") == "off"


def memory():
    """What the factory has seen so far. BRICK_MEMORY=off: an empty memory (the tests); a path: that file."""
    global _memory, _read_when
    path = os.environ.get("BRICK_MEMORY") or PATH
    if path == "off":
        return Memory(path="")
    when = (path, os.path.getmtime(path) if os.path.isfile(path) else None)
    if _memory is None or when != _read_when:
        _memory, _read_when = Memory(path), when
    return _memory
