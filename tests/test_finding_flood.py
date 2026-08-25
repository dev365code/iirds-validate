"""One rule can have as many findings as the document has elements.

A metadata file repeating one violation is a few bytes per repetition and a
finding per repetition, and nothing bounded the second. Measured on this
tool: 20,000 repetitions in a 51 KB archive produced 17 MB of JSON and 143 MB
resident, linear in the repetition count, from an input the size of a
photograph. Nobody reads the twenty-thousandth line and nothing downstream
needs it -- the count does.

So the listing is bounded and the counting is not. Everything a verdict rests
on -- the summary, the exit code, `report.ok` -- is computed over every
finding, including the ones not kept. The sibling project reached the same
shape after the same measurement; this is that shape, keyed on the rule alone
because a report here covers one container.
"""
from __future__ import annotations

import json
import os

from conftest import MINIMAL_RDF, build_package
from iirds_validate import runner
from iirds_validate.model import MAX_LISTED_PER_RULE, Severity

#: Enough to be well past the cap and small enough to build in a moment.
REPETITIONS = MAX_LISTED_PER_RULE * 5


def _flood(tmp_path):
    """A package whose metadata breaks one rule once per information unit."""
    body = "".join('  <iirds:InformationUnit rdf:about="urn:test:u%d"/>\n' % n
                   for n in range(REPETITIONS))
    return build_package(tmp_path, "flood.iirds",
                         metadata=MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>"))


def test_the_listing_is_bounded(tmp_path):
    report = runner.check(_flood(tmp_path))
    listed = [f for f in report.findings if f.rule.id == "M1"]
    assert len(listed) == MAX_LISTED_PER_RULE, len(listed)


def test_the_counting_is_not(tmp_path):
    """The bound is on what is printed, never on what is judged."""
    report = runner.check(_flood(tmp_path))
    assert report.count(Severity.ERROR) >= REPETITIONS
    assert not report.ok
    assert report.suppressed["M1"] == REPETITIONS - MAX_LISTED_PER_RULE


def test_the_json_says_what_it_left_out(tmp_path):
    """A stored report has to be readable as a whole thing years later, so it
    carries the difference between what it lists and what it counted rather
    than leaving a reader to infer it from a number that does not add up."""
    document = json.loads(json.dumps(runner.check(_flood(tmp_path)).as_dict()))
    assert document["summary"]["errors"] >= REPETITIONS
    assert document["summary"]["findingsNotListed"] == REPETITIONS - MAX_LISTED_PER_RULE
    assert document["suppressed"]["M1"] == REPETITIONS - MAX_LISTED_PER_RULE
    assert len(json.dumps(document)) < 400_000


def test_the_headline_counts_what_happened_not_what_was_kept(tmp_path, capsys):
    """The one number in that line a reader acts on.

    The group headline used the length of the list it was printing, which is
    the bounded thing. It would have said a hundred where there were a
    thousand, in the same line that tells somebody how much work they have.
    """
    from iirds_validate import report as report_module

    report_module.render_text(runner.check(_flood(tmp_path)))
    out = capsys.readouterr().out
    assert "×%d" % REPETITIONS in out, out[:400]
    assert "listed to %d per rule" % MAX_LISTED_PER_RULE in out
    assert "%d error(s)" % REPETITIONS in out


def _flood_of_blank_nodes(tmp_path):
    """The same flood, over nodes rdflib has to name for itself.

    A named node arrives in document order however the store is indexed, so a
    fixture of them cannot show which hundred a bound kept -- it would have
    kept the same hundred either way. The instability is carried by the
    labels rdflib mints per parse, so the fixture has to contain some.
    """
    body = "".join(
        '  <iirds:Topic rdf:about="urn:test:t%03d"><iirds:has-rendition>'
        '<iirds:Rendition><iirds:source>content/%d.pdf</iirds:source></iirds:Rendition>'
        '</iirds:has-rendition></iirds:Topic>\n' % (n, n)
        for n in range(REPETITIONS))
    return build_package(tmp_path, "blankflood.iirds",
                         metadata=MINIMAL_RDF.replace("</rdf:RDF>", body + "</rdf:RDF>"))


def test_the_hundred_that_are_listed_are_the_same_hundred_every_run(tmp_path):
    """A bound has to choose, and the choice cannot be graph order.

    rdflib mints a blank-node label per parse and iterates its store in an
    order those labels perturb, so the first hundred to arrive are a hundred
    chosen by this process. The same package listed a different hundred every
    run -- and at one seed, so no seed matrix would have said so.

    Two processes, because running it twice inside one interpreter shares
    both the hash seed and the blank-node counter, which is not the same
    experiment.
    """
    import subprocess
    import sys
    import textwrap

    package = _flood_of_blank_nodes(tmp_path)
    script = textwrap.dedent("""
        import json, sys
        from iirds_validate import runner
        report = runner.check(sys.argv[1])
        print(json.dumps(sorted(f.violation.subject or "" for f in report.findings)))
    """)
    runs = [subprocess.run([sys.executable, "-c", script, str(package)],
                           capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": "0"}).stdout
            for _ in range(3)]
    assert len(set(runs)) == 1, "three runs at one seed listed three different sets"
