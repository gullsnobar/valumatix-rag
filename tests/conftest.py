"""Provide shared pytest fixtures and configuration for the test suite."""

from pathlib import Path

import pytest


@pytest.fixture
def corpus_dir() -> Path:
    """Return the repository's document corpus directory."""

    return Path(__file__).resolve().parents[1] / "corpus"
