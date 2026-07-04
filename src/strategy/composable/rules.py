"""Rule dataclass and evaluator.

A rule is ``{ id, scope, priority, when -> predicate, then -> action }``. On each
bar the evaluator keeps rules whose scope matches the current position state
(flat | long | always), checks them in priority order (higher first), and runs
the action of the first rule whose predicate is true. If nothing matches, the
result is HOLD. """

from __future__ import annotations

from dataclasses import dataclass

from src.engine.models import Signal
from src.engine.types import SignalType

from .actions import Action, parse_action, run_action
from .context import EvaluationContext
from .errors import CompileError
from .predicates import Predicate, compile_predicate

_SCOPES = {"flat", "long", "always"}


@dataclass
class Rule:
    id: str
    scope: str
    priority: int
    predicate: Predicate
    action: Action


def compile_rules(rules_config: list, series_ids: set[str]) -> list[Rule]:
    if not isinstance(rules_config, list) or not rules_config:
        raise CompileError("'rules' must be a non-empty list")
    rules: list[Rule] = []
    seen_ids: set[str] = set()
    for raw in rules_config:
        rid = raw.get("id")
        if not rid or rid in seen_ids:
            raise CompileError(f"each rule needs a unique 'id' (bad/duplicate: {rid!r})")
        seen_ids.add(rid)
        scope = raw.get("scope", "always")
        if scope not in _SCOPES:
            raise CompileError(f"rule '{rid}' scope must be one of {sorted(_SCOPES)}, got '{scope}'")
        try:
            priority = int(raw.get("priority", 0))
        except (TypeError, ValueError):
            raise CompileError(f"rule '{rid}' priority must be an integer")
        if "when" not in raw or "then" not in raw:
            raise CompileError(f"rule '{rid}' needs both 'when' and 'then'")
        predicate = compile_predicate(raw["when"], series_ids)
        action = parse_action(raw["then"])
        rules.append(Rule(rid, scope, priority, predicate, action))
    # higher priority first; stable within equal priority
    rules.sort(key=lambda r: -r.priority)
    return rules


def evaluate_rules(rules: list[Rule], ctx: EvaluationContext) -> Signal:
    long = ctx.is_long()
    scope_now = "long" if long else "flat"
    for rule in rules:  # already sorted by priority desc
        if rule.scope not in (scope_now, "always"):
            continue
        if rule.predicate(ctx):
            return run_action(ctx, rule.action)
    return Signal(type=SignalType.HOLD)
