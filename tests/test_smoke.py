"""Smoke tests for the atlas package."""


def test_package_imports():
    """The atlas package is importable."""
    import atlas

    assert atlas is not None


def test_truth():
    """pytest itself is wired up correctly."""
    assert 1 + 1 == 2
