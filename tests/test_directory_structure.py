"""Navigation structure rules (M24.5, M25, M26, M27) and the iiRDS/H limits.

iiRDS models a table of contents as linked lists: a root node carries
`has-directory-structure-type`, descends with `has-first-child`, and each level
is a chain of `has-next-sibling` ending at `iirds:nil`. Four MUSTs govern its
shape, and getting them wrong produces a package that is valid to a
conformance checker and unnavigable to a consumer — which is why L3 and L4
exist alongside them.

The shape used in the "good" fixture below is the shape tekom's own sample
packages use, so a rule that fires on it is wrong.
"""
from __future__ import annotations

from conftest import MINIMAL_RDF
from iirds_validate import runner

HEAD = MINIMAL_RDF.replace("</rdf:RDF>", "")
NIL = 'rdf:resource="http://iirds.tekom.de/iirds#nil"'


def toc(body: str) -> str:
    return HEAD + body + "</rdf:RDF>\n"


#: Root, two children, list terminated at iirds:nil. What the samples do.
GOOD = toc("""
  <iirds:DirectoryNode rdf:about="urn:test:root">
    <iirds:has-directory-structure-type rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>
    <iirds:has-first-child rdf:resource="urn:test:n1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n1">
    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
  <iirds:DirectoryNode rdf:about="urn:test:n2">
    <iirds:has-next-sibling %s/>
    <iirds:relates-to-information-unit rdf:resource="urn:test:topic1"/>
  </iirds:DirectoryNode>
""" % NIL)


def ids(report):
    return {f.rule.id for f in report.findings}


def test_a_well_formed_table_of_contents_is_clean(make_package):
    report = runner.run(make_package(metadata=GOOD), runner.ALL_KINDS)
    assert report.ok, [(f.rule.id, f.violation.message) for f in report.findings]


def test_m24_5_only_the_root_carries_the_structure_type(make_package):
    """A node hanging off another node is not a root, so it must not claim to
    be one — two roots in one structure is ambiguous to a consumer."""
    broken = GOOD.replace(
        '<iirds:DirectoryNode rdf:about="urn:test:n1">',
        '<iirds:DirectoryNode rdf:about="urn:test:n1">\n'
        '    <iirds:has-directory-structure-type '
        'rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>')
    assert "M24.5" in ids(runner.check(make_package(metadata=broken)))


def test_m24_5_tells_the_reader_to_remove_it_from_the_node_it_named(make_package):
    """The finding is about a node that has the property and must not, so the
    remedy is to take it off that node. It said "Add it to the root node",
    which is the catalogue's title -- the neighbouring sentence, about what a
    root must have -- and following it leaves the finding exactly where it
    was. A remedy that does not resolve the finding it is printed under is
    worse than none: the reader does the work and the tool still refuses."""
    broken = GOOD.replace(
        '<iirds:DirectoryNode rdf:about="urn:test:n1">',
        '<iirds:DirectoryNode rdf:about="urn:test:n1">\n'
        '    <iirds:has-directory-structure-type '
        'rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>')
    report = runner.check(make_package(metadata=broken))
    finding = [f for f in report.findings if f.rule.id == "M24.5"][0]
    assert finding.violation.subject == "urn:test:n1"
    # following the remedy clears the finding, which is the whole test: the
    # remedy is read off the finding and applied to the metadata it names
    mended = broken.replace(
        '    <iirds:has-directory-structure-type '
        'rdf:resource="http://iirds.tekom.de/iirds#TableOfContents"/>\n'
        '    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>',
        '    <iirds:has-next-sibling rdf:resource="urn:test:n2"/>')
    assert mended != broken
    assert "M24.5" not in ids(runner.check(make_package(metadata=mended)))
    assert "Add iirds:has-directory-structure-type" not in finding.fix


def test_m25_a_list_must_be_closed_with_nil(make_package):
    """Without a terminator a consumer cannot tell "end of list" from
    "truncated data"."""
    broken = GOOD.replace('    <iirds:has-next-sibling %s/>\n' % NIL, "")
    assert "M25" in ids(runner.check(make_package(metadata=broken)))


def test_m25_does_not_fire_on_the_root(make_package):
    """The root is not an item in a list, so it has no sibling to point at."""
    assert "M25" not in ids(runner.check(make_package(metadata=GOOD)))


def test_m26_first_child_must_be_a_directory_node(make_package):
    broken = GOOD.replace('<iirds:has-first-child rdf:resource="urn:test:n1"/>',
                          '<iirds:has-first-child rdf:resource="urn:test:topic1"/>')
    assert "M26" in ids(runner.check(make_package(metadata=broken)))


def test_m27_first_child_must_start_a_list_not_join_one(make_package):
    """Pointing has-first-child at the middle of an existing chain makes the
    same nodes reachable by two routes and the tree ill-defined."""
    broken = GOOD.replace('<iirds:has-first-child rdf:resource="urn:test:n1"/>',
                          '<iirds:has-first-child rdf:resource="urn:test:n2"/>')
    assert "M27" in ids(runner.check(make_package(metadata=broken)))


def test_m15_11a_handover_packages_carry_documents_only(make_package):
    """iiRDS/H delivers documents. A Topic in an H package is not deliverable
    by the profile's own rules."""
    handover = GOOD.replace(
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n",
        "    <iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>\n"
        "    <iirds:formatRestriction>H</iirds:formatRestriction>\n")
    report = runner.check(make_package(metadata=handover, jsonld="{}",
                                       extra=(("index.html", "<html/>"),)))
    assert "M15.11a" in ids(report)


def test_m25_a_sibling_that_is_not_nil_and_not_a_node_does_not_close_the_list(make_package):
    """M25 used to ask only whether the property was present, and its own
    message asks for more than that: a terminator. A last node pointing at a
    topic satisfied the presence check and left the chain open — the walk
    arrives somewhere that is neither another node nor the end, which is the
    state M25 exists to keep out. Nothing else covers it: M26 checks the range
    of has-first-child, and no other rule looks at has-next-sibling's."""
    broken = GOOD.replace('<iirds:has-next-sibling %s/>' % NIL,
                          '<iirds:has-next-sibling rdf:resource="urn:test:topic1"/>')
    assert "M25" in ids(runner.check(make_package(metadata=broken)))


def test_m25_does_not_fire_on_nil_when_the_package_declares_it(make_package):
    """A package is allowed to state what it points at. Declaring the
    terminator makes it an instance of iirds:DirectoryNode and a linked node,
    which used to make M25 demand that the end of the list have an end of its
    own."""
    declared = GOOD.replace("</rdf:RDF>",
                            '  <iirds:DirectoryNode rdf:about='
                            '"http://iirds.tekom.de/iirds#nil"/>\n</rdf:RDF>')
    assert "M25" not in ids(runner.check(make_package(metadata=declared)))
