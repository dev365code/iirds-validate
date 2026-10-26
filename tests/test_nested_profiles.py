"""The profile of each readable nested container is its own declaration."""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules


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
