"""The command line, including the one thing a banner must never do."""
from __future__ import annotations

import json

import pytest

from iirds_validate.cli import EXIT_ERROR, EXIT_FINDINGS, EXIT_OK, main


def test_a_bare_invocation_greets_instead_of_erroring(capsys):
    """argparse would exit 2 with a usage error, which is a poor answer to
    someone who has just installed the thing."""
    assert main([]) == EXIT_OK
    out = capsys.readouterr().out
    assert "iirds check" in out
    assert "157" in out, "the banner should say how much of the catalogue is covered"


@pytest.mark.parametrize("command", ["check", "lint", "all"])
def test_the_banner_never_reaches_a_pipe(make_package, capsys, command):
    """A build log is one thing; `--format json` is a document another program
    parses, and a banner in front of it is not noise but corruption."""
    package = str(make_package())

    assert main([command, package, "--format", "json"]) == EXIT_OK
    out = capsys.readouterr().out
    json.loads(out)                       # would raise if anything preceded it
    assert "_ _ ____" not in out

    main([command, package])
    assert "_ _ ____" not in capsys.readouterr().out


def test_quiet_prints_nothing_at_all(make_package, capsys):
    assert main(["check", str(make_package()), "-q"]) == EXIT_OK
    assert capsys.readouterr().out == ""


def test_exit_codes(make_package, capsys):
    broken = make_package(name="broken.iirds", metadata="<rdf:RDF><unclosed>")
    assert main(["check", str(make_package()), "-q"]) == EXIT_OK
    assert main(["check", str(broken), "-q"]) == EXIT_FINDINGS
    assert main(["check", "/no/such/file.iirds", "-q"]) == EXIT_ERROR


def test_warnings_as_errors(make_package, capsys):
    """A relative IRI is a RECOMMENDED, so it must not fail a build unless the
    caller asks for that."""
    from conftest import MINIMAL_RDF
    relative = MINIMAL_RDF.replace("</rdf:RDF>",
                                   '  <iirds:Component rdf:about="c/1"/>\n</rdf:RDF>')
    package = str(make_package(metadata=relative))
    assert main(["check", package, "-q"]) == EXIT_OK
    assert main(["check", package, "-q", "-W"]) == EXIT_FINDINGS


def test_an_unpublished_version_is_rejected_by_the_parser(make_package):
    with pytest.raises(SystemExit) as exc:
        main(["check", str(make_package()), "--iirds-version", "9.9"])
    assert exc.value.code == 2


FRAGMENT = """<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:iirds="http://iirds.tekom.de/iirds#">
  <iirds:Topic rdf:about="urn:frag:topic1">
    <iirds:title>A fragment under test</iirds:title>
    <iirds:has-rendition>
      <iirds:Rendition>
        <iirds:format>application/xhtml+xml</iirds:format>
        <iirds:source>/absolute/path.xhtml</iirds:source>
      </iirds:Rendition>
    </iirds:has-rendition>
  </iirds:Topic>
</rdf:RDF>
"""


def test_fragment_mode_finds_real_defects_without_package_noise(tmp_path, capsys):
    """A bare metadata file — a spec example, a snippet under an editor's
    hands — is not a package, and drowning its one real defect under "no
    Package declared" noise teaches people to ignore the tool. --fragment
    wraps it in a throwaway container and suspends exactly the rules a
    fragment cannot satisfy, saying so in a note."""
    frag = tmp_path / "snippet.rdf"
    frag.write_text(FRAGMENT, "utf-8")
    assert main(["check", str(frag), "--fragment"]) == EXIT_FINDINGS
    out = capsys.readouterr().out
    assert "M9" in out                      # the real defect: absolute source
    # The suspended rules may be *named* -- in the note that says they were
    # suspended -- but must not appear as findings.
    finding_lines = [line for line in out.splitlines() if "suspended" not in line]
    for rid in ("M3", "M4", "L2", "S6"):
        assert not any(rid in line for line in finding_lines), rid
    assert "suspended" in out               # and the note is actually there

    clean = tmp_path / "clean.rdf"
    clean.write_text(FRAGMENT.replace("/absolute/path.xhtml", "content/t.xhtml"), "utf-8")
    assert main(["check", str(clean), "--fragment"]) == EXIT_OK


# ---------------------------------------------------------------------------
# The command's name, in every message the tool prints about itself
#
# Three console scripts point at `main`. All three answer to one name, the way
# `python3` answers `python`: the name is the distribution's, and the other two
# are what the checker was called before the library shipped beside it.
# ---------------------------------------------------------------------------

def test_the_version_flag_names_the_command(capsys):
    from iirds_validate import __version__

    with pytest.raises(SystemExit) as leaving:
        main(["--version"])
    assert leaving.value.code == 0
    assert capsys.readouterr().out == "iirds %s\n" % __version__


def test_help_names_the_command(capsys):
    with pytest.raises(SystemExit) as leaving:
        main(["--help"])
    assert leaving.value.code == 0
    assert capsys.readouterr().out.startswith("usage: iirds ")


@pytest.mark.parametrize("argv", [
    ["check", "--fragment", "/no/such/fragment.rdf"],
    ["check", "/no/such/package.iirds"],
    ["serve", "--host", "8.8.8.8", "--no-open"],
], ids=["missing-fragment", "missing-package", "serve-refuses-host"])
def test_an_operator_error_is_prefixed_with_the_command_name(capsys, argv):
    """`startswith`, not `in`: `iirds:` also occurs inside the vocabulary
    (`iirds:source`), and a prefix test that matched it would pass on an
    error message about the wrong thing."""
    assert main(argv) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("iirds: "), err


def test_an_empty_directory_is_an_operator_error_with_the_same_prefix(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == EXIT_ERROR
    assert capsys.readouterr().err.startswith("iirds: no iiRDS package found under ")
