"""ConceptNet: an open web of everyday English, where each link has a weight. The universe uses it as
ready-made bias, before the factory has learned anything:

  what a word is        'backcloth' is the same as 'backdrop', 'scarlet' is a kind of 'red': a word the
                        universe doesn't know takes the ideas of one it does (universe.py)
  what goes together    'orange' and 'juice' are strongly related, so in 'orange juice at the top' they
                        belong together as the words to show, not a colour and a word (synchronicity.py)

Only the part that touches brick's world is kept, in texts/sources/conceptnet.tsv: links between English words
where one end is a word brick knows (its universe, dictionary, colours, and the sentence pool).
    python3 conceptnet.py fetch       download ConceptNet 5.7 once (about 475 MB, streamed, not kept)
                                      and keep that part

ConceptNet is by the Commonsense Computing Initiative, https://conceptnet.io, under the Creative Commons
Attribution-ShareAlike 4.0 licence (https://creativecommons.org/licenses/by-sa/4.0/). If you share
texts/sources/conceptnet.tsv, share it under the same licence and say where it came from.
"""
import gzip
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "texts", "sources", "conceptnet.tsv")
SOURCE = "https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz"
SAME = {"Synonym", "FormOf", "SimilarTo"}            # one word can stand for the other
KIND = {"IsA"}                                       # the first is a kind of the second: abstract on abstract
TOGETHER = {"RelatedTo", "Synonym", "SimilarTo", "PartOf", "HasA", "MadeOf", "UsedFor"}
KEPT = SAME | KIND | TOGETHER


class Web:
    def __init__(self, path=None):
        path = PATH if path is None else path
        self.links = {}          # word -> [(relation, other word, weight)], both ways for the 'together' kind
        if not os.path.isfile(path):
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                word, relation, other, weight = line.rstrip("\n").split("\t")
                self.links.setdefault(word, []).append((relation, other, float(weight)))
                if relation not in KIND:
                    self.links.setdefault(other, []).append((relation, word, float(weight)))

    def stands_for(self, word, strong=2.0):
        """Words this one is the same as, or a kind of, by links at least this strong (2: the careful links,
        from WordNet; 1: looser ones, like 'page' = 'side') -> [(other word, how it's linked)]."""
        return [(other, relation) for relation, other, w in self.links.get(word, ())
                if relation in SAME | KIND and w >= strong]

    def together(self, a, b):
        """How strongly two words belong together (0 if ConceptNet doesn't link them)."""
        return max((w for relation, other, w in self.links.get(a, ()) if other == b and relation in TOGETHER),
                   default=0.0)


_web = None


def web():
    global _web
    if _web is None:
        _web = Web()
    return _web


# ---------------- fetching the part brick needs ----------------

def brick_words():
    """Every word brick's world uses: the universe, the dictionary, colours, and the sentence pool."""
    sys.path.insert(0, HERE)
    import dictionary
    import universe
    words = set(universe.universe().words) | {e.key for e in dictionary.entries()}
    pool = os.path.join(HERE, "texts", "sentences.txt")
    if os.path.isfile(pool):
        with open(pool, encoding="utf-8", errors="replace") as f:
            words |= set(re.findall(r"[a-z][a-z'-]+", f.read().lower()))
    return words


def concept(uri):
    """'/c/en/sea_green/n' -> 'sea green'; None for other languages."""
    parts = uri.split("/")
    return parts[3].replace("_", " ") if len(parts) > 3 and parts[2] == "en" else None


def fetch():
    known = brick_words()
    print(f"Keeping ConceptNet links that touch {len(known):,} words brick knows. Downloading (about 475 MB)...")
    kept = 0
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with urllib.request.urlopen(SOURCE) as response, gzip.open(response, "rt", encoding="utf-8") as edges, \
            open(PATH + ".new", "w", encoding="utf-8") as out:
        out.write("# Part of ConceptNet 5.7 (https://conceptnet.io), by the Commonsense Computing Initiative,\n"
                  "# under CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). Made by conceptnet.py.\n"
                  "# word, how it's linked, the other word, the link's weight\n")
        for n, line in enumerate(edges):
            _, relation, start, end, extra = line.split("\t")
            relation = relation[3:]
            if relation not in KEPT:
                continue
            a, b = concept(start), concept(end)
            if not a or not b or a == b or not any(x in known or x.split(" ")[0] in known for x in (a, b)):
                continue                        # 'green tea' stays: phrases starting with a word brick knows
            weight = json.loads(extra).get("weight", 1.0)
            out.write(f"{a}\t{relation}\t{b}\t{weight:g}\n")
            kept += 1
            if n % 2_000_000 == 0:
                print(f"  {n:,} links read, {kept:,} kept", flush=True)
    os.replace(PATH + ".new", PATH)
    print(f"Kept {kept:,} links in {PATH}")


if __name__ == "__main__":
    if sys.argv[1:] == ["fetch"]:
        fetch()
    else:
        print(__doc__)
