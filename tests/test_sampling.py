from sampling import seeded_sample


def test_same_seed_gives_same_sample():
    items = [f"item-{i}" for i in range(100)]
    assert seeded_sample(items, 10, seed=42) == seeded_sample(items, 10, seed=42)


def test_different_seed_gives_different_sample():
    items = [f"item-{i}" for i in range(100)]
    assert seeded_sample(items, 10, seed=1) != seeded_sample(items, 10, seed=2)


def test_sample_size_and_membership():
    items = [f"item-{i}" for i in range(50)]
    sample = seeded_sample(items, 20, seed=7)

    assert len(sample) == 20
    assert len(set(sample)) == 20
    assert all(item in items for item in sample)
