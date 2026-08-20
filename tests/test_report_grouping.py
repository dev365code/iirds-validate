"""Forty findings of one rule must not read as forty paragraphs.

The flood case: a package whose metadata names forty missing files produced
246 lines — the same three-line remedy repeated forty times, subjects sorted
so that rendition10 came before rendition2, and nothing anywhere saying
"forty files are missing". The report is the product; a report nobody can
read is a defect in it.
"""
from __future__ import annotations

import io

from conftest import MINIMAL_RDF, build_package
from iirds_validate import report, runner

TOPIC = '''  <iirds:Topic rdf:about="urn:t:%d"><iirds:title>T%d</iirds:title>
    <iirds:has-rendition><iirds:Rendition>
      <iirds:format>application/pdf</iirds:format>
      <iirds:source>content/missing-%d.pdf</iirds:source>
    </iirds:Rendition></iirds:has-rendition></iirds:Topic>
'''


def _flood(tmp_path, count):
    body = "".join(TOPIC % (i, i, i) for i in range(count))
    metadata = MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>")
    return build_package(tmp_path, "flood%d.iirds" % count, metadata=metadata)


def _render(package):
    out = io.StringIO()
    report.render_text(runner.run(package, runner.ALL_KINDS), stream=out)
    return out.getvalue()


def test_a_flood_collapses_to_one_group(tmp_path):
    text = _render(_flood(tmp_path, 40))
    lines = text.splitlines()

    assert len(lines) < 30, "forty findings must not be forty paragraphs"
    assert "×40" in text, "the count is the headline fact"
    assert text.count("Add the file to the container") == 1, "the remedy once, not forty times"
    assert "and 35 more" in text
    assert "--format json" in text, "and it says where the rest went"


def test_the_shown_subjects_are_in_natural_order(tmp_path):
    """rendition10 must not come before rendition2."""
    text = _render(_flood(tmp_path, 12))
    shown = [line for line in text.splitlines() if "missing-" in line]
    numbers = [int(line.split("missing-")[1].split(".")[0]) for line in shown]
    assert numbers == sorted(numbers)
    assert numbers[:3] == [0, 1, 2]


def test_two_findings_of_one_rule_still_print_in_full(tmp_path):
    """Grouping starts at three. Two deserve their whole story each."""
    text = _render(_flood(tmp_path, 2))
    assert "×" not in text
    assert text.count("Add the file to the container") == 2


def test_the_json_report_still_carries_every_finding(tmp_path):
    """Grouping is presentation. The data loses nothing."""
    result = runner.run(_flood(tmp_path, 40), runner.ALL_KINDS)
    assert len([f for f in result.findings if f.rule.id == "L2"]) == 40
    assert len(result.as_dict()["findings"]) >= 40
