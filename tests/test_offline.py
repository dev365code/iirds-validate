"""The tool must never reach the network, and must notice tampered ontologies."""
from __future__ import annotations

import socket

import pytest

from iirds_validate import runner
from iirds_validate.context import load_context
from iirds_validate.ontology import load
from iirds_validate.package import Package


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
    """The guard is about where a context comes from, not what it says.

    Asserting the whole report is clean would be asserting something else: this
    fixture's JSON-LD describes only the package node, so L9 correctly reports
    that the two serialisations disagree. That is a different rule doing its
    job, and conflating the two would let a regression in either hide behind
    the other.
    """
    report = runner.check(make_package(jsonld=INLINE_CONTEXT))
    assert "C16.2" not in {f.rule.id for f in report.findings}
    assert not any("inline" in (f.violation.detail or "") for f in report.findings)


def test_vendored_ontology_is_intact():
    import hashlib

    from iirds_validate import resources
    from iirds_validate.model import LATEST_VERSION

    for line in resources.read_text("ontologies", "sha256sums.txt").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        blob = resources.read_bytes("ontologies", LATEST_VERSION, name.strip())
        assert hashlib.sha256(blob).hexdigest() == digest, \
            "%s was modified; CC BY-ND forbids redistributing an adapted ontology" % name.strip()


def test_ontology_hierarchy_is_read_not_hardcoded():
    from iirds_validate import terms as T
    subclasses = load().subclasses_of(T.InformationUnit)
    assert T.Topic in subclasses and T.Document in subclasses and T.Fragment in subclasses


def test_a_full_validation_run_never_touches_the_network(make_package, monkeypatch):
    """The offline claim, enforced rather than stated: seal DNS and every
    connect, then run all 166+ rules. A single network attempt anywhere in
    the pipeline dies loudly. This is the sentence on the front page
    ("fully offline") turned into a gate."""
    import socket

    def die(*args, **kwargs):
        raise OSError("network attempt during validation — the offline claim broke")

    monkeypatch.setattr(socket, "create_connection", die)
    monkeypatch.setattr(socket, "getaddrinfo", die)
    monkeypatch.setattr(socket.socket, "connect", die, raising=True)

    report = runner.run(make_package(), runner.ALL_KINDS)
    assert report.checked > 150


#: The other half of "reading a package never touches the network", and the
#: half that had no seal anywhere: a `@context` naming no scheme is not a URL,
#: so rdflib resolves it against the *operator's* working directory and opens
#: whatever it finds. The decoy defines a @vocab the document then uses,
#: because a context contributes no triples of its own -- asserting that the
#: decoy's triples are absent would otherwise assert nothing at all.
DECOY_CONTEXT = '{"@context": {"@vocab": "http://leaked.example/secret#"}}'
RELATIVE_CONTEXT = ('{"@context": "secret-ctx.jsonld", "@id": "urn:test:package",'
                    ' "@type": "iirds:Package", "leak": "pwned"}')

#: The refusal is not this project's to make -- it belongs to the layer that
#: parses, `iirds`, which ships from this tree -- so this asserts it from the
#: checker's side, where a regression would surface as a leak.
def test_a_relative_jsonld_context_reads_no_file_outside_the_container(
        make_package, monkeypatch, tmp_path):
    """No byte from outside the container may enter the graph.

    The assertions are deliberately both halves. Absence alone passes for the
    wrong reasons -- a parse that failed for an unrelated cause satisfies it
    -- so the refusal itself is asserted beside it.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "secret-ctx.jsonld").write_text(DECOY_CONTEXT, "utf-8")

    path = make_package(jsonld=RELATIVE_CONTEXT)
    report = runner.check(path)

    assert not report.ok
    assert "C16.2" in {f.rule.id for f in report.findings}
    assert any("inline" in (f.violation.detail or "") for f in report.findings), \
        [f.violation.detail for f in report.findings]

    with Package(path) as package:
        graph = load_context(package).graph
    assert not any("leaked.example" in str(term) for triple in graph for term in triple), \
        "a file from the operator's working directory reached the graph"
