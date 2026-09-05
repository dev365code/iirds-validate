"""Appendix A's "IRI: REQUIRED" rows, each held by a package that breaks it.

Appendix A states, per class, that instances must have an IRI. Fifty-six of
those rows are among the two hundred and eighty obligations this project
publishes a coverage figure against, and fifty of them were being checked by
`src/iirds_validate/rules/schema_tables.py` — a table generated *from the same
appendix* and never told which of its rows each rule was answering. So the
figure said fifty fewer than the tool could defend, which is the opposite of
the error this project guards against and just as wrong.

Claiming them is only worth anything if each claim is shown rather than
matched by name, and the sentence has exactly one shape: an instance of the
class with no IRI. That is a blank node, so each case is one blank node typed
with one class, and the rule that claims the row has to report it.

Three rows are not claimed and are here as refusals, because two rules check
each of those classes and which one answers the row is a question for a person.
A fourth has no rule at all. `tools/appendix_a_map.py` prints them with its
reasons and refuses to propose them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.registry import all_rules

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

#: `rdfclasses_<domain>_<Class>#<n>` — the row's id carries the class it is
#: about, which is what makes the mapping checkable at all.
ROW = re.compile(r"^rdfclasses_(\w+?)_(\w+)#\d+$")

NAMESPACE = {
    "core": "http://iirds.tekom.de/iirds#",
    "handover": "http://iirds.tekom.de/iirds/domain/handover#",
    "machinery": "http://iirds.tekom.de/iirds/domain/machinery#",
    "software": "http://iirds.tekom.de/iirds/domain/software#",
}


def _iri_rows():
    """The appendix ids whose sentence is "IRI: REQUIRED", read from the index.

    Not every `rdfclasses_` id is one — the same table states cardinalities,
    and R17 claims one of those. Matching on the id alone put a cardinality row
    in here and asked a blank node to provoke it.
    """
    import json

    index = json.loads((ROOT / "docs" / "requirements.json").read_text("utf-8"))
    return {row["id"] for row in index["requirements"]
            if " ".join(row["sentence"].split()) == "IRI: REQUIRED"}


def _claimed_iri_rows():
    """(requirement, rule id, class IRI) for every appendix A IRI row a rule claims."""
    iri = _iri_rows()
    out = []
    for rule in all_rules():
        for requirement in rule.covers or ():
            match = ROW.match(requirement)
            if not match or requirement not in iri:
                continue
            domain, class_name = match.groups()
            if domain not in NAMESPACE:
                continue
            out.append((requirement, rule.id, NAMESPACE[domain] + class_name))
    return sorted(out)


CLAIMED = _claimed_iri_rows()


def test_the_appendix_rows_are_claimed_at_all():
    """A floor, so that deleting the mapping shows up here rather than as a
    quietly smaller number in `docs/scope.md`."""
    assert len(CLAIMED) >= 50, len(CLAIMED)


@pytest.mark.parametrize("requirement,rule_id,class_iri", CLAIMED,
                         ids=[c[0] for c in CLAIMED])
def test_an_unnamed_instance_of_the_class_is_reported(tmp_path, requirement,
                                                      rule_id, class_iri):
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", (
        '  <rdf:Description rdf:nodeID="anonymous">\n'
        '    <rdf:type rdf:resource="%s"/>\n'
        "  </rdf:Description>\n</rdf:RDF>") % class_iri)
    package = build_package(tmp_path, "a_%d.iirds" % abs(hash(requirement)),
                            metadata=metadata)
    fired = {f.rule.id for f in runner.check(package).findings}
    assert rule_id in fired, (requirement, rule_id, sorted(fired))


def test_a_named_instance_of_every_claimed_class_is_not_reported(tmp_path):
    """The control the parametrised cases do not give: a rule that reported
    every instance would pass all fifty of them."""
    for requirement, rule_id, class_iri in CLAIMED:
        metadata = MINIMAL_RDF.replace("</rdf:RDF>", (
            '  <rdf:Description rdf:about="urn:test:named">\n'
            '    <rdf:type rdf:resource="%s"/>\n'
            "  </rdf:Description>\n</rdf:RDF>") % class_iri)
        package = build_package(tmp_path, "n_%d.iirds" % abs(hash(requirement)),
                                metadata=metadata)
        fired = {f.rule.id for f in runner.check(package).findings}
        assert rule_id not in fired, (requirement, rule_id, sorted(fired))


def test_the_mapping_tool_and_the_generated_table_agree():
    """`tools/appendix_a_map.py` proposes the mapping and the generated table
    carries it. If the tool can still propose something, a row a rule checks is
    a row nobody claims — which is the state this file was written to end."""
    from appendix_a_map import propose

    proposals, _refusals = propose()
    assert proposals == [], (
        "these appendix A rows are checked by a rule and claimed by nobody: %s"
        % proposals[:6])
