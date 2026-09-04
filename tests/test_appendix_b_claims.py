"""Every appendix B claim, held by content that breaks the sentence.

`tests/test_content_rules.py` gives each B rule a case that fires and a case
that does not, which says the rule works. A `covers=` claim says something
stronger and different: that no package breaking *the sentence* gets past the
rules claiming it. A sentence usually breaks in more ways than one, and the
one way somebody thought of first is not evidence about the others.

So each sentence here is written out, and under it every shape that violates
it. The clean control is the same markup with the one breach removed -- a
sentence "covered" by a rule that fires on everything is covered by nothing.

Two of these needed the code to move before the claim could be made. B.5.7
prohibits scripting and had three routes into a document, of which two were
checked: `<script>` by the element list and `onclick` by the attribute names.
The third is a URL whose scheme is a script, where the element and the
attribute are both ordinary and only the value says what happens; B11 reports
it now. And B.3's extension sentence is met case-insensitively, which is a
spelling and is recorded as one in docs/divergences.md.
"""
from __future__ import annotations

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import runner
from test_content_rules import CLEAN, SYMBOL

#: obligation id -> the rules whose `covers=` names it. Written out rather
#: than derived, so a rule quietly dropping a claim fails here instead of
#: shrinking the set it is checked against.
CLAIMANTS = {
    "b-3-conformance-criteria#2": {"B1"},
    "b-3-conformance-criteria#4": {"B2", "B3"},
    "b-3-conformance-criteria#5": {"B6"},
    "b-5-2-document-metadata#1": {"B5"},
    "b-5-7-scripting#1": {"B2", "B4", "B11"},
    "b-5-10-forms#1": {"B2"},
    "b-5-11-svg-mathml-and-iframes#1": {"B2"},
    "b-6-additional-semantic-tagging-of-content#5": {"B7"},
    "b-6-additional-semantic-tagging-of-content#6": {"B8"},
}

#: obligation id -> [(what the shape is, the content, the file name)].
#: `None` for the file name means the ordinary one.
BREACHES = {
    "b-3-conformance-criteria#2": [
        ("an element that is never closed", "<html><p>unclosed", None),
        ("an attribute given twice", "<p id=\"a\" id=\"b\">x</p>", None),
        ("an entity nothing declares", "<p>&nosuch;</p>", None),
    ],
    "b-3-conformance-criteria#4": [
        ("an element the appendix does not list", "<marquee>x</marquee>", None),
        ("an element from another vocabulary", "<blink>x</blink>", None),
    ],
    "b-3-conformance-criteria#5": [
        ("a .html file declared as iiRDS XHTML5", None, "content/topic1.html"),
        ("a .htm file declared as iiRDS XHTML5", None, "content/topic1.htm"),
        ("no extension at all", None, "content/topic1"),
    ],
    "b-5-2-document-metadata#1": [
        ("a link with another relation",
         None, None, ('rel="stylesheet"', 'rel="next"')),
        ("a link with no relation at all",
         None, None, ('<link rel="stylesheet" type="text/css" href="../a.css"/>',
                      '<link type="text/css" href="../a.css"/>')),
    ],
    "b-5-7-scripting#1": [
        ("a script element", "<script>alert(1)</script>", None),
        ("an event handler attribute", '<p onclick="go()">x</p>', None),
        ("another event handler attribute", '<p onmouseover="go()">x</p>', None),
        ("a javascript: URL", '<p><a href="javascript:alert(1)">x</a></p>', None),
        ("a javascript: URL with the scheme split by a tab",
         '<p><a href="java&#9;script:alert(1)">x</a></p>', None),
        ("a vbscript: URL", '<p><a href="vbscript:MsgBox 1">x</a></p>', None),
        ("a script URL on an image", '<img src="javascript:alert(1)" alt="x"/>', None),
    ],
    "b-5-10-forms#1": [
        ("a form", "<form><input/></form>", None),
        ("a form control on its own", '<input type="text"/>', None),
        ("a button", "<button>go</button>", None),
        ("a select", "<select><option>a</option></select>", None),
        ("a textarea", "<textarea>t</textarea>", None),
    ],
    "b-5-11-svg-mathml-and-iframes#1": [
        ("svg", '<svg xmlns="http://www.w3.org/2000/svg"/>', None),
        ("math", '<math xmlns="http://www.w3.org/1998/Math/MathML"/>', None),
        ("iframe", '<iframe src="a"/>', None),
    ],
    "b-6-additional-semantic-tagging-of-content#5": [
        ("a data-role the table does not define", '<p data-role="banana">x</p>', None),
        ("a data-role the table defines, on the wrong element",
         '<p data-role="symbol-panel">x</p>', None),
    ],
    "b-6-additional-semantic-tagging-of-content#6": [
        ("two safety alert symbols in one hazard statement",
         None, None, (SYMBOL, SYMBOL + SYMBOL)),
        ("a safety alert symbol outside the signal word panel",
         None, None, (SYMBOL, ""),
         ('<div data-role="message-panel">', SYMBOL + '<div data-role="message-panel">')),
    ],
}

CASES = [(obligation, breach[0], breach)
         for obligation, breaches in sorted(BREACHES.items())
         for breach in breaches]


def _content(breach):
    """The clean document with the one breach applied."""
    fragment, _name = breach[1], breach[2]
    xhtml = CLEAN
    for old, new in breach[3:]:
        assert old in xhtml, "the fixture edit matched nothing: %r" % (old,)
        xhtml = xhtml.replace(old, new)
    if fragment is not None:
        marker = "<ul><li>Risk of electrical shock</li></ul>"
        assert marker in xhtml, "the fixture edit matched nothing"
        xhtml = xhtml.replace(marker, fragment)
    return xhtml


def _fired(make_package, breach, name):
    source = breach[2] or "content/topic1.xhtml"
    metadata = MINIMAL_RDF.replace(
        "<iirds:source>content/topic1.xhtml</iirds:source>",
        "<iirds:source>%s</iirds:source>" % source)
    package = make_package(name=name, metadata=metadata, content=(),
                           extra=((source, _content(breach)),))
    return {f.rule.id for f in runner.check(package).findings}


@pytest.mark.parametrize("obligation,what,breach", CASES,
                         ids=["%s :: %s" % (o, w) for o, w, _ in CASES])
def test_every_way_of_breaking_an_appendix_b_sentence_is_reported(
        make_package, obligation, what, breach):
    fired = _fired(make_package, breach, "b_%d.iirds" % abs(hash((obligation, what))))
    claimants = CLAIMANTS[obligation]
    assert claimants & fired, (
        "%s -- %s: reported by nobody who claims the sentence; fired: %s"
        % (obligation, what, sorted(fired)))


def test_the_claimants_are_the_rules_that_claim_these_sentences(make_package):
    """The table above is a copy of `covers=`, and copies drift. If a rule
    gains or loses one of these obligations, the set it is checked against has
    to change with it or the case list is being run against the wrong rules."""
    from iirds_validate.registry import all_rules

    actual = {}
    for rule in all_rules():
        for obligation in rule.covers or ():
            if obligation in CLAIMANTS:
                actual.setdefault(obligation, set()).add(rule.id)
    assert actual == CLAIMANTS


def test_the_clean_control_breaks_none_of_them(make_package):
    """Every case above is CLEAN plus one breach, so CLEAN itself has to be
    silent or the cases are measuring the fixture."""
    package = make_package(name="b_clean.iirds", content=(),
                           extra=(("content/topic1.xhtml", CLEAN),))
    fired = {f.rule.id for f in runner.check(package).findings}
    assert not any(f.startswith("B") for f in fired), sorted(fired)


def test_each_sentence_is_broken_more_than_one_way_where_it_can_be():
    """A sentence with a single case is a sentence somebody looked at once.
    Two of these genuinely have one shape each -- an element list is broken by
    using an element that is not on it, and there is one way to do that -- so
    the floor is stated per sentence rather than as a rule."""
    counts = {obligation: len(breaches) for obligation, breaches in BREACHES.items()}
    assert counts == {
        "b-3-conformance-criteria#2": 3,
        "b-3-conformance-criteria#4": 2,
        "b-3-conformance-criteria#5": 3,
        "b-5-2-document-metadata#1": 2,
        "b-5-7-scripting#1": 7,
        "b-5-10-forms#1": 5,
        "b-5-11-svg-mathml-and-iframes#1": 3,
        "b-6-additional-semantic-tagging-of-content#5": 2,
        "b-6-additional-semantic-tagging-of-content#6": 2,
    }, counts
