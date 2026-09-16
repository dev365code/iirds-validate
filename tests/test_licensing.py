"""Licence compliance, as tests rather than as good intentions.

The ontologies are third-party material under CC BY-ND 4.0. Redistributing them
is allowed, and Section 3(a)(1) says precisely what has to travel with them. A
notice that quietly loses one of those items during a refactor is the kind of
mistake nobody notices until it matters, so each one is asserted here.
"""
from __future__ import annotations

import hashlib
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTICE = (ROOT / "NOTICE").read_text("utf-8")
ONTOLOGIES = ROOT / "src/iirds_validate/data/ontologies"

#: CC BY-ND 4.0 Section 3(a)(1): what must be retained when Sharing.
REQUIRED_IN_NOTICE = {
    "(i) creator": ["tekom Deutschland e.V."],
    "(ii) copyright notice": ["© 2023 Gesellschaft für Technische Kommunikation"],
    "(iii) licence notice": ["Creative Commons Attribution-NoDerivatives 4.0"],
    "(iii) licence URI": ["https://creativecommons.org/licenses/by-nd/4.0/"],
    "(iv) warranty disclaimer": ["DISCLAIMER OF WARRANTIES"],
    "(v) licensed material URI": ["https://www.iirds.org/materials/version-13"],
    "modification status": ["NOT MODIFIED"],
    "no endorsement": ["not sponsored or endorsed"],
}


@pytest.mark.parametrize("requirement", sorted(REQUIRED_IN_NOTICE))
def test_notice_carries_every_attribution_element(requirement):
    for needle in REQUIRED_IN_NOTICE[requirement]:
        assert needle in NOTICE, "NOTICE no longer states %s (%r)" % (requirement, needle)


def test_notice_scopes_apache_away_from_the_third_party_material():
    """Section 2(a)(5) forbids imposing different terms on the licensed
    material. A bare "this project is Apache-2.0" would read as doing exactly
    that to files that are not ours to relicense."""
    assert "does NOT extend to the third-party material" in NOTICE


def test_the_ontologies_are_byte_for_byte_as_published():
    """The whole basis for bundling them is that they are unmodified. If that
    stops being true, the licence stops permitting redistribution.

    Both directions, because one of them is the only one that matters here.
    Walking the manifest and hashing what it names cannot see a file the
    manifest stopped naming -- and deleting a line is easier than forging a
    digest. Measured: drop the `iirds-core.rdf` line, add a class to tekom's
    file, and `--verify` printed four "ok" lines and exited 0 while the forged
    class was live in `subclasses_of(iirds:InformationUnit)`.

    `tools/vendor_corpus.py::check` had this right for the vendored corpus
    already; the ontologies got one half of it.
    """
    sums = (ONTOLOGIES / "sha256sums.txt").read_text("utf-8")
    assert sums.strip(), "no checksums recorded"

    recorded = {}
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        recorded[name.strip()] = digest

    shipped = {path.name for path in (ONTOLOGIES / "1.3").iterdir()
               if path.suffix == ".rdf"}
    assert shipped, "no ontology files at all"
    assert set(recorded) == shipped, (
        "the manifest and the directory disagree: unrecorded %s, missing %s"
        % (sorted(shipped - set(recorded)), sorted(set(recorded) - shipped)))

    for name, digest in sorted(recorded.items()):
        blob = (ONTOLOGIES / "1.3" / name).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest, name


def test_each_ontology_keeps_its_own_copyright_header():
    """Retaining the notices that came with the material is not optional, and
    the notices came inside the files."""
    for path in sorted((ONTOLOGIES / "1.3").glob("*.rdf")):
        head = path.read_text("utf-8", errors="replace")[:2000]
        assert "tekom Deutschland e.V." in head, path.name
        assert "Attribution-NoDerivatives" in head, path.name


def test_no_converted_copy_of_an_ontology_is_committed():
    """CC BY-ND permits producing Adapted Material but not Sharing it. A
    checked-in Turtle or JSON-LD rendering of the ontology would be Sharing.

    shapes/ is exempt from the filename screen — those are this project's own
    SHACL artefacts, which reference iiRDS term IRIs but must copy no ontology
    content — and the exemption is not taken on trust: the test below reads
    every shape file and rejects the two ways ontology content could leak.
    """
    strays = [path for pattern in ("iirds-*.ttl", "iirds-*.jsonld", "iirds-*.nt")
              for path in ROOT.rglob(pattern)
              if "shapes" not in path.parts]
    assert not strays, [str(p.relative_to(ROOT)) for p in strays]


def test_the_shapes_copy_no_ontology_content():
    """The exemption above, earned rather than assumed.

    Two leak vectors. Structural: ontology axioms (subClassOf/domain/range
    about iiRDS-namespace subjects) reproduced as triples — the generator
    bakes closures into target *lists*, never re-states the hierarchy.
    Textual: the ontology's own label/description prose copied into shape
    metadata — every human-readable string in the shapes is this project's
    (titles, remedies), so tekom's sentences must not appear.
    """
    from rdflib import RDFS, Graph, URIRef

    shape_dir = ROOT / "shapes" / "iirds-1.3"
    assert shape_dir.exists(), (
        "shapes/ is part of the tree now; a silent pass here would let the "
        "boundary rot unwatched")
    graph = Graph()
    ttl_text = ""
    for path in sorted(shape_dir.glob("*.ttl")):
        graph.parse(path, format="turtle")
        ttl_text += path.read_text("utf-8")

    iirds = "http://iirds.tekom.de/"
    for predicate in (RDFS.subClassOf, RDFS.domain, RDFS.range, RDFS.subPropertyOf):
        offenders = [s for s, o in graph.subject_objects(predicate)
                     if str(s).startswith(iirds) or str(o).startswith(iirds)]
        assert offenders == [], (predicate, offenders[:3])

    described = {str(s) for s in graph.subjects(URIRef(iirds + "iirds#description"), None)}
    assert described == set(), "ontology prose predicate found in shapes"

    # The textual vector, actually implemented. The review
    # found 35 occurrences of the ontology's description prose riding in as
    # sh:message via the catalogue's `en` field -- while this test's own
    # docstring promised the check. Every description/comment sentence in the
    # bundled ontologies must be absent from the shipped Turtle, verbatim or
    # whitespace-collapsed.
    from urllib.parse import unquote

    from iirds_validate.ontology import Ontology

    # Three readings of the same bytes: raw, percent-decoded, and with
    # Turtle string escapes undone. The raw reading alone certifies a
    # boundary it does not check: the evicted prose was still shipping,
    # percent-encoded inside dcterms:source text fragments.
    readings = (
        " ".join(ttl_text.split()),
        " ".join(unquote(ttl_text).split()),
        " ".join(ttl_text.replace('\\"', '"').replace("\\n", " ")
                 .replace("\\\\", "\\").split()),
    )
    leaked = []
    ontology = Ontology("1.3")
    for _s, pred, value in ontology.graph:
        text = " ".join(str(value).split())
        if len(text) < 25:
            continue          # short labels ("Topic") legitimately recur
        if (str(pred).endswith("#description") or str(pred).endswith("comment")) \
                and any(text in reading for reading in readings):
            leaked.append(text[:60])
    assert leaked == [], sorted(set(leaked))[:5]


def test_the_readme_does_not_claim_endorsement():
    readme = (ROOT / "README.md").read_text("utf-8")
    assert "Not affiliated with" in readme
    for forbidden in (r"\bofficial iiRDS validator\b", r"\bcertified\b(?! by)"):
        assert not re.search(forbidden, readme, re.I), forbidden


def test_strategy_paths_can_never_be_tracked():
    """Planning notes and post drafts live outside the repository entirely;
    these two directory names are the belt over that braces, and this test
    is the alarm on the belt. If either name ever shows up tracked, someone
    has published strategy by accident — red is the correct colour."""
    import subprocess

    ignore = (ROOT / ".gitignore").read_text("utf-8")
    for line in ("docs/consortium/", "docs/private/"):
        assert line in ignore, line

    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "docs/consortium", "docs/private"],
        capture_output=True, text=True)
    if result.returncode != 0:
        import pytest
        pytest.skip("not a git checkout")
    assert result.stdout.strip() == "", result.stdout


# ---------------------------------------------------------------------------
# The stewardship pledge, word for word
#
# The `iirds` name on PyPI was held under a pledge from the day the library
# first shipped, and the PyPI page renders this README. The two paragraphs are
# the terms the name is held on; they are not paraphrased, and a test holds
# the text so that an edit to the surrounding page cannot quietly loosen it.
# ---------------------------------------------------------------------------

PLEDGE = (
    "The `iirds` name on PyPI belongs to the standard's community more than to any\n"
    "one project. **Should the iiRDS Consortium want this name for an official\n"
    "SDK, it will be transferred on request** — until then it does real work\n"
    "rather than squatting. `iirds-sdk` is an alias of this package and travels\n"
    "under the same pledge.",
    "This is an unofficial project, not affiliated with or endorsed by the iiRDS\n"
    "Consortium or tekom Deutschland e.V. \"iiRDS\" is used descriptively, to name\n"
    "the standard these functions read and write.",
)


@pytest.mark.parametrize("paragraph", PLEDGE, ids=["transfer-on-request", "unofficial"])
def test_the_readme_carries_the_stewardship_pledge_word_for_word(paragraph):
    assert paragraph in (ROOT / "README.md").read_text("utf-8")


#: Every file the distribution carries that is not code, and what licences it.
#: A list rather than a rule, because the answer for each one is a judgement
#: somebody made: `version-terms.json` shipped for five releases with its
#: argument for why it is not restricted written inside the file itself, where
#: no reader of NOTICE would meet it. A new data file has to be added here,
#: which is the moment to ask the question about it.
BUNDLED_DATA = {
    "src/iirds_validate/data/ontologies/1.3/iirds-core.rdf": "NOTICE item 1",
    "src/iirds_validate/data/ontologies/1.3/iirds-handover.rdf": "NOTICE item 1",
    "src/iirds_validate/data/ontologies/1.3/iirds-machinery.rdf": "NOTICE item 1",
    "src/iirds_validate/data/ontologies/1.3/iirds-skos.rdf": "NOTICE item 1",
    "src/iirds_validate/data/ontologies/1.3/iirds-software.rdf": "NOTICE item 1",
    "src/iirds_validate/data/ontologies/README.md": "ours",
    "src/iirds_validate/data/ontologies/sha256sums.txt": "ours",
    "src/iirds_validate/data/rule-catalog.json": "NOTICE item 2",
    "src/iirds_validate/data/version-terms.json": "NOTICE item 3",
    "src/iirds_validate/data/web/app.js": "ours",
    "src/iirds_validate/data/web/i18n.json": "ours",
    "src/iirds_validate/data/web/page.html": "ours",
    "src/iirds_validate/data/web/style.css": "ours",
    "src/iirds_validate/py.typed": "ours",
}


def _shipped_data():
    """Every non-code file under `src/`, as the wheel carries them."""
    import subprocess
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "src"],
                            capture_output=True, text=True)
    if listed.returncode != 0:                       # pragma: no cover - no git
        pytest.skip("no git checkout to ask")
    return {p for p in listed.stdout.split() if not p.endswith(".py")}


def test_every_bundled_data_file_has_been_licensed_on_purpose():
    """A file that ships and is not code is either ours or somebody else's.

    The distribution is what a reader receives, so this asks `git ls-files`
    rather than a glob: a file that is committed under `src/` and is not code
    reaches them, whatever any packaging list says.
    """
    shipped = _shipped_data()
    assert shipped == set(BUNDLED_DATA), (
        "the distribution's data files and this list disagree -- new: %s, gone: %s"
        % (sorted(shipped - set(BUNDLED_DATA)), sorted(set(BUNDLED_DATA) - shipped)))


@pytest.mark.parametrize("path", sorted(p for p, who in BUNDLED_DATA.items() if who != "ours"))
def test_third_party_data_is_named_where_a_reader_looks(path):
    """NOTICE is where somebody checks what they may redistribute, and a file
    whose provenance is argued only inside itself is not findable from there.

    Findable, not spelled one way: NOTICE heads the ontologies with the
    directory that holds them, and THIRD_PARTY.md's table names several of
    them by file name in one cell. Either reaches a reader; what must not
    happen is that neither does.
    """
    import posixpath
    import re

    def findable(text):
        """Does this document name the file, or a directory that contains it?

        Not "does the path appear anywhere": the first version of this asked
        whether any ancestor string occurred in the text, and
        `src/iirds_validate/data/` occurs inside the heading for the
        ontologies -- so removing this file's own item left the gate green.
        A directory counts only when it is a real ancestor of the file.
        """
        if path in text or posixpath.basename(path) in text:
            return True
        here = posixpath.dirname(path) + "/"
        for named in re.findall(r"src/[\w./-]+", text):
            named = named if named.endswith("/") else named + "/"
            if here.startswith(named):
                return True
        return False

    assert findable(NOTICE), "NOTICE does not name %s or the directory it is in" % path
    assert findable((ROOT / "THIRD_PARTY.md").read_text("utf-8")), (
        "THIRD_PARTY.md's table does not name %s" % path)
