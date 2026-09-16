"""Seeded random sampling, so a sample is both random and reproducible/provable.

random.Random(seed) is a separate, isolated generator (does not touch the
global random module), so sampling never depends on call order elsewhere.
"""

import random


def seeded_sample(items, k, seed):
    rng = random.Random(seed)
    return rng.sample(list(items), k)
