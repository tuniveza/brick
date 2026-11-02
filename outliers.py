"""Outliers: what brick couldn't settle by itself, waiting for a person to decide (the Decisions tab in
brick gui). brick keeps learning on its own meanwhile; these are only the lines and words it gave up on.

texts/factory/unsure.txt holds them, one block each, separated by a blank line:
    line: wait 2 secs then wirte hi
    said: I don't know how to 'wirte'. Did you mean 'write'?
    meant: wait 2 seconds then write hi            (when brick knows what it should mean: the scrambler)
    could be: restate = repeat | restate = say      (when a word could mean more than one thing)
    from: the scrambler

What a person decides goes in texts/decisions.txt, in plain words.
"""
import hashlib
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "texts", "factory", "unsure.txt")
FOR_DIRECTOR = os.path.join(HERE, "texts", "factory", "for-director.txt")
DECISIONS = os.path.join(HERE, "texts", "decisions.txt")
FIELDS = ("line", "said", "meant", "could be", "from")


def entries(path=None):
    """Every outlier waiting -> [{"id", "line", "said", "meant", "could be": [...], "from"}]."""
    path = path or PATH
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        blocks = f.read().split("\n\n")
    found = []
    for block in blocks:
        entry = {}
        for row in block.strip().split("\n"):
            name, _, value = row.partition(": ")
            if name in FIELDS and value:
                entry[name] = value.strip()
        if entry.get("line"):
            entry["could be"] = [c.strip() for c in entry["could be"].split(" | ")] if entry.get("could be") else []
            entry["id"] = hashlib.sha1(entry["line"].encode()).hexdigest()[:12]
            found.append(entry)
    return found


def add(line, said="", meant=None, could_be=(), source="", path=None):
    """A new outlier, unless that line is waiting already."""
    path = path or PATH
    if any(e["line"] == line for e in entries(path)):
        return
    rows = [f"line: {line}"] + ([f"said: {said}"] if said else []) + ([f"meant: {meant}"] if meant else []) + \
        ([f"could be: {' | '.join(could_be)}"] if could_be else []) + ([f"from: {source}"] if source else [])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n\n")


def remove(id, path=None):
    """Take an outlier off the list -> the entry, or None."""
    path = path or PATH
    found = entries(path)
    gone = next((e for e in found if e["id"] == id), None)
    if gone:
        keep = [e for e in found if e["id"] != id]
        with open(path + ".new", "w", encoding="utf-8") as f:
            for e in keep:
                rows = [f"line: {e['line']}"] + [f"{name}: {e[name]}" for name in ("said", "meant") if e.get(name)] + \
                    ([f"could be: {' | '.join(e['could be'])}"] if e["could be"] else []) + \
                    ([f"from: {e['from']}"] if e.get("from") else [])
                f.write("\n".join(rows) + "\n\n")
        os.replace(path + ".new", path)
    return gone


def note(what):
    """Write a decision down, in plain words."""
    with open(DECISIONS, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')}  {what}\n")


# ---------------- a person decides ----------------

def decide(id, action, meaning=""):
    """action: 'means' (the line means this, in brick's words), 'word' (this way of teaching the word),
    'director' (leave it for the English Director) or 'dismiss'. -> (ok, a message to show)."""
    entry = next((e for e in entries() if e["id"] == id), None)
    if not entry:
        return False, "That one has been settled already."
    line = entry["line"]
    if action == "means":
        import review
        problem = review.correct(line, 1, meaning)
        if problem:
            return False, problem
        remove(id)
        note(f"'{line}' means: {meaning}")
        return True, f"Kept: brick reads '{line}' as '{meaning}' from now on."
    if action == "word":
        import factory
        ok, message = factory.teach(meaning)
        if ok:
            remove(id)
            note(f"taught: {meaning}  (for '{line}')")
        return ok, message
    if action == "director":
        remove(id)
        add(line, entry.get("said", ""), entry.get("meant"), entry["could be"], entry.get("from", ""), path=FOR_DIRECTOR)
        note(f"left for the English Director: '{line}'")
        return True, "Left for the English Director (texts/factory/for-director.txt)."
    if action == "dismiss":
        remove(id)
        note(f"dismissed: '{line}'")
        return True, "Dismissed."
    return False, "I don't know that choice."
