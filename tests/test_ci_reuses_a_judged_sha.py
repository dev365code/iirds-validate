"""A commit judged on a work branch need not fill the queue again on main.

The expensive lint, test and mutation jobs may reuse a successful push run of
this same workflow and commit from the last week, with its address and branch
in the summary.
Every other job still runs. A run with skipped checks is not a full judgement,
and a lookup that cannot establish one must leave all checks enabled.

These tests run the workflow's shell with local API response shapes and hold
its job conditions, event scope and read permissions without a YAML package.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
SHA = "a" * 40
RUNS_URL = (
    "repos/sample/project/actions/workflows/ci.yml/runs"
    "?head_sha=%s&event=push&status=success&per_page=100" % SHA
)
CATALOGUES = ("upstream rule catalogue", "vendored catalogue is faithful to its pin")
HEAVY = {"lint", "test", "mutations"}
OTHER = {"wheel", "vendored-catalogue", "upstream-catalogue",
         "the-action-this-repo-offers", "the-action-on-a-runner-as-it-comes"}
CONDITION = "${{ always() && !cancelled() && needs.judged.outputs.run_id == '' }}"
SCOPE = "github.event_name == 'push' && github.ref == 'refs/heads/main'"
AGE_LIMIT = "select((.created_at | fromdateiso8601) > now - 7 * 86400)"
#: The lookup runs on ubuntu-latest and nowhere else. The cases that run its
#: shell need bash and jq, and on Windows the jq there writes CRLF under MSYS2
#: and this repository does not link tools in: they would be cases about a
#: shell the workflow never uses. What reads the workflow file runs everywhere.
SHELL_CASE = pytest.mark.skipif(
    os.name == "nt",
    reason="the judged step runs on ubuntu-latest; jq under MSYS2 writes CRLF "
           "and this repository does not link tools in on nt")


def jobs_of():
    """Read job blocks at the workflow's two-space indent, without comments."""
    text = WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    found = list(re.finditer(r"^  ([A-Za-z0-9_-]+):$", text, re.M))
    blocks = {}
    for index, match in enumerate(found):
        end = found[index + 1].start() if index + 1 < len(found) else len(text)
        blocks[match.group(1)] = "\n".join(
            line for line in text[match.end():end].splitlines()
            if not line.lstrip().startswith("#"))
    return blocks


def lookup():
    blocks = jobs_of()
    assert "judged" in blocks, "CI has no earlier-run lookup job"
    block = blocks["judged"]
    steps = block.split("    steps:\n", 1)
    assert len(steps) == 2, "judged has no steps"
    step = steps[1]
    scripts = re.findall(r"^        run: \|\n((?:          [^\n]*\n|\n)*)", step + "\n", re.M)
    assert len(scripts) == 1, "the lookup must have one shell block"
    return block, step, textwrap.dedent(scripts[0])


def created(days_ago=0, hours_ago=1):
    """A run's `created_at` as the API writes it, counted back from now."""
    when = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def branch_run(run_id=11, branch="wip/checks"):
    return {"id": run_id, "head_branch": branch, "head_sha": SHA,
            "html_url": "https://example.test/runs/%s" % run_id,
            "event": "push", "status": "completed", "conclusion": "success",
            "created_at": created()}


def full_jobs():
    names = (["judged", "lint", "installed wheel", "the-action-this-repo-offers",
              "the-action-on-a-runner-as-it-comes"]
             + ["py%s on ubuntu-latest" % version
                for version in ("3.9", "3.10", "3.11", "3.12", "3.13")]
             + ["py3.9 rdflib floor on ubuntu-latest", "py3.11 on windows-latest",
                "py3.11 on macos-latest"]
             + ["mutations (%s)" % shard for shard in range(1, 13)])
    jobs = [{"name": name, "conclusion": "success", "status": "completed",
             "run_attempt": 1} for name in names]
    jobs.extend({"name": name, "conclusion": "skipped", "status": "completed",
                 "run_attempt": 1} for name in CATALOGUES)
    return {"total_count": len(jobs), "jobs": jobs}


def jobs_url(run_id):
    return "repos/sample/project/actions/runs/%s/jobs?per_page=100" % run_id


def execute_lookup(tmp_path, runs, jobs, *, runs_code=0, jobs_code=0,
                   missing_gh=False, missing_jq=False, output_writable=True,
                   summary_writable=True):
    """Only the two local tools are on PATH; no installed gh can be reached."""
    _, _, script = lookup()
    bash = shutil.which("bash")
    jq = shutil.which("jq")
    if not bash or not jq:
        pytest.skip("the workflow shell cases require bash and jq")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if not missing_jq:
        (bin_dir / "jq").symlink_to(jq)
    replies = {RUNS_URL: {"body": runs, "code": runs_code}}
    replies.update({jobs_url(run_id): {"body": body, "code": jobs_code}
                    for run_id, body in jobs.items()})
    responses = tmp_path / "responses.json"
    responses.write_text(json.dumps(replies), encoding="utf-8")
    requests = tmp_path / "requests.txt"
    requests.touch()
    responder = tmp_path / "respond.py"
    responder.write_text(textwrap.dedent('''\
        import json
        import os
        import sys
        from pathlib import Path

        with Path(os.environ["TEST_REQUESTS"]).open("a") as out:
            out.write(json.dumps(sys.argv[1:]) + "\\n")
        replies = json.loads(Path(os.environ["TEST_RESPONSES"]).read_text())
        if len(sys.argv) != 3 or sys.argv[1] != "api" or sys.argv[2] not in replies:
            sys.exit(70)
        reply = replies[sys.argv[2]]
        body = reply["body"]
        sys.stdout.write(body if isinstance(body, str) else json.dumps(body))
        sys.exit(reply["code"])
        '''), encoding="utf-8")
    if not missing_gh:
        stub = bin_dir / "gh"
        stub.write_text('#!/bin/sh\nexec "$TEST_PYTHON" "$TEST_RESPONDER" "$@"\n',
                        encoding="utf-8")
        stub.chmod(0o755)
    output = tmp_path / ("output.txt" if output_writable else "gone/output.txt")
    summary = tmp_path / ("summary.md" if summary_writable else "summary-is-a-directory")
    if output_writable:
        output.touch()
    if summary_writable:
        summary.touch()
    else:
        summary.mkdir()
    env = dict(os.environ, PATH=str(bin_dir), GH_TOKEN="local-test",
               GITHUB_REPOSITORY="sample/project", GITHUB_SHA=SHA,
               GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary),
               TEST_PYTHON=sys.executable, TEST_RESPONDER=str(responder),
               TEST_RESPONSES=str(responses), TEST_REQUESTS=str(requests))
    result = subprocess.run([bash, "--noprofile", "--norc", "-e", "-o", "pipefail"],
                            input=script, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in requests.read_text().splitlines()]
    return (output.read_text() if output.exists() else "",
            summary.read_text() if summary.is_file() else "", calls)


@SHELL_CASE
def test_a_fully_judged_branch_run_is_named(tmp_path):
    run = branch_run()
    output, summary, calls = execute_lookup(
        tmp_path, {"total_count": 1, "workflow_runs": [run]}, {11: full_jobs()})
    assert output == "run_id=11\n"
    assert run["html_url"] in summary and run["head_branch"] in summary
    # One sentence: the run it names, and not also the one saying every job runs.
    assert summary.count("\n") == 1, summary
    assert calls == [["api", RUNS_URL], ["api", jobs_url(11)]]


def test_the_jobs_a_full_judgement_may_skip_are_the_catalogue_checks():
    """Two jobs may be skipped in a run that still counts as a full judgement:
    the scheduled catalogue checks. They have to be jobs of this workflow under
    those names, or the exemption would cover a job nobody wrote."""
    blocks = jobs_of()
    for name in CATALOGUES:
        assert any("    name: " + name in blocks[job] for job in OTHER)


@SHELL_CASE
@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_every_required_job_must_succeed(tmp_path, conclusion):
    jobs = full_jobs()
    next(job for job in jobs["jobs"] if job["name"] == "lint")["conclusion"] = conclusion
    output, summary, _ = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run()]}, {11: jobs})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary


@SHELL_CASE
def test_main_is_not_an_earlier_branch_judgement(tmp_path):
    output, _, calls = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run(branch="main")]}, {11: full_jobs()})
    assert output == ""
    assert calls == [["api", RUNS_URL]]


@SHELL_CASE
def test_the_first_full_judgement_can_be_the_second_run(tmp_path):
    first = full_jobs()
    first["jobs"][1]["conclusion"] = "skipped"
    second = branch_run(12, "fix/checks")
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run(), second]}, {11: first, 12: full_jobs()})
    assert output == "run_id=12\n"
    assert second["html_url"] in summary and second["head_branch"] in summary
    assert branch_run()["html_url"] not in summary
    assert calls[-1] == ["api", jobs_url(12)]


@SHELL_CASE
@pytest.mark.parametrize("days, hours, reused", [(6, 23, True), (7, 1, False), (30, 0, False)])
def test_only_a_judgement_from_the_last_week_is_reused(tmp_path, days, hours, reused):
    """The same commit is not the same judgement for ever. The suite reads the
    tags and today's date, and installs what its dependency floors resolve to
    on the day, so a commit judged green can be judged red later without a
    byte of it changing. The Monday schedule judges main in full every week; a
    reused judgement is held to the same age."""
    run = dict(branch_run(), created_at=created(days_ago=days, hours_ago=hours))
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [run]}, {11: full_jobs()})
    if reused:
        assert output == "run_id=11\n"
        assert run["html_url"] in summary
    else:
        assert output == ""
        assert "no earlier run of this commit was judged in full here; every job runs" in summary
        assert calls == [["api", RUNS_URL]]


def test_the_age_limit_is_one_filter_of_a_week():
    _, _, script = lookup()
    assert script.count(AGE_LIMIT) == 1


@SHELL_CASE
def test_a_reuse_that_cannot_be_recorded_is_not_announced(tmp_path):
    """The summary names the earlier run only once the output that skips the
    checks has been written. Announced first and then not recorded, the reuse
    left two sentences in the summary, and the first of them was false."""
    output, summary, _ = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run()]}, {11: full_jobs()},
        output_writable=False)
    assert output == ""
    assert "judged in full by" not in summary
    assert "no earlier run of this commit was judged in full here; every job runs" in summary


@SHELL_CASE
def test_a_reuse_the_summary_cannot_name_is_not_made(tmp_path):
    """Checks are skipped on the strength of a run the summary names. If the
    summary file cannot be opened, nothing could name the run, so it is not
    reused. A write that fails once the file is open is not covered here."""
    output, _, _ = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run()]}, {11: full_jobs()},
        summary_writable=False)
    assert output == ""


@SHELL_CASE
@pytest.mark.parametrize("field, value", [("head_sha", "b" * 40), ("event", "pull_request"),
                                          ("status", "in_progress"), ("conclusion", "failure")])
def test_each_run_in_the_answer_is_checked_again(tmp_path, field, value):
    """The query asks for this commit's successful push runs, and the answer is
    read as though it might hold something else: a run of another commit, of
    another event, or one not finished green is passed over by the lookup
    itself, not only by the server's filter."""
    run = dict(branch_run(), **{field: value})
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [run]}, {11: full_jobs()})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary
    assert calls == [["api", RUNS_URL]]


@SHELL_CASE
def test_a_run_of_another_commit_in_the_answer_is_passed_over(tmp_path):
    other = dict(branch_run(77, "wip/other"), head_sha="b" * 40)
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [other, branch_run()]}, {77: full_jobs(), 11: full_jobs()})
    assert output == "run_id=11\n"
    assert other["html_url"] not in summary
    assert ["api", jobs_url(77)] not in calls


@SHELL_CASE
def test_a_run_with_only_the_catalogue_checks_is_not_a_full_judgement(tmp_path):
    """Leaving the catalogue checks out must not leave nothing to look at: over
    no jobs at all, "every job succeeded" is true."""
    jobs = [{"name": name, "conclusion": "success", "status": "completed", "run_attempt": 1}
            for name in CATALOGUES]
    output, summary, _ = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run()]}, {11: {"total_count": 2, "jobs": jobs}})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary


@SHELL_CASE
def test_an_empty_jobs_response_stops_the_lookup(tmp_path):
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run(), branch_run(12)]},
        {11: "", 12: full_jobs()})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary
    assert calls == [["api", RUNS_URL], ["api", jobs_url(11)]]


@SHELL_CASE
@pytest.mark.parametrize("case", ["runs-status", "jobs-status", "runs-text", "jobs-text",
                                 "runs-empty-text", "jobs-empty-text", "count", "no-runs",
                                 "no-jobs", "page-count", "repeated-run", "null-branch",
                                 "no-gh", "no-jq", "no-created", "created-text"])
def test_unconfirmed_response_shapes_leave_every_job_enabled(tmp_path, case):
    runs = {"workflow_runs": [branch_run()]}
    jobs = full_jobs()
    options = {}
    if case == "runs-status":
        options["runs_code"] = 1
    elif case == "jobs-status":
        options["jobs_code"] = 1
    elif case == "runs-text":
        runs = "not json"
    elif case == "jobs-text":
        jobs = "not json"
    elif case == "runs-empty-text":
        runs = ""
    elif case == "jobs-empty-text":
        jobs = ""
    elif case == "count":
        jobs["total_count"] += 1
    elif case == "no-runs":
        runs["workflow_runs"] = []
    elif case == "no-jobs":
        jobs = {"total_count": 0, "jobs": []}
    elif case == "page-count":
        jobs = {"total_count": 101, "jobs": [copy.deepcopy(jobs["jobs"][0])
                                             for _ in range(100)]}
    elif case == "repeated-run":
        runs["workflow_runs"].append(branch_run())
    elif case == "null-branch":
        runs["workflow_runs"][0]["head_branch"] = None
    elif case == "no-gh":
        options["missing_gh"] = True
    elif case == "no-jq":
        options["missing_jq"] = True
    elif case == "no-created":
        del runs["workflow_runs"][0]["created_at"]
    elif case == "created-text":
        runs["workflow_runs"][0]["created_at"] = "yesterday"
    output, summary, _ = execute_lookup(tmp_path, runs, {11: jobs}, **options)
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary


def test_only_the_three_expensive_jobs_depend_on_judged():
    blocks = jobs_of()
    assert set(blocks) == HEAVY | OTHER | {"judged"}
    for name in HEAVY:
        assert re.search(r"^    needs: judged$", blocks[name], re.M), name
        assert re.search(r"^    if: " + re.escape(CONDITION) + r"$", blocks[name], re.M), name
    for name in OTHER:
        assert not re.search(r"^    needs:", blocks[name], re.M), name
        assert "needs.judged" not in blocks[name], name


def test_lookup_has_read_permissions_and_main_push_scope():
    block, step, script = lookup()
    permissions = re.search(r"^    permissions:\n((?:      [^\n]*\n)+)", block, re.M)
    assert permissions, "judged has no job permissions"
    assert dict(re.findall(r"^      ([\w-]+): (\S+)$", permissions.group(1), re.M)) == {
        "actions": "read", "contents": "read"}
    for line in ("    runs-on: ubuntu-latest", "    timeout-minutes: 5",
                 "    continue-on-error: true"):
        assert line in block.splitlines()
    assert "uses:" not in block
    assert re.search(r"^        if: " + re.escape(SCOPE) + r"$", step, re.M)
    # The shell above runs the script as GitHub runs a `shell: bash` step,
    # `bash --noprofile --norc -eo pipefail`. Without the key the step gets
    # `bash -e`, and the cases here would be about a different shell.
    assert "        shell: bash" in step.splitlines()
    assert "          GH_TOKEN: ${{ github.token }}" in step.splitlines()
    step_id = re.search(r"^        id: ([\w-]+)$", step, re.M)
    assert step_id
    assert "      run_id: ${{ steps.%s.outputs.run_id }}" % step_id.group(1) in block.splitlines()
    assert "${{" not in script
    assert "$GITHUB_REPOSITORY" in script and "$GITHUB_SHA" in script
