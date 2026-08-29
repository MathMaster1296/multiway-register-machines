"""Smoke test: the package installs and imports."""

import mrm


def test_version_is_a_string() -> None:
    assert isinstance(mrm.__version__, str)
    assert mrm.__version__
