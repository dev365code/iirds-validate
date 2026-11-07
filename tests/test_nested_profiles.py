"""The profile of each readable nested container is its own declaration, and
it is compared with the profile of the package that declares the container."""
from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from conftest import MIMETYPE, MINIMAL_RDF, build_package
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


def side_by_side(tmp_path, top=None, middle="A", grand="H", grand_part_of=None, grand_rdf=None,
                 extra=()):
    """Section 6.3.3's layout: the grandchild packed beside its parent in the
    top archive and declared in its parent's own metadata.rdf -- and, given
    `grand_part_of`, declared in the top's metadata.rdf as well, part of that
    package."""
    middle_rdf = package_rdf("urn:test:middle", middle, declares=(("urn:test:grand", None),))
    top_rdf = package_rdf(profile=top, declares=(("urn:test:middle", None),))
    if grand_part_of is not None:
        top_rdf = top_rdf.replace(
            "</rdf:RDF>", '<iirds:Package rdf:about="urn:test:grand"><iirds:iiRDSVersion>1.3'
                          '</iirds:iiRDSVersion><iirds:is-part-of-package rdf:resource="%s"/>'
                          '</iirds:Package></rdf:RDF>' % grand_part_of)
    if grand_rdf is None:
        grand_rdf = package_rdf("urn:test:grand", grand)
    return build_package(tmp_path, "top.iirds", metadata=top_rdf,
                         extra=(("content/middle.iirds", archive(tmp_path, "middle", middle_rdf)),
                                ("content/grand.iirds", archive(tmp_path, "grand", grand_rdf)))
                         + tuple(extra))


def two_parents(tmp_path, first, second, grand="H"):
    """Two middle containers side by side, each declaring the one grandchild
    packed beside them."""
    middles = tuple(("content/%s-middle.iirds" % letter,
                     archive(tmp_path, "m" + letter,
                             package_rdf("urn:test:m" + letter, profile,
                                         declares=(("urn:test:grand", None),))))
                    for letter, profile in (("a", first), ("b", second)))
    return build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(declares=(("urn:test:ma", None), ("urn:test:mb", None))),
                         extra=middles + (("content/grand.iirds",
                                           archive(tmp_path, "grand",
                                                   package_rdf("urn:test:grand", grand))),))


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


def test_each_level_is_compared_with_the_package_packing_it(tmp_path):
    """The iiRDS/A middle container packs an iiRDS/H one inside itself.
    Validated on its own it reports that child; packed in the outer archive,
    the outer run reports it too, under the middle container's place in that
    archive -- the middle package nests it whichever archive is checked."""
    middle_dir = tmp_path / "middle"
    middle_dir.mkdir()
    middle = nested(middle_dir, "H")
    outer = build_package(tmp_path, "enclosing.iirds", metadata=metadata("A"),
                          extra=(("content/middle.iirds", middle.read_bytes()),))
    found = profile_findings(outer)
    assert [f.violation.subject for f in found] == ["content/middle.iirds"]
    assert "content/member-0.iirds, packed inside content/middle.iirds" in found[0].violation.detail
    assert len(profile_findings(middle)) == 1


@pytest.mark.parametrize("declared", ["H", "iiRDS/A"])
@pytest.mark.parametrize("packed", [False, True], ids=["declared-only", "packed-declaring-A"])
def test_a_package_the_parent_declares_as_not_a_is_reported(tmp_path, packed, declared):
    """The parent's own metadata can say what it nests. Section 6.3.3's
    declaration is an iirds:Package, and iirds:formatRestriction is a property
    of one: an iiRDS/A package whose metadata.rdf declares a nested package
    with the restriction H says that it nests an iiRDS/H package, whether the
    archive is packed beside it or not, and whatever that archive says. A
    declaration that writes iiRDS/A is not iiRDS/A either -- the value is A
    -- and the finding says so, as the one about a child's own metadata does."""
    extra = ((("content/child.iirds",
               archive(tmp_path, "child", package_rdf("urn:test:child", "A"))),) if packed else ())
    path = build_package(tmp_path, "enclosing.iirds", extra=extra,
                         metadata=package_rdf(profile="A", declares=(("urn:test:child", declared),)))
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["urn:test:child"]
    assert "iirds:formatRestriction %r" % declared in found[0].violation.detail
    assert found[0].violation.detail.endswith("; iiRDS/A is the value A")


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


@pytest.mark.parametrize("grand", ["H", "A"])
@pytest.mark.parametrize("grand_part_of", ["urn:test:package", "urn:test:middle"],
                         ids=["as-the-tops", "as-the-middles"])
def test_a_grandchild_the_top_declares_as_well_is_held_to_its_parent(tmp_path, grand_part_of,
                                                                      grand):
    """A second declaration in the top's metadata.rdf does not take the
    grandchild from the iiRDS/A package beside it that declares it: every
    package that declares a child is one that nests it, and the iiRDS/A one
    among them asks for an iiRDS/A child."""
    found = profile_findings(side_by_side(tmp_path, grand=grand, grand_part_of=grand_part_of))
    assert [f.violation.subject for f in found] == (["content/grand.iirds"] if grand == "H"
                                                    else [])
    assert all("content/middle.iirds" in f.violation.detail for f in found)


@pytest.mark.parametrize("first,second,declarer", [
    ("A", None, "content/a-middle.iirds"),
    (None, "A", "content/b-middle.iirds"),
    (None, None, None),
], ids=["A-sorts-first", "A-sorts-second", "neither-A"])
def test_every_package_declaring_a_grandchild_is_compared(tmp_path, first, second, declarer):
    """Two packages beside each other can both declare one grandchild. The
    iiRDS/A one asks for an iiRDS/A child, whichever name sorts first."""
    found = profile_findings(two_parents(tmp_path, first, second))
    assert [f.violation.subject for f in found] == ([] if declarer is None
                                                    else ["content/grand.iirds"])
    assert all(declarer in f.violation.detail for f in found)


@pytest.mark.parametrize("middle,grand_part_of,reported", [
    ("A", None, True),
    ("A", "urn:test:package", True),
    (None, "urn:test:package", False),
], ids=["A-middle-declares-it", "the-top-declares-it-as-well", "no-A-package"])
def test_an_unread_grandchild_beside_an_a_parent_is_reported(tmp_path, middle, grand_part_of,
                                                             reported):
    """The grandchild's metadata does not parse, so its IRI is not known and no
    declaration can be matched to it. The iiRDS/A package beside it declares
    a package that no container read here is, which the grandchild can be:
    nothing then shows that the iiRDS/A package nests only iiRDS/A packages."""
    found = profile_findings(side_by_side(tmp_path, middle=middle, grand_part_of=grand_part_of,
                                          grand_rdf="<rdf"))
    assert [f.violation.subject for f in found] == (["content/grand.iirds"] if reported else [])
    assert all("does not parse" in f.violation.detail
               and "content/middle.iirds" in f.violation.detail for f in found)


def test_an_unread_container_no_a_declaration_is_left_for_goes_to_r60(tmp_path):
    """Every package the iiRDS/A middle declares is a container read here, so
    none of its declarations is left for the unread container beside them:
    R60 reports that one, as it does with no middle at all."""
    unread = archive(tmp_path, "other", "<rdf")
    found = runner.check(side_by_side(tmp_path, grand="A",
                                      extra=(("content/other.iirds", unread),))).findings
    assert [f.violation.subject for f in found if f.rule.id == "R75"] == []
    assert [f.violation.subject for f in found if f.rule.id == "R60"] == ["content/other.iirds"]


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


def zipped(*entries):
    """An archive of (name, bytes, compression) entries, the clock left out."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data, method in entries:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = method
            zf.writestr(info, data)
    return buffer.getvalue()


def second_own_package(profile, other_iri, other_profile=None):
    """A middle container's own metadata naming a second package of its own:
    one part of no package, which is not a package it nests."""
    about = "" if other_iri is None else ' rdf:about="%s"' % other_iri
    said = ("" if other_profile is None
            else "<iirds:formatRestriction>%s</iirds:formatRestriction>" % other_profile)
    return package_rdf("urn:test:middle", profile).replace(
        "</rdf:RDF>", '<iirds:Package%s><iirds:iiRDSVersion>1.3</iirds:iiRDSVersion>%s'
                      '</iirds:Package></rdf:RDF>' % (about, said))


def test_a_declared_child_matched_by_its_rendition_is_reported_when_not_read(tmp_path):
    """Until 1.2 a parent named its child's archive by iirds:has-rendition, and
    1.3 does not forbid it. The rendition says which declaration is the
    child's when the child's own metadata does not, because it is not read:
    the iiRDS/A parent declares it, and R60 has nothing to say."""
    rdf = package_rdf(profile="A").replace(
        "</rdf:RDF>", '<iirds:Package rdf:about="urn:test:child"><iirds:iiRDSVersion>1.3'
                      '</iirds:iiRDSVersion><iirds:is-part-of-package rdf:resource='
                      '"urn:test:package"/><iirds:has-rendition><iirds:Rendition><iirds:source>'
                      'content/child.iirds</iirds:source><iirds:format>application/iirds+zip'
                      '</iirds:format></iirds:Rendition></iirds:has-rendition></iirds:Package>'
                      '</rdf:RDF>')
    path = build_package(tmp_path, "enclosing.iirds", metadata=rdf,
                         extra=(("content/child.iirds", archive(tmp_path, "child", "<rdf")),))
    found = runner.check(path).findings
    assert [f.violation.subject for f in found if f.rule.id == "R75"] == ["content/child.iirds"]
    assert not any(f.rule.id == "R60" for f in found)


def test_a_declaration_matched_to_a_read_child_is_not_left_for_an_unread_one(tmp_path):
    """The one package the iiRDS/A parent declares is its readable child's, so
    none is left that the unread child beside it can be: R60 reports that
    one, and this rule does not take it."""
    path = build_package(tmp_path, "enclosing.iirds",
                         metadata=package_rdf(profile="A", declares=(("urn:test:child", None),)),
                         extra=(("content/child.iirds",
                                 archive(tmp_path, "child", package_rdf("urn:test:child", "A"))),
                                ("content/other.iirds", archive(tmp_path, "other", "<rdf"))))
    found = runner.check(path).findings
    assert [f.violation.subject for f in found if f.rule.id == "R60"] == ["content/other.iirds"]
    assert [f.violation.subject for f in found if f.rule.id == "R75"] == []


@pytest.mark.parametrize("other_iri,other_profile,unread_beside", [
    ("urn:test:other", "H", False),
    (None, None, True),
], ids=["second-own-package-saying-H", "second-own-package-without-an-IRI-beside-an-unread-one"])
def test_a_second_package_of_a_childs_own_is_not_one_it_declares(tmp_path, other_iri,
                                                                 other_profile, unread_beside):
    """Section 6.3.3 declares a nested package as part of its parent. A
    package the iiRDS/A middle's own metadata leaves part of nothing is one of
    its own, not one it nests: neither its profile nor an unread container
    beside it is held to the middle's."""
    extra = [("content/middle.iirds",
              archive(tmp_path, "middle", second_own_package("A", other_iri, other_profile)))]
    if unread_beside:
        extra.append(("content/other.iirds", archive(tmp_path, "other", "<rdf")))
    path = build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(declares=(("urn:test:middle", None),)),
                         extra=tuple(extra))
    assert profile_findings(path) == []


@pytest.mark.parametrize("damage,said", [
    ("cut", "could not be read as a ZIP archive"),
    ("entities", "was refused: the document declares XML entities"),
    ("no-metadata", "the archive has no META-INF/metadata.rdf"),
    ("bzip2", "its META-INF/metadata.rdf is stored with bzip2 (method 12), which is not read"),
    ("metadata-past-the-bound",
     "its META-INF/metadata.rdf is past the 4096 byte bound a metadata file is read to"),
])
def test_an_unread_declared_child_says_what_stopped_the_read(tmp_path, monkeypatch, damage, said):
    """The other ways a declared child's metadata goes unread: an archive that
    begins as an iiRDS archive does and ends before its central directory, a
    metadata.rdf the reader refuses rather than fails to parse, none at all,
    one compressed with a method the reader does not decompress, and one
    larger than a metadata file is read to inside an archive that is not.
    The finding names which, because the remedy differs."""
    if damage == "cut":
        whole = archive(tmp_path, "whole", package_rdf("urn:test:child", "A"))
        child = whole[:whole.rfind(b"PK\x01\x02")]
    elif damage == "entities":
        rdf = package_rdf("urn:test:child", "A").replace(
            "<rdf:RDF", '<!DOCTYPE rdf:RDF [<!ENTITY a "A">]>\n<rdf:RDF', 1)
        child = archive(tmp_path, "child", rdf)
    elif damage == "no-metadata":
        child = build_package(tmp_path, "child.iirds", metadata=None).read_bytes()
    else:
        rdf = package_rdf("urn:test:child", "A")
        method = zipfile.ZIP_BZIP2 if damage == "bzip2" else zipfile.ZIP_DEFLATED
        if damage == "metadata-past-the-bound":
            rdf = rdf.replace("<rdf:RDF", "<!--%s-->\n<rdf:RDF" % (" " * 8192), 1)
            monkeypatch.setattr(container_rules, "MAX_METADATA_BYTES", 4096)
        child = zipped(("mimetype", MIMETYPE, zipfile.ZIP_STORED),
                       ("META-INF/metadata.rdf", rdf, method))
        assert damage == "bzip2" or len(child) < 4096 < len(rdf)
    path = build_package(tmp_path, "enclosing.iirds",
                         metadata=package_rdf(profile="A", declares=(("urn:test:child", None),)),
                         extra=(("content/child.iirds", child),))
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["content/child.iirds"]
    assert said in found[0].violation.detail


def packed_inside(tmp_path, middle_rdf, inner, top=None):
    """A middle container in the top archive with `inner` -- (entry name,
    archive bytes) pairs -- packed inside it rather than beside it."""
    folder = tmp_path / "middle"
    folder.mkdir()
    middle = build_package(folder, "middle.iirds", metadata=middle_rdf,
                           extra=tuple(inner)).read_bytes()
    return build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(profile=top, declares=(("urn:test:middle", None),)),
                         extra=(("content/middle.iirds", middle),))


def holding(tmp_path, name, rdf, inner=(), filler=0):
    """A container's bytes: `rdf` as its metadata, `inner` packed inside it,
    and `filler` bytes that do not compress."""
    folder = tmp_path / name
    folder.mkdir()
    noise = b"".join(hashlib.sha256(b"%d" % i).digest() for i in range(filler // 32))
    extra = tuple(inner) + ((("content/filler.bin", noise),) if filler else ())
    return build_package(folder, name + ".iirds", metadata=rdf, extra=extra).read_bytes()


@pytest.mark.parametrize("top", [None, "A"], ids=["unrestricted-top", "A-top"])
@pytest.mark.parametrize("declared,inner,reported", [
    (False, "H", True),
    (True, "H", True),
    (False, "A", False),
], ids=["H-undeclared", "H-declared-without-a-profile", "A"])
def test_a_package_an_a_container_packs_inside_itself_is_held_to_it(tmp_path, top, declared,
                                                                    inner, reported):
    '''"An iiRDS/A package MUST nest only iiRDS/A packages"

    Section 6.3.3 packs nested containers side by side in the top archive,
    and a container can pack one inside itself all the same: the package it
    packs is one it nests, declared or not. The finding's subject is where the
    container is in this archive, and its detail says what it packs.'''
    middle = package_rdf("urn:test:middle", "A",
                         declares=(("urn:test:inner", None),) if declared else ())
    path = packed_inside(tmp_path, middle, (("content/inner.iirds",
                                             holding(tmp_path, "inner",
                                                     package_rdf("urn:test:inner", inner))),),
                         top=top)
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == (["content/middle.iirds"] if reported else [])
    assert all("content/inner.iirds, packed inside content/middle.iirds" in f.violation.detail
               and "iirds:formatRestriction 'H'" in f.violation.detail for f in found)


@pytest.mark.parametrize("middle", [None, "H"], ids=["unrestricted-middle", "H-middle"])
def test_what_a_container_that_is_not_a_packs_is_not_this_rules(tmp_path, middle):
    inner = holding(tmp_path, "inner", package_rdf("urn:test:inner", "H"))
    path = packed_inside(tmp_path, package_rdf("urn:test:middle", middle),
                         (("content/inner.iirds", inner),))
    assert profile_findings(path) == []


def test_a_package_packed_two_levels_down_is_held_to_the_one_packing_it(tmp_path):
    """Inside the unrestricted middle container an iiRDS/A one, and inside
    that an iiRDS/H one: the iiRDS/A package packing it nests it."""
    deepest = holding(tmp_path, "deepest", package_rdf("urn:test:deepest", "H"))
    inner = holding(tmp_path, "inner", package_rdf("urn:test:inner", "A"),
                    (("content/deepest.iirds", deepest),))
    found = profile_findings(packed_inside(tmp_path, package_rdf("urn:test:middle"),
                                           (("content/inner.iirds", inner),)))
    assert [f.violation.subject for f in found] == ["content/middle.iirds"]
    assert ("content/deepest.iirds, packed inside content/inner.iirds inside "
            "content/middle.iirds" in found[0].violation.detail)


@pytest.mark.parametrize("declared", [False, True], ids=["undeclared", "declared"])
def test_an_unread_package_an_a_container_packs_inside_itself_is_reported(tmp_path, declared):
    """A container packed inside an iiRDS/A one is that package's child,
    declared or not, so one whose own metadata is not read has not been shown
    to be iiRDS/A. R60 asks what the top package declares for the containers
    in its own archive, and says nothing about it."""
    middle = package_rdf("urn:test:middle", "A",
                         declares=(("urn:test:inner", None),) if declared else ())
    path = packed_inside(tmp_path, middle,
                         (("content/inner.iirds", holding(tmp_path, "inner", "<rdf")),))
    found = runner.check(path).findings
    profiles = [f for f in found if f.rule.id == "R75"]
    assert [f.violation.subject for f in profiles] == ["content/middle.iirds"]
    assert "content/inner.iirds, packed inside content/middle.iirds" in profiles[0].violation.detail
    assert "does not parse" in profiles[0].violation.detail
    assert not any(f.rule.id == "R60" for f in found)


def test_a_declaration_a_packed_container_accounts_for_is_not_left_for_an_unread_one(tmp_path):
    """The package the iiRDS/A middle declares is packed inside it and read,
    so the declaration is not one the unread container beside the middle can
    be: R60 reports that one, and this rule does not."""
    middle = holding(tmp_path, "middle", package_rdf("urn:test:middle", "A",
                                                      declares=(("urn:test:inner", None),)),
                     (("content/inner.iirds",
                       holding(tmp_path, "inner", package_rdf("urn:test:inner", "A"))),))
    path = build_package(tmp_path, "top.iirds",
                         metadata=package_rdf(declares=(("urn:test:middle", None),)),
                         extra=(("content/middle.iirds", middle),
                                ("content/other.iirds", holding(tmp_path, "other", "<rdf"))))
    found = runner.check(path).findings
    assert [f.violation.subject for f in found if f.rule.id == "R75"] == []
    assert [f.violation.subject for f in found if f.rule.id == "R60"] == ["content/other.iirds"]


def test_what_is_packed_past_the_bound_is_not_read(tmp_path, monkeypatch):
    """The containers packed inside one in this archive are read to the bound
    one nested container is read to, all of them together. Past it the
    reading stops, and a container it did not read inside an iiRDS/A package
    is reported as one whose metadata was not read. Lowering the bound to the
    middle container's size takes the line a deep tree past 64 MiB takes,
    without writing one."""
    deepest = holding(tmp_path, "deepest", package_rdf("urn:test:deepest", "A"), filler=4096)
    inner = holding(tmp_path, "inner", package_rdf("urn:test:inner", "A"),
                    (("content/deepest.iirds", deepest),))
    path = packed_inside(tmp_path, package_rdf("urn:test:middle", "A"),
                         (("content/inner.iirds", inner),))
    assert profile_findings(path) == []
    with zipfile.ZipFile(path) as top:
        bound = top.getinfo("content/middle.iirds").file_size
    assert len(inner) <= bound < len(inner) + len(deepest)
    monkeypatch.setattr(container_rules, "MAX_METADATA_BYTES", bound)
    found = profile_findings(path)
    assert [f.violation.subject for f in found] == ["content/middle.iirds"]
    assert "content/deepest.iirds, packed inside content/inner.iirds" in found[0].violation.detail
    assert ("the containers packed inside content/middle.iirds are read to %d bytes together"
            % bound in found[0].violation.detail)


def test_a_container_that_packs_itself_is_compared_once(tmp_path, monkeypatch):
    """A ZIP archive can be written to contain itself, so that opening each
    copy finds the next. A container packed inside one whose bytes it has is
    that container again: it is compared with the one packing it once, and
    not opened again. The read is made to answer with the middle's own bytes,
    which is what such an archive gives."""
    inner = holding(tmp_path, "inner", package_rdf("urn:test:inner", "A"))
    path = packed_inside(tmp_path, package_rdf("urn:test:middle", "H"),
                         (("content/inner.iirds", inner),))
    with zipfile.ZipFile(path) as top:
        middle = top.read("content/middle.iirds")
    real = container_rules._own_metadata

    def as_if_packed_in_itself(package, name, *args, **kwargs):
        if name == "content/inner.iirds":
            package = type("Itself", (), {"read_bounded": staticmethod(
                lambda _name, limit: (middle[:limit + 1], len(middle) > limit))})()
        return real(package, name, *args, **kwargs)

    monkeypatch.setattr(container_rules, "_own_metadata", as_if_packed_in_itself)
    monkeypatch.setattr(container_rules, "MAX_METADATA_BYTES", 16 * len(middle))
    found = [f for f in runner.check(path).findings if f.rule.id == "R9"]
    assert [f.violation.detail.split(";")[0] for f in found] == [
        "content/inner.iirds, packed inside content/middle.iirds"]
