"""Week 12: one text normaliser, shared by the index (what is indexed), the agent (what counts as relevant) and the
composer (which passage leads) -- three places that each had their own idea of "the same word" and disagreed.

A deliberately small suffix stripper: retries -> retry, attempts -> attempt, failed -> fail,
pagination / paginate -> pagin, authenticate / authentication -> authentic. The Week 3-4 TF-IDF has no stemmer, so
without this "retry" and "retries" are different words and a question about one never finds the page about the other.
Applied identically to INDEXED text and to QUERIES, never to what the caller sees. Stop words and identifiers
(anything with an underscore or digit) are left alone.
"""

import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

_SUFFIXES = (("ies", "y"), ("ation", ""), ("ate", ""), ("ing", ""), ("ed", ""))


def stem(word):
    if len(word) <= 3 or word in ENGLISH_STOP_WORDS:
        return word
    for suf, rep in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            word = word[: -len(suf)] + rep
            break
    else:
        if word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    return word


def stem_text(text):
    return re.sub(r"(?<![\w])[A-Za-z]+(?![\w])", lambda m: stem(m.group(0).lower()), text)


def stems(text, filler=(), min_len=4):
    """The set of stemmed content words in `text` (identifiers split on underscores / dots, so list_messages gives 'messag')."""
    return {stem(w) for w in re.findall(r"[a-z]{%d,}" % min_len, text.lower()) if w not in filler}


def strip_parens(text):
    """'Send a message (2.2 to 2.4)' -> 'Send a message': a version label is not a topic."""
    return re.sub(r"[(][^)]*[)]", " ", text)


# Words that are in nearly every chunk of an SDK-docs corpus: they count as evidence in a TITLE ("Send a message") but never
# as evidence in a tag line or a body ("request" in a print() string once made a timeout sample 'relevant' to a headers question).
GENERIC = {"request", "client", "messag", "call", "acme", "data", "user", "make", "send", "reply", "page"}
