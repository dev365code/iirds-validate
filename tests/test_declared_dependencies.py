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
the check would filter nothing while appearing to work.

Neither does "is it under the standard library's directory", and that was
wrong here twice, in both directions. `site-packages` can sit *inside* that
directory -- it does on the interpreter this was written on, and on most
distribution-packaged Pythons -- so `pip`, `setuptools` and `pkg_resources`
all answered "standard library" and walked through the gate built to catch
exactly them. And the standard library reaches outside it: on Windows
`unicodedata` is an extension module in the `DLLs` directory, beside
`Lib` rather than under it, and the repair for the first mistake reported
it as an undeclared
dependency of this project.

So the install directories are asked for by name, from `sysconfig` and from
`site`, and asked first; and what is left is the standard library if it comes
from anywhere under the interpreter itself.

An import inside `try:` with a handler that catches its absence is not in
scope, and neither is one inside that handler: both have already said what
happens when the module is missing, which is the thing this test exists to
require. `tools/build_zipapp.py` falls back from `packaging` to pip's
vendored copy that way, and demanding that `pip` be declared would put a
dependency in `pyproject.toml` that this project does not have.
"""
from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import os
import re
import site
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCHED = ("tests", "tools")
STDLIB = os.path.realpath(sysconfig.get_paths()["stdlib"])
#: Where the interpreter itself lives. The standard library is not one
#: directory: on Windows `unicodedata` is an extension module in the `DLLs`
#: directory, beside `Lib` rather than under it, and asking only about `stdlib` put it
#: outside the standard library and into the report. Everything the
#: interpreter ships sits under this, `DLLs`, `lib-dynload` and `Lib` alike --
#: and so does `site-packages`, which is why the install directories are
#: asked about first.
BASE_PREFIX = os.path.realpath(sys.base_prefix)
INSIDE = os.path.realpath(ROOT)

#: A path component that means "something was installed here". Belt to the
#: braces below: a layout neither `sysconfig` nor `site` reports still says
#: so in the path, and `dist-packages` is what Debian and its children call
#: the same thing.
INSTALL_MARKERS = ("site-packages", "dist-packages")


def _install_directories():
    """Where distributions land on this interpreter.

    `purelib` and `platlib` are two of them and on some interpreters they are
    two names for one directory that holds almost nothing: the interpreter's
    own `site-packages`, and the user's, are elsewhere. `site` lists both,
    and is guarded because a virtualenv may not carry `getsitepackages`.
    """
    out = set()
    paths = sysconfig.get_paths()
    for key in ("purelib", "platlib"):
        if paths.get(key):
            out.add(os.path.realpath(paths[key]))
    for getter in ("getsitepackages", "getusersitepackages"):
        try:
            got = getattr(site, getter)()
        except Exception:                      # not every environment has these
            continue
        for one in ([got] if isinstance(got, str) else got or ()):
            out.add(os.path.realpath(one))
    return out


INSTALLED = _install_directories()


def _is_installed(path):
    if any(path.startswith(directory + os.sep) for directory in INSTALLED):
        return True
    return any(marker in path.split(os.sep) for marker in INSTALL_MARKERS)


def _is_standard_library(path):
    if path == "built-in":
        return True
    if _is_installed(path):
        return False
    return (path.startswith(BASE_PREFIX + os.sep)
            or path.startswith(STDLIB + os.sep))


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


#: Exception names whose handler catches a module that is not there.
#: `ModuleNotFoundError` is the 3.6 subclass of `ImportError` and a handler
#: naming only it still catches the absence; `Exception` and `BaseException`
#: catch it as well. A list of names rather than a subclass test because
#: this reads source, and the source has not been imported.
CATCHES_ABSENCE = ("ImportError", "ModuleNotFoundError", "Exception", "BaseException")


def _handler_catches_absence(handler):
    if handler.type is None:                   # a bare `except:`
        return True
    named = [handler.type]
    if isinstance(handler.type, ast.Tuple):
        named = list(handler.type.elts)
    for node in named:
        name = getattr(node, "id", None) or getattr(node, "attr", None)
        if name in CATCHES_ABSENCE:
            return True
    return False


def _optional_imports(tree):
    """Import nodes inside a `try:` that catches their absence, and inside
    that handler.

    The handler counts because the fallback lives there. An import that runs
    only when another one failed is reached only on the machines where the
    first is missing, and requiring it to be declared would write down a
    dependency the project does not have.
    """
    spared = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        handlers = [h for h in node.handlers if _handler_catches_absence(h)]
        if not handlers:
            continue
        bodies = list(node.body)
        for handler in handlers:
            bodies.extend(handler.body)
        for statement in bodies:
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
        if _is_standard_library(loaded):
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
    assert _is_standard_library(_where_it_loads_from("json"))
    assert _is_standard_library(_where_it_loads_from("sys"))


def test_a_package_installed_inside_the_standard_library_is_not_the_standard_library():
    """The control the first version did not have, and the reason it passed
    while filtering nothing.

    It asked only whether a standard-library module is recognised as one, and
    `json` is, wherever `site-packages` happens to sit. Here it sits inside
    the standard library's own directory, so every distribution installed
    there was recognised as standard library too -- `pip`, `setuptools` and
    `pkg_resources` among them, which is the shape this gate exists for.

    Written the first time with `pytest` as its witness, which is installed
    and is not the standard library, and which passed on the unrepaired code:
    `pytest` lives in the *user's* site directory, and that is not under the
    standard library, so the case was wrong on a different axis than the one
    under test. The path here is built rather than looked up, so the axis is
    the only thing it is wrong on, and so the case does not depend on where
    this interpreter happens to keep things. `dist-packages` is the same
    layout under the name Debian and its children give it, and it is pinned
    here rather than left to whichever machine happens to run this.
    """
    for inside in (os.path.join(STDLIB, "site-packages", "somepkg", "__init__.py"),
                   os.path.join(STDLIB, "dist-packages", "somepkg", "__init__.py")):
        assert _is_installed(inside), inside
        assert not _is_standard_library(inside), inside
    assert _is_standard_library(os.path.join(STDLIB, "json", "__init__.py"))
    assert _is_standard_library("built-in")


def test_the_standard_library_reaches_outside_its_own_directory():
    """The other direction, and the one the repair above introduced.

    `sysconfig` names one directory and the standard library occupies more
    than one: on Windows the extension modules are in the `DLLs` directory, a
    sibling of `Lib`, so `unicodedata` -- imported by a test here --
    loaded from outside everything this knew about and was reported as a
    dependency nobody had declared. Every machine running this suite on
    Windows said so; none of the others could.

    Built rather than looked up, for the same reason as above: on a machine
    with no `DLLs` directory the case still asks the question it is here for.
    """
    shipped = os.path.join(BASE_PREFIX, "DLLs", "unicodedata.pyd")
    assert not _is_installed(shipped), shipped
    assert _is_standard_library(shipped), shipped


def test_the_search_finds_more_than_one_place_to_install_into():
    """A `site` that answers with nothing would put every installed package
    back under the standard library by the same route as before."""
    assert INSTALLED, "no install directory found; the classification is one-sided"


def test_a_fallback_import_inside_the_handler_is_not_counted():
    source = ("try:\n    import nowhere\n"
              "except ImportError:\n    import elsewhere\n")
    assert len(_optional_imports(ast.parse(source))) == 2
    source = ("try:\n    import nowhere\n"
              "except (ValueError, ModuleNotFoundError):\n    import elsewhere\n")
    assert len(_optional_imports(ast.parse(source))) == 2
    source = ("try:\n    import nowhere\n"
              "except ValueError:\n    import elsewhere\n")
    assert not _optional_imports(ast.parse(source))
