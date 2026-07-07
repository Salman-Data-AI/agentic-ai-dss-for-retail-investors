"""
Deterministic signal evaluation for approved compiled rule sets.

This module receives already-fetched metric data and never calls a provider.
It expects rule sets in the shape validated by ``agent.rule_sets``.

Runtime data policy: if any relevant clause is unevaluable because its metric is
missing, bool, non-numeric, or an error dict, evaluation returns ``ERROR`` with a
structured clause outcome. The DI#4 fail-closed compile stance does not define
runtime missing-data semantics; making unevaluable data explicit avoids quietly
turning absent metrics into BUY/SELL/SKIP/HOLD decisions.

Triggering policy: the downstream database currently has a single
``triggering_rule`` text column. This pure result therefore includes both a
single ``triggering_rule`` summary string and a ``triggering_clauses`` list for
debugging/future UI use. BUY success reports all passing BUY clauses; BUY skip
reports failing clauses. SELL reports all true SELL clauses; HOLD reports an
empty triggering list and a summary that no SELL clause fired.
"""

from __future__ import annotations

import operator as operator_module
from numbers import Real
from typing import Any


BUY_EVALUATION = "BUY"
SELL_EVALUATION = "SELL"

_OPERATORS = {
    "<": operator_module.lt,
    "<=": operator_module.le,
    ">": operator_module.gt,
    ">=": operator_module.ge,
    "==": operator_module.eq,
    "!=": operator_module.ne,
}


def evaluate_rule_set(rule_set: dict[str, Any], metrics: dict[str, Any], evaluation_type: str) -> dict[str, Any]:
    """Evaluate BUY or SELL clauses and return a structured signal result."""
    if evaluation_type == BUY_EVALUATION:
        clauses = rule_set.get("buy_clauses", [])
        success_signal = "BUY"
        fallback_signal = "SKIP"
    elif evaluation_type == SELL_EVALUATION:
        clauses = rule_set.get("sell_clauses", [])
        success_signal = "SELL"
        fallback_signal = "HOLD"
    else:
        return _error_result(f"Unsupported evaluation_type: {evaluation_type}.", [])

    if not isinstance(clauses, list) or not clauses:
        return _error_result(f"No clauses available for {evaluation_type} evaluation.", [])

    outcomes = [_evaluate_clause(clause, metrics, index) for index, clause in enumerate(clauses)]
    errors = [outcome for outcome in outcomes if outcome["status"] == "error"]
    if errors:
        return _error_result("One or more clauses could not be evaluated.", outcomes)

    if evaluation_type == BUY_EVALUATION:
        failing = [outcome for outcome in outcomes if outcome["status"] == "false"]
        if failing:
            return _result(fallback_signal, failing, outcomes)
        return _result(success_signal, outcomes, outcomes)

    firing = [outcome for outcome in outcomes if outcome["status"] == "true"]
    if firing:
        return _result(success_signal, firing, outcomes)
    return _result(fallback_signal, [], outcomes, triggering_rule="No SELL clause fired.")


def _evaluate_clause(clause: dict[str, Any], metrics: dict[str, Any], index: int) -> dict[str, Any]:
    metric_key = clause.get("bound_metric")
    base = {
        "index": index,
        "user_phrase": clause.get("user_phrase"),
        "bound_metric": metric_key,
        "operator": clause.get("operator"),
        "threshold": clause.get("threshold"),
    }

    if metric_key not in metrics:
        return {**base, "status": "error", "reason": "Metric is missing."}

    actual_value = metrics[metric_key]
    if isinstance(actual_value, dict) and "error" in actual_value:
        return {**base, "actual_value": actual_value, "status": "error", "reason": "Metric value is an error dict."}

    if not _is_number(actual_value):
        return {**base, "actual_value": actual_value, "status": "error", "reason": "Metric value is not numeric."}

    threshold = clause.get("threshold")
    if not _is_number(threshold):
        return {**base, "actual_value": actual_value, "status": "error", "reason": "Threshold is not numeric."}

    comparator = _OPERATORS.get(clause.get("operator"))
    if comparator is None:
        return {**base, "actual_value": actual_value, "status": "error", "reason": "Operator is unsupported."}

    passed = comparator(actual_value, threshold)
    return {**base, "actual_value": actual_value, "status": "true" if passed else "false"}


def _result(
    signal: str,
    triggering_clauses: list[dict[str, Any]],
    clause_outcomes: list[dict[str, Any]],
    triggering_rule: str | None = None,
) -> dict[str, Any]:
    return {
        "signal": signal,
        "triggering_rule": triggering_rule if triggering_rule is not None else _summarize_triggering_rule(triggering_clauses),
        "triggering_clauses": triggering_clauses,
        "clause_outcomes": clause_outcomes,
        "error": None,
    }


def _error_result(message: str, clause_outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "signal": "ERROR",
        "triggering_rule": "",
        "triggering_clauses": [],
        "clause_outcomes": clause_outcomes,
        "error": message,
    }


def _summarize_triggering_rule(triggering_clauses: list[dict[str, Any]]) -> str:
    phrases = [str(clause.get("user_phrase", "")).strip() for clause in triggering_clauses]
    phrases = [phrase for phrase in phrases if phrase]
    return "; ".join(phrases)


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)
