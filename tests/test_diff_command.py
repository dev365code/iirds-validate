"""`iirds diff`, and the number a build gates on.

The subcommand is small; the exit code is the interface. Everything here is
about that number meaning one thing, and about the rewrite in `main()` that
turns an unrecognised verb into a path -- which is how a new subcommand
arrives silently broken.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from conftest import MINIMAL_RDF
from iirds_validate import cli, runner


def two_formats(metadata):
    return metadata.replace(
        "<iirds:format>application/xhtml+xml</iirds:format>",
        "<iirds:format>application/xhtml+xml</iirds:format>"
        "<iirds:format>text/html</iirds:format>")


def stored(tmp_path, package, name="stored.json", kinds=None):
    document = runner.run(package, kinds or runner.ALL_KINDS).as_dict()
    path = tmp_path / name
    path.write_text(json.dumps(document), "utf-8")
    return str(path)


def test_every_subcommand_is_recognised_as_one(capsys):
    """`main()` treats an unknown first word as a path, so a subcommand
    missing from the list it checks is swallowed and its arguments are read as
    packages. The list is derived from the parser rather than kept beside it,
    because two lists of one thing drift and this one drifts silently."""
    parser, sub = cli.build_parser()
    assert "diff" in sub.choices
    for name in sub.choices:
        assert name in cli.subcommands(), name


def test_the_command_is_not_read_as_a_path(tmp_path, make_package, capsys):
    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    code = cli.main(["diff", stored(tmp_path, good), str(good)])
    assert code == 0, capsys.readouterr()


def test_a_package_that_got_worse_exits_one(tmp_path, make_package, capsys):
    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    bad = make_package(name="bad.iirds", metadata=two_formats(MINIMAL_RDF))
    code = cli.main(["diff", stored(tmp_path, good), str(bad)])
    out = capsys.readouterr().out
    assert code == 1, out
    assert "regression" in out, out


def test_a_package_that_got_better_exits_zero(tmp_path, make_package, capsys):
    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    bad = make_package(name="bad.iirds", metadata=two_formats(MINIMAL_RDF))
    code = cli.main(["diff", stored(tmp_path, bad), str(good)])
    assert code == 0, capsys.readouterr().out


def test_a_report_it_cannot_read_is_two_and_a_sentence(tmp_path, make_package, capsys):
    """Not one. One means "errors found", and a build told that would go
    looking for a defect in the package instead of at its own baseline."""
    package = make_package(name="one.iirds", metadata=MINIMAL_RDF)
    older = tmp_path / "older.json"
    older.write_text(json.dumps({"schemaVersion": 1}), "utf-8")
    code = cli.main(["diff", str(older), str(package)])
    captured = capsys.readouterr()
    assert code == 2
    assert "validate the package again" in captured.err.lower(), captured


def test_a_file_that_is_not_json_is_two_and_not_a_traceback(tmp_path, make_package, capsys):
    package = make_package(name="one.iirds", metadata=MINIMAL_RDF)
    junk = tmp_path / "junk.json"
    junk.write_text("{not json", "utf-8")
    assert cli.main(["diff", str(junk), str(package)]) == 2
    assert capsys.readouterr().err.strip()


def test_the_stored_report_decides_which_rules_run(tmp_path, make_package, capsys):
    """A baseline stored from `check` compared against a run of everything
    produces a screen of rules the stored run never put. The stored report
    says which command made it, so this runs that one."""
    package = make_package(name="one.iirds", metadata=MINIMAL_RDF)
    path = stored(tmp_path, package, kinds=runner.LINT_KINDS)
    assert cli.main(["diff", path, str(package), "--format", "json"]) == 0
    document = json.loads(capsys.readouterr().out)
    assert document["newlyChecked"] == [], document["newlyChecked"]
    assert document["noLongerChecked"] == [], document["noLongerChecked"]
    assert document["comparable"]


def test_quiet_says_nothing_and_still_answers(tmp_path, make_package, capsys):
    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    bad = make_package(name="bad.iirds", metadata=two_formats(MINIMAL_RDF))
    code = cli.main(["diff", stored(tmp_path, good), str(bad), "-q"])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == "", captured.out


def test_json_is_the_document_the_library_returns(tmp_path, make_package, capsys):
    from iirds_validate import difference as diff

    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    bad = make_package(name="bad.iirds", metadata=two_formats(MINIMAL_RDF))
    path = stored(tmp_path, good)
    assert cli.main(["diff", path, str(bad), "--format", "json"]) == 1
    printed = json.loads(capsys.readouterr().out)
    expected = diff.difference(json.loads(pathlib.Path(path).read_text("utf-8")),
                               runner.run(bad, runner.ALL_KINDS).as_dict()).as_dict()
    assert printed == json.loads(json.dumps(expected))


def test_warnings_as_errors_is_not_offered(tmp_path, make_package):
    """The gate is about errors this run has and the stored report does not.
    `-W` on the other subcommands changes only the exit code and is recorded
    nowhere in a report, so a stored one cannot say whether it was gated that
    way -- offering it here would promise a comparison the documents cannot
    support."""
    good = make_package(name="good.iirds", metadata=MINIMAL_RDF)
    with pytest.raises(SystemExit) as exit_:
        cli.main(["diff", stored(tmp_path, good), str(good), "-W"])
    assert exit_.value.code == 2


def test_the_exit_codes_are_the_ones_the_module_documents():
    """`0 clean, 1 errors found, 2 could not run`, with one clause added for
    this command rather than a private code space: a shop that wired `set -e`
    to the old meanings keeps them."""
    assert "0 clean, 1 errors found, 2 could not run" in cli.__doc__
    said = " ".join(cli.__doc__.split())
    assert 'For `diff`, "errors found" means errors this run has and the stored ' \
           'report does not.' in said, said
