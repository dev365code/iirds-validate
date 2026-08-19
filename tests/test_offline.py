"""The tool must never reach the network, and must notice tampered ontologies."""
from __future__ import annotations

import socket

import pytest

from iirds_validate import runner
from iirds_validate.ontology import load


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the validator attempted a network connection")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_validation_runs_with_the_network_disabled(make_package, no_network):
    report = runner.run(make_package(), runner.ALL_KINDS)
    assert report.checked > 40


def test_vendored_ontology_is_intact():
    import hashlib

    from iirds_validate.model import LATEST_VERSION
    from iirds_validate.ontology import DATA

    for line in (DATA / "sha256sums.txt").read_text().splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        blob = (DATA / LATEST_VERSION / name.strip()).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest, \
            "%s was modified; CC BY-ND forbids redistributing an adapted ontology" % name.strip()


def test_ontology_hierarchy_is_read_not_hardcoded():
    from iirds_validate import terms as T
    subclasses = load().subclasses_of(T.InformationUnit)
    assert T.Topic in subclasses and T.Document in subclasses and T.Fragment in subclasses
