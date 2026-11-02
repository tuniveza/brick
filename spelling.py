"""Spotting likely typos that can't safely be refused: 'write scroe' when the program has score,
'write hello in gren'. The program still builds; brick just mentions them.

A word only counts as a slip if it's one small finger-slip away from a name or colour
(two letters swapped, one letter left out, or one letter typed twice) and isn't an
ordinary English word.
"""

# Ordinary words that are one slip away from a likely name or colour ("live" / "lives", "sore" / "score").
COMMON = set("""
about above after again against also always another answer around away back because been before
being below best better between both bring brow came come cons could does done down each even ever
every fast feel find fine first form found four free fried from full gave give goes going gone good
great half hand hard have head hear heard heat help here high hold home hope into just keep kind
knew know last late left less lets lies life like line lines list live lived lives long look lost
love made make many mark mean meet mind more most move much must name near need never next nice none
note nothing once only open over part pass past payer pick pints place plane plant play plays point
read real rest ride right road room round said same save says seed seen sell send sent shot show
side sign since slat some soon sore sort sped star start stay step still stop such sure take tale
tell than that them then there these they thin thing think this those tier time tire tired told took
tore tree trial tried true turn under until upon very wait walk want ware wars well went were what
when where which while white whole will wish with word words work world would year your yours
""".split())


def slip_of(word, choices):
    """The choice word looks like a slip of, or None."""
    if len(word) < 4 or not word.isalpha() or word in COMMON or word in choices:
        return None
    for choice in sorted(choices):
        if len(choice) >= 4 and choice.isalpha() and is_slip(word, choice):
            return choice
    return None


def is_slip(word, meant):
    """Two letters next to each other swapped, a letter left out (not the first, and not a
    plural's last s), or one letter typed twice."""
    if len(word) == len(meant):
        diff = [k for k in range(len(word)) if word[k] != meant[k]]
        return len(diff) == 2 and diff[1] == diff[0] + 1 and word[diff[0]] == meant[diff[1]] \
            and word[diff[1]] == meant[diff[0]]
    if len(word) == len(meant) - 1:
        return any(meant[:k] + meant[k + 1:] == word for k in range(1, len(meant))) and word + "s" != meant
    if len(word) == len(meant) + 1:
        return any(word[:k] + word[k + 1:] == meant and word[k] == word[k - 1] for k in range(1, len(word)))
    return False
