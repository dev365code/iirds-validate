"""Section 8.3.2.1: what an iiRDS/H package's renditions must point at.

Three sentences, and each is the other end of something the checker already
looks at from one side only.

    #2  Each content file MUST be referenced by at least one iirds:Rendition.
    #3  Each rendition must be referenced by at least one iirds:Document and
        therefore MUST use the mandatory relation iirds:has-document-type.
    #5  All renditions MUST reference a whole file.

L2 asks whether every `iirds:source` resolves to a file that is packed; #2 is
the converse and nothing asked it. M15.11c forbids an `iirds:Selector`
*instance* in a handover package, which reports #5 only where the selector is
described here -- a rendition whose `iirds:has-selector` points out of the
package breaks the sentence and was reported by nothing. M15.1 already asks
every document for a document type, which is #3's second clause.

The trap in #2 is one section up: 8.3.1.1 says the content list is *not* an
information unit and MUST NOT be referenced in the metadata file. A rule
reading "every file in the container is referenced" would demand exactly what
that sentence forbids, on the one file every conformant handover package has.
"""
from __future__ import annotations

import pytest

from conftest import build_package
from iirds_validate import runner
from iirds_validate.model import Severity

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Package rdf:about="urn:test:package">
    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>
    <iirds:formatRestriction>H</iirds:formatRestriction>
    <iirds:title>T</iirds:title>
  </iirds:Package>
%s</rdf:RDF>
"""

RENDITION = """    <iirds:has-rendition>
      <iirds:Rendition%s>
        <iirds:format>application/pdf</iirds:format>
        <iirds:source>%s</iirds:source>
%s      </iirds:Rendition>
    </iirds:has-rendition>
"""

DOCUMENT = """  <iirds:Document rdf:about="urn:test:d1">
    <iirds:title>D</iirds:title>
    <iirds:has-document-type rdf:resource="http://iirds.tekom.de/iirds#OperatingInstructions"/>
%s  </iirds:Document>
"""


def report(tmp_path, body, content=("content/a.pdf", "index.html")):
    package = build_package(tmp_path, "handover.iirds",
                            metadata=HEAD % body, content=content)
    return runner.check(package)


def fired(tmp_path, body, **kw):
    return {f.rule.id for f in report(tmp_path, body, **kw).findings}


def conformant_body(extra_rendition_attrs="", selector=""):
    return DOCUMENT % (RENDITION % (extra_rendition_attrs, "content/a.pdf", selector))


# ---------------------------------------------------------------------------
# #2 -- a content file no rendition points at
# ---------------------------------------------------------------------------

def test_a_content_file_no_rendition_points_at_is_reported(tmp_path):
    base = fired(tmp_path, conformant_body())
    with_orphan = fired(tmp_path, conformant_body(),
                        content=("content/a.pdf", "content/orphan.pdf", "index.html"))
    assert "R37" in with_orphan - base, sorted(with_orphan - base)


def test_the_content_list_is_not_an_orphan(tmp_path):
    """`index.html` is in every conformant handover package and is referenced by
    nothing on purpose -- 8.3.1.1 forbids referencing it. Without this the rule
    reports every package the standard requires."""
    assert "R37" not in fired(tmp_path, conformant_body())


def test_the_metadata_and_the_mimetype_are_not_content_files(tmp_path):
    """They are the container's own furniture. A rendition pointing at either
    would be the defect."""
    assert "R37" not in fired(tmp_path, conformant_body(),
                              content=("content/a.pdf", "index.html"))


# ---------------------------------------------------------------------------
# #3 -- a rendition no document points at
# ---------------------------------------------------------------------------

FLOATING = """  <iirds:Rendition rdf:about="urn:test:r9">
    <iirds:format>application/pdf</iirds:format>
    <iirds:source>content/a.pdf</iirds:source>
  </iirds:Rendition>
"""


def test_a_rendition_no_document_points_at_is_reported(tmp_path):
    base = fired(tmp_path, conformant_body())
    loose = fired(tmp_path, conformant_body() + FLOATING)
    assert "R38" in loose - base, sorted(loose - base)


def test_a_rendition_a_document_owns_is_not_reported(tmp_path):
    assert "R38" not in fired(tmp_path, conformant_body())


def test_the_document_type_half_of_that_sentence_is_m15_1(tmp_path):
    """The sentence has two clauses and the second one already had a rule. Both
    claim it, which is what the criterion asks for when neither reports every
    package on its own."""
    from iirds_validate.registry import all_rules
    claimants = {rule.id for rule in all_rules()
                 if "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#3"
                 in (rule.covers or ())}
    assert claimants == {"R38", "M15.1"}, claimants


# ---------------------------------------------------------------------------
# #5 -- a rendition that references part of a file
# ---------------------------------------------------------------------------

SELECTOR_HERE = """        <iirds:has-selector>
          <iirds:FragmentSelector><rdf:value>page=3</rdf:value></iirds:FragmentSelector>
        </iirds:has-selector>
"""
SELECTOR_ELSEWHERE = '        <iirds:has-selector rdf:resource="urn:elsewhere:sel1"/>\n'


@pytest.mark.parametrize("selector,label", [(SELECTOR_HERE, "described here"),
                                            (SELECTOR_ELSEWHERE, "described elsewhere")])
def test_a_rendition_that_selects_part_of_a_file_is_reported(tmp_path, selector, label):
    """Both shapes, because only one of them was reported.

    M15.11c forbids an `iirds:Selector` instance in a handover package, so the
    first shape was already caught -- by a rule about the class, not about the
    reference. The second names a selector the package does not describe: the
    rendition still references part of a file, and nothing said so."""
    base = fired(tmp_path, conformant_body())
    got = fired(tmp_path, conformant_body(selector=selector))
    assert "R39" in got - base, (label, sorted(got - base))


def test_a_rendition_with_no_selector_is_not_reported(tmp_path):
    assert "R39" not in fired(tmp_path, conformant_body())


# ---------------------------------------------------------------------------
# The three together
# ---------------------------------------------------------------------------

CLAIMS = {
    "R37": "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#2",
    "R38": "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#3",
    "R39": "x8-3-2-1-restrictions-regarding-the-use-of-classes-and-instances#5",
}


@pytest.mark.parametrize("rule_id,requirement", sorted(CLAIMS.items()))
def test_each_rule_claims_its_sentence(rule_id, requirement):
    from iirds_validate.registry import all_rules
    rule = {r.id: r for r in all_rules()}.get(rule_id)
    assert rule is not None, "%s is not registered" % rule_id
    assert requirement in (rule.covers or ()), (rule_id, rule.covers)
    assert rule.severity is Severity.ERROR
    assert rule.variants == ("H",), (rule_id, rule.variants)


def test_none_of_them_speaks_outside_the_handover_profile(tmp_path):
    """Section 8.3 is iiRDS/H. An unrestricted package may carry a rendition
    nobody owns, a file nobody renders and a selector on any of them."""
    unrestricted = HEAD.replace(
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n", "")
    package = build_package(
        tmp_path, "plain.iirds",
        metadata=unrestricted % (conformant_body(selector=SELECTOR_ELSEWHERE) + FLOATING),
        content=("content/a.pdf", "content/orphan.pdf", "index.html"))
    assert not ({"R37", "R38", "R39"}
                & {f.rule.id for f in runner.check(package).findings})
