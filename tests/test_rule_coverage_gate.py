"""The gate on docs/rule-coverage.json, which three count changes walked past.

`--check` compared the never-fires set and nothing else, so the two numbers the
same tool writes -- how many rules there are, and how many have been seen to
fire -- sat at 185 and 184 while the suite printed 188 and 187, and `make
check` stayed green through all of it. In a repository whose thesis is that
every claim is held by a gate, a generated file no gate reads is the claim
without the gate.

The numbers are checked here rather than pinned, because pinning them is what
the baseline file is for: the test says the gate must notice, not what the
count is.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import rule_coverage  # noqa: E402


def _baseline(**overrides):
    """A baseline that agrees with the live state, minus whatever is overridden."""
    rules, never, fired = rule_coverage._state()
    return dict({"never_fires": never, "rules": len(rules), "exercised": len(fired)},
                **overrides)


def _check_against(tmp_path, monkeypatch, content) -> int:
    path = tmp_path / "rule-coverage.json"
    path.write_text(json.dumps(content), "utf-8")
    monkeypatch.setattr(rule_coverage, "BASELINE", path)
    return rule_coverage.check()


def test_a_baseline_that_agrees_with_the_suite_passes(tmp_path, monkeypatch):
    assert _check_against(tmp_path, monkeypatch, _baseline()) == 0


def test_a_stale_rule_count_is_caught(tmp_path, monkeypatch):
    """Three rules were added and this number did not move."""
    stale = _baseline(rules=_baseline()["rules"] - 3)
    assert _check_against(tmp_path, monkeypatch, stale) != 0


def test_a_stale_exercised_count_is_caught(tmp_path, monkeypatch):
    stale = _baseline(exercised=_baseline()["exercised"] - 3)
    assert _check_against(tmp_path, monkeypatch, stale) != 0


def test_a_baseline_missing_the_numbers_is_caught(tmp_path, monkeypatch):
    """An older file, from before the tool wrote them. Silence is not agreement."""
    partial = _baseline()
    del partial["rules"]
    assert _check_against(tmp_path, monkeypatch, partial) != 0
