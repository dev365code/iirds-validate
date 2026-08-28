"""The offline story, held by a gate rather than told in prose.

This SDK exists for air-gapped plants: one third-party dependency,
installable from a USB stick. That claim rots the moment somebody adds a
convenient import, so the import set is pinned -- exactly, in both
directions. Growing it is allowed; it happens here, consciously, in the
same commit as the import.
"""
import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "iirds"

#: Everything the SDK imports: itself, rdflib, and precisely the
#: standard-library modules it uses today.
#:
#: `xml` is here for `xml.parsers.expat`, and it is a decision rather than a
#: convenience: the guard that refuses entity declarations asks the parser
#: instead of matching bytes, because a pattern has to decide the encoding for
#: itself and then agree with the parser about it, and has to know where the
#: grammar permits a declaration. It did neither. Standard library, so the
#: offline story is unchanged -- one third-party dependency, still rdflib.
#: `unicodedata` is here so that a name goes into an archive in one spelling.
#: A filesystem hands back whichever form a name was created in, and the
#: metadata that refers to the file is composed; storing the other form makes
#: two byte strings for one file. Standard library, like `xml` above.
#: `urllib` is here for `urllib.parse.unquote`. §6.3 calls an iirds:source
#: a URL, so this library reads it as one and a name with a space in it
#: arrives percent-encoded; Appendix A calls the same value a path, and the
#: choice between them is recorded as a reading rather than assumed here.
#: Given the choice, hand-rolling the decoder is how one ends up
#: disagreeing with every other decoder. Standard library, like the two
#: above.
#: `hashlib` is here so that the write self-check stays affordable. It
#: compares the bytes written against the graph they came from, and asking
#: rdflib whether two graphs are isomorphic prices itself for the general
#: case -- on a manual-sized package, where every information unit nests a
#: blank-node rendition, that check grew to three quarters of a minute and
#: to almost all of what writing cost. Where the blank nodes form a forest
#: the same answer comes from naming each one by a digest of its subtree.
#: Standard library, like the three above.
ALLOWED = {"hashlib", "iirds", "rdflib", "__future__", "json", "os",
           "pathlib", "posixpath", "re", "time", "typing", "unicodedata",
           "urllib", "xml", "zipfile"}


def imports_in(path):
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.partition(".")[0]
        elif isinstance(node, ast.ImportFrom):
            # a relative import stays inside the package
            yield "iirds" if node.level else node.module.partition(".")[0]


def modules_under(root):
    """Every module in the package, subpackages included.

    A plain glob was used here while the package happened to be one flat
    directory, so it swept everything and the test looked complete. It was
    complete by accident: the first subpackage would have carried any import
    at all past the allowlist below, and no test would have said so. Pulled
    out as a function so the sweep itself can be tested against a tree that
    has a subpackage, which the real one does not."""
    return sorted(root.rglob("*.py"))


def test_the_sweep_reaches_into_a_subpackage(tmp_path):
    """The red this was written against: with a non-recursive glob the deep
    module is absent from the result and its import is never examined."""
    package = tmp_path / "pkg"
    (package / "sub").mkdir(parents=True)
    (package / "__init__.py").write_text("", "utf-8")
    (package / "sub" / "deep.py").write_text("import nothing_you_allow\n", "utf-8")

    found = modules_under(package)
    assert package / "sub" / "deep.py" in found, [str(p) for p in found]
    assert "nothing_you_allow" in set(imports_in(package / "sub" / "deep.py"))


def test_the_only_third_party_dependency_is_rdflib():
    used = set()
    for path in modules_under(SRC):
        used |= set(imports_in(path))
    assert used - ALLOWED == set(), \
        "a new import needs a conscious decision here: %s" % sorted(used - ALLOWED)
    assert ALLOWED - used == set(), \
        "allowlist rot -- these are no longer imported: %s" % sorted(ALLOWED - used)


def test_pyproject_says_the_same_thing():
    text = (SRC.parent.parent / "pyproject.toml").read_text("utf-8")
    assert 'dependencies = ["rdflib>=6"]' in text
