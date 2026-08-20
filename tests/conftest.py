"""Fixtures for the test suite.

The container builder itself lives in `tools/make_fixture_package.py` so that
CI can produce a package for the installed-wheel smoke test without importing
pytest. One builder, imported here, rather than two that drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from make_fixture_package import (  # noqa: E402
    ATTRIBUTE_STYLE_RDF,
    DESCRIPTION_STYLE_RDF,
    MIMETYPE,
    MINIMAL_JSONLD,
    MINIMAL_RDF,
    build_package,
)

__all__ = ["ATTRIBUTE_STYLE_RDF", "DESCRIPTION_STYLE_RDF", "MIMETYPE", "MINIMAL_JSONLD", "MINIMAL_RDF",
           "build_package", "make_package"]


@pytest.fixture
def make_package(tmp_path):
    def factory(**kwargs):
        return build_package(tmp_path, **kwargs)
    return factory
