"""The specification's own examples, run through this validator.

56 of the vendored fixtures are excerpts from the standard's numbered examples,
and 24 of them are referenced by no rule in the catalogue -- so neither tool has
ever evaluated them. They are the highest-authority conformant material
available offline: written by the people who wrote the requirements, illustrating
the requirements, and invented by neither this project nor plusmeta.

That makes them a false-positive oracle nothing else here provides. The
cross-validation corpus tests whether this validator agrees with *another
implementation*; these test whether it agrees with *the standard's own idea of a
correct package*. When the two disagree, the example is almost always right --
it has happened three times already (B4, M17/M18, M78-M93), and each time the
rule was too broad.

They are fragments, not packages, so package-level rules fire on all of them.
That noise is enumerated below rather than filtered by severity, because a list
of excuses somebody has to maintain is honest and a blanket exemption is not.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import vendor_corpus
from crossvalidate import wrap
from iirds_validate import runner
from iirds_validate.model import Severity

MANIFEST = json.loads(vendor_corpus.MANIFEST.read_text("utf-8"))

#: Rules that fire because a fragment is a fragment, not because anything is
#: wrong with it. Each is here for a stated reason; none is a severity filter.
FRAGMENT_NOISE = {
    "M3":  "an excerpt has no iirds:Package element; a real package would",
    "L2":  "iirds:source names content files that exist in the standard's prose, not here",
    "L8":  "examples reference external vocabularies on purpose -- that is the point of them",
    "L6":  "proprietary values are shown without the labels a whole package would carry",
    "L7":  "an excerpt shows one property, not the title an information unit would have",
}

#: Not RDF at all. Example 46 is the Appendix B hazard-statement markup and
#: Example 18 is prose; feeding either into the metadata slot tests the harness,
#: not the validator. Example 46 gets its own test below, against the B rules
#: it was actually written to illustrate.
NOT_METADATA = {"Example 46 - Tagging.rdf", "Example 18 - Topic types.rdf"}


def _usable():
    """Examples the standard presents as correct: excludes plusmeta's
    deliberately broken `_false` variants, and anything that will not parse."""
    return [name for name in sorted(MANIFEST["files"])
            if name.startswith("Example ")
            and "_false" not in name
            and name not in NOT_METADATA
            and MANIFEST["files"][name]["parses"] in ("ok", "needs_namespace_wrapper")]


def _as_package(name: str, directory: Path) -> Path:
    raw = (vendor_corpus.FILES / name).read_bytes()
    if MANIFEST["files"][name]["parses"] == "needs_namespace_wrapper":
        text = raw.decode("utf-8", "replace")
        body = text.split("?>", 1)[1] if text.lstrip().startswith("<?xml") else text
        raw = (vendor_corpus.NAMESPACE_WRAPPER % body).encode("utf-8")
    return wrap(raw, directory / ("%d.iirds" % abs(hash(name))))


EXAMPLES = _usable()


def test_there_is_material_to_test():
    assert len(EXAMPLES) > 20


@pytest.mark.parametrize("name", EXAMPLES, ids=[n[:40] for n in EXAMPLES])
def test_no_unexplained_error_on_material_the_standard_wrote(name, tmp_path):
    """An error-level finding here means one of two things, and both matter: a
    rule of ours is too broad, or the specification's own example does not
    satisfy the specification. Neither should pass unnoticed.
    """
    report = runner.run(_as_package(name, tmp_path), runner.ALL_KINDS)
    unexplained = sorted({f.rule.id for f in report.findings
                          if f.severity is Severity.ERROR and f.rule.id not in FRAGMENT_NOISE})
    assert unexplained == [], "%s: %s" % (name, unexplained)


def test_the_noise_list_is_not_a_dumping_ground():
    """Every entry must actually be provoked by this material. An exemption for
    a rule nothing here trips is an exemption that silently covers a future
    regression instead.
    """
    seen = set()
    with tempfile.TemporaryDirectory() as directory:
        for name in EXAMPLES:
            report = runner.run(_as_package(name, Path(directory)), runner.ALL_KINDS)
            seen |= {f.rule.id for f in report.findings}
    idle = sorted(set(FRAGMENT_NOISE) - seen)
    assert idle == [], "exempted but never provoked: %s" % idle


def test_the_hazard_statement_example_passes_the_rules_it_illustrates():
    """Example 46 is not metadata -- it is the Appendix B tagging markup, and
    it is the only piece of iiRDS XHTML5 in this corpus that tekom wrote.

    The ten B rules have no counterpart in any other tool, and two of them rest on
    readings the specification does not settle, so a conformant sample authored
    by the people who wrote Appendix B is the strongest check available on them.
    A finding here would mean a B rule is too strict.
    """
    from conftest import MINIMAL_RDF, build_package

    fragment = (vendor_corpus.FILES / "Example 46 - Tagging.rdf").read_text("utf-8")
    document = ('<?xml version="1.0" encoding="utf-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Caution</title>'
                "</head><body>%s</body></html>" % fragment)

    with tempfile.TemporaryDirectory() as directory:
        package = build_package(Path(directory), "tagging.iirds", metadata=MINIMAL_RDF,
                                content=(), extra=(("content/topic1.xhtml", document),))
        findings = [f for f in runner.run(package, runner.ALL_KINDS).findings
                    if f.rule.id.startswith("B")]

    assert findings == [], [(f.rule.id, f.violation.message) for f in findings]


def test_m30_separates_copying_the_schema_from_extending_it(tmp_path):
    """The rule this file's oracle found, pinned in both directions.

    M30 forbids restating the iiRDS schema inside metadata.rdf. It used to
    decide that on the subject alone, so any statement *about* an iiRDS term
    was a violation -- including the one the standard's Example 43 exists to
    demonstrate, and including exactly the link L5 asks authors to make. One
    rule forbidding what another recommends is a contradiction that no fixture
    in the reference corpus would ever have surfaced.

    What matters is whether both ends of the statement are the standard's.
    """
    from conftest import MINIMAL_RDF, build_package

    def ids(body, name):
        metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
        package = build_package(tmp_path, name, metadata=metadata)
        return {f.rule.id for f in runner.check(package).findings}

    copied = ids('''  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#InformationObject"/>
  </rdf:Description>
''', "copied.iirds")
    assert "M30" in copied, "a relationship internal to iiRDS is a copy of the ontology"

    redeclared = ids('  <rdfs:Class rdf:about="http://iirds.tekom.de/iirds#Component"/>\n',
                     "redeclared.iirds")
    assert "M30" in redeclared, "typing an iiRDS term as a class restates the schema"

    extended = ids('''  <rdf:Description rdf:about="http://iirds.tekom.de/iirds#Component">
    <rdfs:subClassOf rdf:resource="http://myCompany.com/p#ProductPart"/>
  </rdf:Description>
''', "extended.iirds")
    assert "M30" not in extended, "Example 43: RDFS has no owl:equivalentClass, so " \
                                  "equivalence to a proprietary class is written this way"
