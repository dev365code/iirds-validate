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


#: A JSON-LD context may be a URL, and the parser dereferences it. The earlier
#: version of this file validated a package with no JSON-LD in it and therefore
#: proved nothing about the case that actually reaches the network.
REMOTE_CONTEXT = '{"@context": "https://example.invalid/ctx.jsonld", "@id": "urn:p"}'
NESTED_REMOTE_CONTEXT = (
    '{"@context": [{"iirds": "http://iirds.tekom.de/iirds#"},'
    ' "http://example.invalid/ctx"], "@id": "urn:p"}')
INLINE_CONTEXT = ('{"@context": {"iirds": "http://iirds.tekom.de/iirds#"},'
                  ' "@id": "urn:test:package", "@type": "iirds:Package"}')


@pytest.mark.parametrize("jsonld", [REMOTE_CONTEXT, NESTED_REMOTE_CONTEXT],
                         ids=["top-level", "nested-in-array"])
def test_a_remote_jsonld_context_is_refused_not_fetched(make_package, no_network, jsonld):
    """Otherwise a supplier chooses which host the validator connects to.

    Inside a plant network that is worse than a broken promise about being
    offline: the package decides where a machine behind the firewall reaches
    out to. Contexts must be inline.
    """
    report = runner.check(make_package(jsonld=jsonld))     # no_network would raise on a fetch

    assert not report.ok
    assert "C16.2" in {f.rule.id for f in report.findings}
    assert any("inline" in (f.violation.detail or "") for f in report.findings)


def test_an_inline_context_still_works(make_package, no_network):
    report = runner.check(make_package(jsonld=INLINE_CONTEXT))
    assert report.ok, [f.violation.message for f in report.findings]


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
