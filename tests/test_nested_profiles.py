"""The profile of each readable nested container is its own declaration, and
it is compared with the profile of the package that declares the container."""
from __future__ import annotations

import zipfile

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules
from iirds_validate.rules import container as container_rules


def metadata(profile=None, version="1.3"):
    text = MINIMAL_RDF.replace(">1.3<", ">%s<" % version)
    profiles = () if profile is None else (profile if isinstance(profile, tuple) else (profile,))
    declaration = "".join("<iirds:formatRestriction>%s</iirds:formatRestriction>" % p
                          for p in profiles)
    return text.replace("</iirds:Package>", declaration + "</iirds:Package>")


def nested(tmp_path, child_profile=None, parent_profile="A", child_rdf=None, count=1,
           version="1.3"):
    inner = tmp_path / "member"
    inner.mkdir()
    child = build_package(inner, "member.iirds", metadata=(metadata(child_profile)
                          if child_rdf is None else child_rdf))
    return build_package(tmp_path, "enclosing.iirds", metadata=metadata(parent_profile, version),
                         extra=tuple(("content/member-%d.iirds" % i, child.read_bytes())
                                     for i in range(count)))


def profile_findings(path):
    return [f for f in runner.check(path).findings if f.rule.id == "R75"]


def package_rdf(iri="urn:test:package", profile=None, declares=()):
    """A package's own metadata.rdf under its own IRI, with each (IRI, profile)
    in `declares` declared as a package nested in it, the way section 6.3.3
    asks the parent to: an iirds:Package part of this one."""
    text = metadata(profile).replace('rdf:about="urn:test:package"', 'rdf:about="%s"' % iri)
    declared = "".join(
        '<iirds:Package rdf:about="%s"><iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>%s'
        '<iirds:is-part-of-package rdf:resource="%s"/></iirds:Package>'
        % (child, "" if child_profile is None
           else "<iirds:formatRestriction>%s</iirds:formatRestriction>" % child_profile, iri)
        for child, child_profile in declares)
    return text.replace("</rdf:RDF>", declared + "</rdf:RDF>")


def archive(tmp_path, name, rdf):
    folder = tmp_path / name
    folder.mkdir()
    return build_package(folder, name + ".iirds", metadata=rdf).read_bytes()


def declared_child(tmp_path, child_rdf, parent_profile="A"):
    """A parent that declares its one nested package and packs its archive."""
    return build_package(tmp_path, "enclosing.iirds",
                         metadata=package_rdf(profile=parent_profile,
                                              declares=(("urn:test:child", None),)),
                         extra=(("content/child.iirds", archive(tmp_path, "child", child_rdf)),))


def side_by_side(tmp_path, top=None, middle="A", grand="H"):
    """Section 6.3.3's layout: the grandchild packed beside its parent in the
    top archive and declared in its parent's own metadata.rdf."""
    middle_rdf = package_rdf("urn:test:middle", middle, declares=(("urn:test:grand", None),))
    return build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(profile=top, declares=(("urn:test:middle", None),)),
                         extra=(("content/middle.iirds", archive(tmp_path, "middle", middle_rdf)),
                                ("content/grand.iirds",
                                 archive(tmp_path, "grand", package_rdf("urn:test:grand", grand)))))


@pytest.mark.parametrize("child_profile", ["H", None])
def test_a_parent_requires_a_children(tmp_path, child_profile):
    '''"An iiRDS/A package MUST nest only iiRDS/A packages, an iiRDS/H package MUST nest only iiRDS/H packages."'''
    path = nested(tmp_path, child_profile)
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["content/member-0.iirds"]
    assert all(f.severity.value == "error" for f in found)
    claim = "x8-1-1-unrestricted-iirds-vs-restricted-iirds#2"
    assert sorted(r.id for r in all_rules() if claim in r.covers) == ["R75"]


@pytest.mark.parametrize("parent_profile,child_profile", [("A", "A"), (None, "H"), ("H", "A")])
def test_other_profile_pairs_are_left_to_their_rules(tmp_path, parent_profile, child_profile):
    assert profile_findings(nested(tmp_path, child_profile, parent_profile)) == []


def test_unread_child_is_reported_by_r60(tmp_path):
    path = nested(tmp_path, child_rdf="<rdf")
    found = runner.check(path).findings
    assert not any(f.rule.id in {"R75", "S3"} for f in found)
    assert any(f.rule.id == "R60" for f in found)


def test_each_child_is_compared(tmp_path):
    path = nested(tmp_path, "H", count=2)
    assert sorted(f.violation.subject for f in profile_findings(path)) == [
        "content/member-0.iirds", "content/member-1.iirds"]


def test_multiple_child_profiles_use_the_shared_detection(tmp_path):
    from rdflib import Graph

    from iirds_validate.context import _detect

    text = metadata(("H", "A"))
    variant = _detect(Graph().parse(data=text, format="xml"))[1]
    found = profile_findings(nested(tmp_path, child_rdf=text))
    assert bool(found) == (variant != "A")


def test_an_empty_child_graph_has_no_profile(tmp_path):
    text = '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>'
    assert len(profile_findings(nested(tmp_path, child_rdf=text))) == 1


def test_an_older_parent_does_not_run_the_rule(tmp_path):
    assert profile_findings(nested(tmp_path, "H", version="1.0")) == []


def test_each_level_uses_its_direct_children(tmp_path):
    middle_dir = tmp_path / "middle"
    middle_dir.mkdir()
    middle = nested(middle_dir, "H")
    outer = build_package(tmp_path, "enclosing.iirds", metadata=metadata("A"),
                          extra=(("content/middle.iirds", middle.read_bytes()),))
    assert profile_findings(outer) == []
    assert len(profile_findings(middle)) == 1


@pytest.mark.parametrize("packed", [False, True], ids=["declared-only", "packed-declaring-A"])
def test_a_package_the_parent_declares_as_not_a_is_reported(tmp_path, packed):
    """The parent's own metadata can say what it nests. Section 6.3.3's
    declaration is an iirds:Package, and iirds:formatRestriction is a property
    of one: an iiRDS/A package whose metadata.rdf declares a nested package
    with the restriction H says that it nests an iiRDS/H package, whether the
    archive is packed beside it or not, and whatever that archive says."""
    extra = ((("content/child.iirds",
               archive(tmp_path, "child", package_rdf("urn:test:child", "A"))),) if packed else ())
    path = build_package(tmp_path, "enclosing.iirds", extra=extra,
                         metadata=package_rdf(profile="A", declares=(("urn:test:child", "H"),)))
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["urn:test:child"]
    assert "iirds:formatRestriction 'H'" in found[0].violation.detail


def test_a_declaration_in_a_nested_container_is_its_own(tmp_path):
    """One level down the same: an iiRDS/A child whose own metadata.rdf
    declares an iiRDS/H package nests one, and the finding says where."""
    middle_rdf = package_rdf("urn:test:middle", "A", declares=(("urn:test:grand", "H"),))
    path = build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(declares=(("urn:test:middle", None),)),
                         extra=(("content/middle.iirds", archive(tmp_path, "middle", middle_rdf)),))
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["urn:test:grand"]
    assert "content/middle.iirds" in found[0].violation.detail


@pytest.mark.parametrize("declared_profile", ["A", None])
def test_a_declaration_saying_a_or_nothing_is_not_reported(tmp_path, declared_profile):
    """A declaration with no profile has none of its own to compare: Example
    16 puts the child's profile in the child's own metadata, and a package
    declared and not packed is section 6.3.3's question."""
    path = build_package(tmp_path, "enclosing.iirds",
                         metadata=package_rdf(profile="A",
                                              declares=(("urn:test:child", declared_profile),)))
    assert profile_findings(path) == []


def test_a_declared_child_whose_metadata_does_not_parse_is_reported(tmp_path):
    """A declared child whose own metadata is not read has not been shown to
    be iiRDS/A. R60 says nothing here, because a declaration is there that
    can be the child's, so this rule is the one that does."""
    found = runner.check(declared_child(tmp_path, "<rdf")).findings
    profiles = [f for f in found if f.rule.id == "R75"]
    assert [f.violation.subject for f in profiles] == ["content/child.iirds"]
    assert "does not parse" in profiles[0].violation.detail
    assert not any(f.rule.id == "R60" for f in found)


def test_a_declared_child_past_the_bound_is_reported(tmp_path, monkeypatch):
    """The bound a nested container is read to is this project's number and
    the child is legal; that its metadata was never read is not a reading of
    its profile. Lowering the bound below the child's size takes the line a
    child past 64 MiB takes, without writing one."""
    path = declared_child(tmp_path, package_rdf("urn:test:child", "H"))
    with zipfile.ZipFile(path) as top:
        size = top.getinfo("content/child.iirds").file_size
    shipped = profile_findings(path)
    assert [f.violation.subject for f in shipped] == ["content/child.iirds"]
    assert "not read" not in shipped[0].violation.message
    monkeypatch.setattr(container_rules, "MAX_METADATA_BYTES", size - 1)
    found = runner.check(path).findings
    profiles = [f for f in found if f.rule.id == "R75"]
    assert [f.violation.subject for f in profiles] == ["content/child.iirds"]
    assert "past the %d byte bound" % (size - 1) in profiles[0].violation.detail
    assert not any(f.rule.id == "R60" for f in found)


@pytest.mark.parametrize("parent_profile", [None, "H"])
def test_an_unread_child_of_a_package_that_is_not_a_is_not_reported(tmp_path, parent_profile):
    assert profile_findings(declared_child(tmp_path, "<rdf", parent_profile)) == []


@pytest.mark.parametrize("top", [None, "A"], ids=["unrestricted-top", "A-top"])
def test_a_grandchild_beside_its_parent_is_compared_with_that_parent(tmp_path, top):
    '''"All nested iiRDS containers MUST be included side by side in the iiRDS ZIP archive of the highest level iiRDS package."

    So a grandchild is packed beside its parent, and R60 reads a child
    declared in a sibling's metadata.rdf as that sibling's child. The iiRDS/A
    middle container nests the iiRDS/H grandchild whatever the top is.'''
    found = profile_findings(side_by_side(tmp_path, top))
    assert [f.violation.subject for f in found] == ["content/grand.iirds"]
    assert "content/middle.iirds" in found[0].violation.detail


@pytest.mark.parametrize("top,middle,grand", [(None, "A", "A"), (None, None, "H"), ("A", "A", "A")])
def test_a_grandchild_its_parent_may_nest_is_not_reported(tmp_path, top, middle, grand):
    assert profile_findings(side_by_side(tmp_path, top, middle, grand)) == []


@pytest.mark.parametrize("child_profile,said", [
    ("iiRDS/A", "iirds:formatRestriction 'iiRDS/A'; iiRDS/A is the value A"),
    (None, "declares no iirds:formatRestriction"),
])
def test_the_finding_says_what_the_child_declared(tmp_path, child_profile, said):
    """A child that writes iiRDS/A is not iiRDS/A -- the value is A -- and a
    report saying "does not declare iiRDS/A" over "child profile: iiRDS/A"
    reads as contradicting itself. The detail gives the value as written."""
    found = profile_findings(nested(tmp_path, child_profile))
    assert len(found) == 1 and said in found[0].violation.detail
    assert "as iirds:formatRestriction A" in found[0].fix


@pytest.mark.parametrize("damage,said", [
    ("cut", "could not be read as a ZIP archive"),
    ("entities", "was refused: the document declares XML entities"),
])
def test_an_unread_declared_child_says_what_stopped_the_read(tmp_path, damage, said):
    """The two other ways a declared child's metadata goes unread: an archive
    that begins as an iiRDS archive does and ends before its central
    directory, and a metadata.rdf the reader refuses rather than fails to
    parse. The finding names which, because the remedy differs."""
    if damage == "cut":
        whole = archive(tmp_path, "whole", package_rdf("urn:test:child", "A"))
        child = whole[:whole.rfind(b"PK\x01\x02")]
    else:
        rdf = package_rdf("urn:test:child", "A").replace(
            "<rdf:RDF", '<!DOCTYPE rdf:RDF [<!ENTITY a "A">]>\n<rdf:RDF', 1)
        child = archive(tmp_path, "child", rdf)
    path = build_package(tmp_path, "enclosing.iirds",
                         metadata=package_rdf(profile="A", declares=(("urn:test:child", None),)),
                         extra=(("content/child.iirds", child),))
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["content/child.iirds"]
    assert said in found[0].violation.detail
