"""Rule registration.

A rule's *metadata* (priority, applicable versions and variants, the sentence in
the specification it enforces) comes from the catalogue extracted from
plusmeta's MIT-licensed tool. A rule's *implementation* is the function below
the decorator. Keeping the identifiers aligned means the two tools can be run
over the same package and diffed rule by rule.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .model import Rule

CATALOG_PATH = Path(__file__).parent / "data" / "rule-catalog.json"

_registry: Dict[str, Rule] = {}


def _load_catalog() -> Dict[str, dict]:
    raw = json.loads(CATALOG_PATH.read_text("utf-8"))
    return {r["id"]: r for r in raw["rules"]}


CATALOG = _load_catalog()


def rule(rule_id: str, kind: Optional[str] = None, prio: Optional[str] = None,
         title: Optional[str] = None, versions: Optional[Tuple[str, ...]] = None,
         variants: Optional[Tuple[str, ...]] = None, spec: Optional[str] = None) -> Callable:
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
        )
        return fn

    return decorator


def all_rules() -> List[Rule]:
    def sort_key(r: Rule):
        head = r.id[0]
        digits = "".join(c if c.isdigit() or c == "." else " " for c in r.id[1:]).split()
        return (head, [int(p) if p.isdigit() else 0 for p in (digits[0].split(".") if digits else ["0"])], r.id)
    return sorted(_registry.values(), key=sort_key)


def rules_of_kind(kind: str) -> List[Rule]:
    return [r for r in all_rules() if r.kind == kind]


def implemented_ids() -> set:
    return set(_registry)


def coverage() -> dict:
    """How much of the catalogue is actually implemented, per kind."""
    out: Dict[str, dict] = {}
    for rid, meta in CATALOG.items():
        bucket = out.setdefault(meta["kind"], {"total": 0, "implemented": 0})
        bucket["total"] += 1
        bucket["implemented"] += rid in _registry
    extra = sorted(rid for rid in _registry if rid not in CATALOG)
    out["lint"] = {"total": len(extra), "implemented": len(extra)}
    return out
