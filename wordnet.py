"""WordNet: the dictionary of English in texts/sources/wordnet, for words that mean the same thing.

Used by the universe (a word brick doesn't know, read as a synonym it does: 'state hello' -> say hello)
and the factory (which then keeps that, once the tests agree).
"""
import os

WORDNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "texts", "sources", "wordnet")

FILES = {'n': 'noun', 'v': 'verb', 'a': 'adj', 'r': 'adv'}


def senses(word, pos):
    key = word.replace(' ', '_').lower() + ' '
    with open(os.path.join(WORDNET, 'index.' + FILES[pos])) as index:
        for line in index:
            if line.startswith(key):
                fields = line.split()
                return fields[6 + int(fields[3]):]
    return []


def synset(offset, pos):
    """The words of one WordNet entry and the entries it points to, by pointer symbol."""
    with open(os.path.join(WORDNET, 'data.' + FILES[pos])) as data:
        data.seek(int(offset))
        fields = data.readline().split(' | ')[0].split()
    count = int(fields[3], 16)
    words = [fields[4 + 2 * k].split('(')[0].replace('_', ' ') for k in range(count)]
    at = 4 + 2 * count
    pointers = []
    for k in range(int(fields[at])):
        symbol, target, target_pos = fields[at + 1 + 4 * k: at + 4 + 4 * k]
        pointers.append((symbol, target, target_pos))
    return words, pointers


_synonyms = {}


def synonyms(word):
    """Words that mean the same in the word's two commonest senses (same entry, never a wider word:
    'inscribe' is a kind of 'write', not the same thing, and wider words surprise people)."""
    if word not in _synonyms:
        found = []
        for pos in 'vna':
            for offset in senses(word, pos)[:2]:
                found += [w.lower() for w in synset(offset, pos)[0] if w.lower() != word]
        _synonyms[word] = list(dict.fromkeys(found))
    return _synonyms[word]
