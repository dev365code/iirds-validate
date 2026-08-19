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
    assert "iirdsv check" in out
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
