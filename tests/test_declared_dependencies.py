"""Every third-party import in the suite and the tools is a declared one.

A dependency that is installed on the machine and named in no file is a
dependency that works until it is somewhere else. It does not announce
itself: the import succeeds, the test passes, and the first report comes
from a fresh checkout on a machine that happens not to have it -- which is
CI, or a contributor, or the person the tool was written for.

The question is asked of the interpreter rather than of a list of names.
A list is a second place to forget, and this project has watched what a
second place to forget does. What is asked of each name is *where it loaded
from*: inside the standard library, inside this repository, or somewhere
else -- and somewhere else has to be a distribution that pyproject.toml
names.

`sys.stdlib_module_names` would answer the first part in one line and is
3.10; on 3.9, which this project supports and CI runs, it does not exist and
the check would filter nothing while appearing to work. The standard
library's own directory, from `sysconfig`, answers the same question
everywhere.

An import inside `try:` with an `except ImportError` is not in scope: that
import has already said what happens when it is absent, which is the thing
this test exists to require.
"""
from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import os
import re
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCHED = ("tests", "tools")
STDLIB = os.path.realpath(sysconfig.get_paths()["stdlib"])
INSIDE = os.path.realpath(ROOT)


def _declared():
    """Distribution names from pyproject: the runtime one and every extra.

    Read as text. `tomllib` is 3.11, and a parser installed to read the file
    that says what may be installed is the thing this test is about.
    """
    text = (ROOT / "pyproject.toml").read_text("utf-8")
    #: This distribution too. An editable install can resolve the package
    #: through a finder that lives in site-packages, and a project importing
    #: itself is not an undeclared dependency.
    names = set(re.findall(r'^name\s*=\s*"([A-Za-z0-9_.-]+)"', text, re.M))
    for block in re.findall(r"^dependencies\s*=\s*\[(.*?)\]", text, re.M | re.S):
        names |= set(re.findall(r'"([A-Za-z0-9_.-]+)', block))
    extras = re.search(r"^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)",
                       text, re.M | re.S)
    if extras:
        for line in extras.group(1).splitlines():
            if "=" in line:
                names |= set(re.findall(r'"([A-Za-z0-9_.-]+)', line.split("=", 1)[1]))
    return names


def _optional_imports(tree):
    """Import nodes under a `try:` that catches their absence."""
    spared = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        catches = any(handler.type is None
                      or "ImportError" in ast.dump(handler.type)
                      for handler in node.handlers)
        if not catches:
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    spared.add(id(inner))
    return spared


def _imported_names():
    """Every module name imported by the suite and the tools, with a witness."""
    found = {}
    for where in SEARCHED:
        for path in sorted((ROOT / where).rglob("*.py")):
            tree = ast.parse(path.read_text("utf-8"))
            spared = _optional_imports(tree)
            for node in ast.walk(tree):
                if id(node) in spared:
                    continue
                if isinstance(node, ast.Import):
                    names = [alias.name.partition(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [] if node.level else [(node.module or "").partition(".")[0]]
                else:
                    continue
                for name in names:
                    if name:
                        found.setdefault(name, str(path.relative_to(ROOT)))
    return found


def _where_it_loads_from(name):
    try:
        spec = importlib.util.find_spec(name)
    except Exception:
        return None
    if spec is None:
        return None
    origin = spec.origin
    if origin in (None, "built-in", "frozen"):
        #: A namespace package has no origin and a search path instead. If any
        #: of it is inside this repository the module is this repository's.
        for location in spec.submodule_search_locations or ():
            if os.path.realpath(str(location)).startswith(INSIDE + os.sep):
                return os.path.realpath(str(location))
        return "built-in"
    real = os.path.realpath(origin)
    if not real.startswith(INSIDE + os.sep):
        #: A package whose module file is elsewhere but whose contents are
        #: here -- what an editable install looks like from the outside.
        for location in spec.submodule_search_locations or ():
            if os.path.realpath(str(location)).startswith(INSIDE + os.sep):
                return os.path.realpath(str(location))
    return real


def _owning_distribution(path, declared):
    for name in sorted(declared):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        for owned in distribution.files or ():
            try:
                if os.path.realpath(str(distribution.locate_file(owned))) == path:
                    return name
            except Exception:              # a path a distribution cannot locate
                continue
    return None


def test_every_third_party_import_is_declared():
    """The failure this catches is silent in the direction that matters: the
    machine that has the package says nothing, and the machine that does not
    is the one nobody is watching."""
    declared = _declared()
    assert declared, "pyproject.toml declares nothing; the comparison has no right-hand side"
    undeclared = []
    for name, witness in sorted(_imported_names().items()):
        loaded = _where_it_loads_from(name)
        if loaded is None:
            continue          # not importable here: a different question
        if loaded == "built-in" or loaded.startswith(STDLIB + os.sep):
            continue
        if loaded.startswith(INSIDE + os.sep):
            continue
        if _owning_distribution(loaded, declared) is None:
            undeclared.append("%s (imported by %s, loaded from %s)" % (name, witness, loaded))
    assert not undeclared, (
        "imported and installed here, declared nowhere:\n  " + "\n  ".join(undeclared))


def test_the_search_is_looking_at_the_files_it_says_it_is():
    """A glob that matches nothing passes every assertion above it."""
    found = _imported_names()
    assert len(found) > 30, sorted(found)
    assert "rdflib" in found and "pytest" in found, sorted(found)


def test_an_optional_import_is_not_counted():
    """The exemption has to be the shape it claims, not the word `try`."""
    tree = ast.parse("try:\n    import nowhere\nexcept ImportError:\n    nowhere = None\n")
    assert len(_optional_imports(tree)) == 1
    tree = ast.parse("try:\n    import nowhere\nexcept ValueError:\n    nowhere = None\n")
    assert not _optional_imports(tree)


def test_the_standard_library_is_actually_being_recognised():
    """`sysconfig` answering with a directory nothing is under would make the
    check above pass by classifying the whole standard library as declared --
    no, as third-party, and then failing; or, with the test written the other
    way round, by classifying everything as fine. Named here so the mistake
    cannot be silent."""
    assert _where_it_loads_from("json").startswith(STDLIB + os.sep)
    assert _where_it_loads_from("sys") == "built-in"
