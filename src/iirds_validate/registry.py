"""Rule registration.

A rule's *metadata* (priority, applicable versions and variants, the sentence in
the specification it enforces) comes from the catalogue extracted from
plusmeta's MIT-licensed tool. A rule's *implementation* is the function below
the decorator. Keeping the identifiers aligned means the two tools can be run
over the same package and diffed rule by rule.
"""
from __future__ import annotations

import hashlib
import json
from typing import Callable, Dict, List, Optional, Tuple

from . import resources
from .model import Rule, rule_source

_registry: Dict[str, Rule] = {}


def _load_catalog():
    """The rules, and where they came from.

    The provenance keys were being parsed and thrown away, which is how
    `crossvalidate.py` came to fetch the fixture corpus from `master` while the
    rules it validates were pinned to a commit. Whoever needs the rules
    generally needs to know which revision produced them.
    """
    raw = json.loads(resources.read_text("rule-catalog.json"))
    return ({r["id"]: r for r in raw["rules"]},
            {k: v for k, v in raw.items() if k.startswith("_")})


CATALOG, PROVENANCE = _load_catalog()


def rule(rule_id: str, kind: Optional[str] = None, prio: Optional[str] = None,
         title: Optional[str] = None, versions: Optional[Tuple[str, ...]] = None,
         variants: Optional[Tuple[str, ...]] = None, spec: Optional[str] = None,
         conformance: bool = False, fix: Optional[str] = None,
         covers: Tuple[str, ...] = (), diagnosis: str = "") -> Callable:
    """Register a rule, inheriting anything not given from the catalogue."""
    meta = CATALOG.get(rule_id, {})

    def decorator(fn: Callable) -> Callable:
        if rule_id in _registry:
            raise ValueError(f"duplicate rule id: {rule_id}")
        _registry[rule_id] = Rule(
            id=rule_id,
            kind=kind or meta.get("kind") or "lint",
            prio=prio or meta.get("prio") or "MUST",
            title=title or meta.get("en") or rule_id,
            versions=tuple(versions if versions is not None else meta.get("versions", ())),
            variants=tuple(variants if variants is not None else meta.get("variants", ())),
            spec=spec or meta.get("spec"),
            fn=fn,
            conformance=conformance,
            fix=fix,
            covers=tuple(covers),
            diagnosis=diagnosis,
        )
        return fn

    return decorator


def _ensure_registered() -> None:
    """Every rule module, imported -- which is what registers a rule.

    Registration is a side effect of importing `iirds_validate.rules`, and
    for a long time the package did that on its own import, so anything that
    asked the registry found it full. The package no longer imports eagerly;
    the registry asks for the modules itself, the first time it is asked
    anything, rather than answering "no rules" to a caller that imported
    only this module.
    """
    from . import rules  # noqa: F401  -- importing registers every rule


def all_rules() -> List[Rule]:
    _ensure_registered()

    def sort_key(r: Rule):
        head = r.id[0]
        digits = "".join(c if c.isdigit() or c == "." else " " for c in r.id[1:]).split()
        return (head, [int(p) if p.isdigit() else 0 for p in (digits[0].split(".") if digits else ["0"])], r.id)
    return sorted(_registry.values(), key=sort_key)


def rule_set_digest(rules: Optional[List[Rule]] = None) -> str:
    """What this build's rules *are*, in one string, so two reports can be
    asked whether they were judged by the same set before they are compared.

    What it sees: every registered rule's id, whose rule it is, its kind, the
    severity its priority produces, the versions and variants it applies to,
    and whether it runs on a conformance check. Change any of those and this
    string moves.

    What it does not see, and the reason `toolVersion` is recorded beside it:

    * **the rules' implementations.** A rule whose body was rewritten has the
      same identity and the same digest. `tests/test_report_envelope.py` pins
      that as a fact rather than leaving it a caveat here, because a later
      difference view must not be built on a promise this string cannot keep.
    * **the runner's own policy** -- which kinds a command selects, which
      rules an unpacked container cannot answer, which a fragment suspends,
      and the run-time severity demotion. None of them is a property of a
      rule, and each changes what a run says.

    So "the same digest" means "the same registered rule metadata", never "the
    same rules". The severity is hashed rather than the priority keyword
    because MUST, MUST NOT, REQUIRED and SHALL all produce an error: hashing
    the spelling would refuse to compare two reports over a difference no
    verdict can express. The source is hashed because `B*`, `L*` and `S4`-`S8`
    share an identifier namespace with the catalogue -- if the catalogue ever
    mints a real `B1`, this string moves and the comparison stops, which is
    the safe direction for a report that cannot be repaired after the fact.

    Pure, and takes its input, so a test can ask what a *different* rule set
    would hash to without touching the registry every other test reads.
    """
    if rules is None:
        _ensure_registered()
        rules = all_rules()
    identities = [{
        "id": rule.id,
        "source": rule_source(rule.id),
        "kind": rule.kind,
        "severity": str(rule.severity),
        "versions": sorted(rule.versions),
        "variants": sorted(rule.variants),
        "conformance": bool(rule.conformance),
    } for rule in sorted(rules, key=lambda r: r.id)]
    blob = json.dumps(identities, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def rules_of_kind(kind: str) -> List[Rule]:
    return [r for r in all_rules() if r.kind == kind]


def implemented_ids() -> set:
    _ensure_registered()
    return set(_registry)


def coverage() -> dict:
    """Implemented against catalogued, per kind, plus this project's own.

    The earlier version put every uncatalogued rule in the `lint` bucket, so
    the content rules and the extra system rules were counted as
    interoperability rules and `system` reported 3 when there were 8. The
    README took its numbers from here, and a reviewer comparing the table to
    the command would have found the discrepancy in five minutes.
    """
    out: Dict[str, dict] = {}
    for kind in ("container", "schema", "system", "content", "lint"):
        out[kind] = {"total": 0, "implemented": 0, "ours": 0}
    for rid, meta in CATALOG.items():
        bucket = out.setdefault(meta["kind"], {"total": 0, "implemented": 0, "ours": 0})
        bucket["total"] += 1
        bucket["implemented"] += rid in _registry
    for rule in _registry.values():
        if rule.id not in CATALOG:
            out.setdefault(rule.kind, {"total": 0, "implemented": 0, "ours": 0})["ours"] += 1
    return out
