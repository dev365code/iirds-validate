"""The query surface: closure over what the package itself declares.

Section 7 of iiRDS lets a package subclass the standard's classes and
requires consumers to treat instances as the parent. Exact typing is how
that gets forgotten one rule at a time — the validator's changelog
records two rules caught doing exactly that. The SDK therefore answers
"instances of X" with the data-declared closure, and nothing else: it
bundles no ontology, so its answer is always a subset of the
validator's, never a contradiction.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_roundtrip import MINIMAL_RDF  # noqa: E402

import iirds  # noqa: E402
from iirds import IIRDS  # noqa: E402


@pytest.fixture
def package(tmp_path):
    def build(metadata=MINIMAL_RDF):
        root = tmp_path / "pkg"
        if root.exists():
            import shutil
            shutil.rmtree(root)
        (root / "META-INF").mkdir(parents=True)
        (root / "META-INF" / "metadata.rdf").write_text(metadata, "utf-8")
        return iirds.open(iirds.pack(root, tmp_path / "p.iirds", overwrite=True))
    return build


def _with(body):
    head = MINIMAL_RDF.replace(
        'xmlns:iirds="http://iirds.tekom.de/iirds#">',
        'xmlns:iirds="http://iirds.tekom.de/iirds#" '
        'xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#">')
    return head.replace("</rdf:RDF>", body + "</rdf:RDF>")


CHAIN = _with("""  <rdf:Description rdf:about="urn:acme:ServiceTopic">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Topic"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:acme:PumpServiceTopic">
    <rdfs:subClassOf rdf:resource="urn:acme:ServiceTopic"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:special">
    <rdf:type rdf:resource="urn:acme:ServiceTopic"/>
  </rdf:Description>
  <rdf:Description rdf:about="urn:test:deeper">
    <rdf:type rdf:resource="urn:acme:PumpServiceTopic"/>
  </rdf:Description>
""")


PLAIN_TOPIC = MINIMAL_RDF.replace("</rdf:RDF>", """  <iirds:Topic rdf:about="urn:test:topic1">
    <iirds:title>A directly typed topic</iirds:title>
  </iirds:Topic>
</rdf:RDF>""")


def test_instances_of_finds_directly_typed_subjects(package):
    pkg = package(PLAIN_TOPIC)
    subjects = {str(s) for s in pkg.instances_of(IIRDS["Topic"])}
    assert "urn:test:topic1" in subjects


def test_instances_of_sees_a_package_declared_subclass(package):
    pkg = package(CHAIN)
    subjects = {str(s) for s in pkg.instances_of(IIRDS["Topic"])}
    assert "urn:test:special" in subjects


def test_instances_of_follows_a_two_level_subclass_chain(package):
    pkg = package(CHAIN)
    subjects = {str(s) for s in pkg.instances_of(IIRDS["Topic"])}
    assert "urn:test:deeper" in subjects


def test_instances_of_does_not_invent_the_standards_hierarchy(package):
    """The SDK bundles no ontology, so iirds:InformationUnit yields only
    what the package itself declares beneath it — a documented boundary,
    and a tripwire against a future implementer hard-coding the tree."""
    pkg = package()
    assert pkg.instances_of(IIRDS["InformationUnit"]) == []


def test_subclasses_of_includes_the_class_itself(package):
    pkg = package(CHAIN)
    closure = iirds.subclasses_of(pkg.graph, IIRDS["Topic"])
    assert IIRDS["Topic"] in closure and len(closure) == 3


def test_is_instance_agrees_with_instances_of(package):
    pkg = package(CHAIN)
    for node in pkg.instances_of(IIRDS["Topic"]):
        assert pkg.is_instance(node, IIRDS["Topic"])


LABELLED = _with("""  <rdf:Description rdf:about="urn:test:both">
    <rdfs:label>the label</rdfs:label>
    <iirds:title>the title</iirds:title>
  </rdf:Description>
""")


def test_label_of_prefers_rdfs_label_over_iirds_title(package):
    pkg = package(LABELLED)
    from rdflib import URIRef
    assert pkg.label_of(URIRef("urn:test:both")) == "the label"


def test_label_of_falls_back_to_the_node_itself(package):
    pkg = package()
    from rdflib import URIRef
    assert pkg.label_of(URIRef("urn:test:nowhere")) == "urn:test:nowhere"


STRAY_VERSION = MINIMAL_RDF.replace(
    "<iirds:iiRDSVersion> 1.3 </iirds:iiRDSVersion>\n    ", ""
).replace("</rdf:RDF>", """  <rdf:Description rdf:about="urn:test:not-a-package">
    <iirds:iiRDSVersion>9.9</iirds:iiRDSVersion>
  </rdf:Description>
</rdf:RDF>""")


def test_version_comes_from_the_package_node(package):
    """A version literal on some non-Package subject is noise, not the
    declaration. The validator reads it off the Package node; two answers
    to one question in the two repos this SDK exists to align would be
    the ecosystem's bug, not a style choice."""
    pkg = package(STRAY_VERSION)
    assert pkg.version is None


SUBCLASSED_PACKAGE = _with("""  <rdf:Description rdf:about="urn:acme:Delivery">
    <rdfs:subClassOf rdf:resource="http://iirds.tekom.de/iirds#Package"/>
  </rdf:Description>
""").replace('<iirds:Package rdf:about="urn:test:package">',
             '<rdf:Description rdf:about="urn:test:package">\n'
             '    <rdf:type rdf:resource="urn:acme:Delivery"/>'
).replace("</iirds:Package>", "</rdf:Description>")


def test_version_is_read_through_a_package_subclass(package):
    pkg = package(SUBCLASSED_PACKAGE)
    assert pkg.version == "1.3"


def test_variant_comes_from_the_package_node(package):
    stray = MINIMAL_RDF.replace("</rdf:RDF>", """  <rdf:Description rdf:about="urn:test:not-a-package">
    <iirds:formatRestriction>H</iirds:formatRestriction>
  </rdf:Description>
</rdf:RDF>""")
    pkg = package(stray)
    assert pkg.variant == "unrestricted"


def test_the_published_namespace_is_bracket_safe():
    """rdflib's Namespace subclasses str, so IIRDS.format is str.format —
    a bound method, silently. Bracket syntax is always the property. This
    pins the trap so an rdflib behaviour change is noticed here first."""
    assert str(IIRDS["format"]) == "http://iirds.tekom.de/iirds#format"
    assert not isinstance(IIRDS.format, str)
