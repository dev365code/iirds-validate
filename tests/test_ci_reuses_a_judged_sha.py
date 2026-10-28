"""A commit judged on a work branch need not fill the queue again on main.

The expensive lint, test and mutation jobs may reuse a successful push run of
this same workflow and commit, with its address and branch in the summary.
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


def branch_run(run_id=11, branch="wip/checks"):
    return {"id": run_id, "head_branch": branch, "head_sha": SHA,
            "html_url": "https://example.test/runs/%s" % run_id,
            "event": "push", "status": "completed", "conclusion": "success"}


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
                   missing_gh=False, missing_jq=False):
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
    output = tmp_path / "output.txt"
    summary = tmp_path / "summary.md"
    output.touch()
    summary.touch()
    env = dict(os.environ, PATH=str(bin_dir), GH_TOKEN="local-test",
               GITHUB_REPOSITORY="sample/project", GITHUB_SHA=SHA,
               GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary),
               TEST_PYTHON=sys.executable, TEST_RESPONDER=str(responder),
               TEST_RESPONSES=str(responses), TEST_REQUESTS=str(requests))
    result = subprocess.run([bash, "--noprofile", "--norc", "-e", "-o", "pipefail"],
                            input=script, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in requests.read_text().splitlines()]
    return output.read_text(), summary.read_text(), calls


def test_a_fully_judged_branch_run_is_named(tmp_path):
    run = branch_run()
    output, summary, calls = execute_lookup(
        tmp_path, {"total_count": 1, "workflow_runs": [run]}, {11: full_jobs()})
    assert output == "run_id=11\n"
    assert run["html_url"] in summary and run["head_branch"] in summary
    assert calls == [["api", RUNS_URL], ["api", jobs_url(11)]]
    blocks = jobs_of()
    for name in CATALOGUES:
        assert any("    name: " + name in blocks[job] for job in OTHER)


@pytest.mark.parametrize("conclusion", ["skipped", "failure", "cancelled", None])
def test_every_required_job_must_succeed(tmp_path, conclusion):
    jobs = full_jobs()
    next(job for job in jobs["jobs"] if job["name"] == "lint")["conclusion"] = conclusion
    output, summary, _ = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run()]}, {11: jobs})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary


def test_main_is_not_an_earlier_branch_judgement(tmp_path):
    output, _, calls = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run(branch="main")]}, {11: full_jobs()})
    assert output == ""
    assert calls == [["api", RUNS_URL]]


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


def test_an_empty_jobs_response_stops_the_lookup(tmp_path):
    output, summary, calls = execute_lookup(
        tmp_path, {"workflow_runs": [branch_run(), branch_run(12)]},
        {11: "", 12: full_jobs()})
    assert output == ""
    assert "no earlier run of this commit was judged in full here; every job runs" in summary
    assert calls == [["api", RUNS_URL], ["api", jobs_url(11)]]


@pytest.mark.parametrize("case", ["runs-status", "jobs-status", "runs-text", "jobs-text",
                                 "runs-empty-text", "jobs-empty-text", "count", "no-runs",
                                 "no-jobs", "page-count", "repeated-run", "null-branch",
                                 "no-gh", "no-jq"])
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
    assert "          GH_TOKEN: ${{ github.token }}" in step.splitlines()
    step_id = re.search(r"^        id: ([\w-]+)$", step, re.M)
    assert step_id
    assert "      run_id: ${{ steps.%s.outputs.run_id }}" % step_id.group(1) in block.splitlines()
    assert "${{" not in script
    assert "$GITHUB_REPOSITORY" in script and "$GITHUB_SHA" in script
