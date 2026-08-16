"""
Pure validation helpers for compiled user rule sets.

Chunk 1 deliberately defines a narrow rule-set contract for later compile and
UI work to build against:

- A rule set is a dict with ``buy_clauses`` and ``sell_clauses`` lists.
- Each clause has ``user_phrase``, ``bound_metric``, ``operator``, and
  ``threshold``.
- Operators are numeric comparisons only: ``<``, ``<=``, ``>``, ``>=``,
  ``==``, and ``!=``. This matches the current DI#4 example of natural-language
  valuation rules compiling to numeric metric checks, without silently adding
  categorical semantics that the design notes have not specified.
- Thresholds must be int or float values, excluding bool. Strings and ranges are
  rejected until a later design explicitly defines categorical or interval
  behavior.
- Invalid means the validator cannot positively prove the clause is executable:
  unknown metric, malformed clause, unsupported operator, non-numeric threshold,
  missing required text, or an empty rule set.

The allowed metric keys are passed in by the caller. This module intentionally
does not import TOOL_SCHEMAS or any runtime agent code.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

ALLOWED_OPERATORS = frozenset({"<", "<=", ">", ">=", "==", "!="})
CLAUSE_LIST_KEYS = ("buy_clauses", "sell_clauses")
REQUIRED_CLAUSE_KEYS = frozenset({"user_phrase", "bound_metric", "operator", "threshold"})


def validate_rule_set(candidate: dict[str, Any], allowed_metric_keys: set[str]) -> dict[str, Any]:
    """Return structured validation details for a compiled rule-set candidate."""
    problems: list[dict[str, str]] = []

    if not isinstance(candidate, dict):
        return {
            "valid": False,
            "problems": [{"path": "$", "message": "Rule set must be a dict."}],
        }

    if not isinstance(allowed_metric_keys, set) or not all(isinstance(key, str) for key in allowed_metric_keys):
        problems.append(
            {
                "path": "allowed_metric_keys",
                "message": "Allowed metric keys must be supplied as a set of strings.",
            }
        )

    total_clauses = 0
    for list_key in CLAUSE_LIST_KEYS:
        clauses = candidate.get(list_key)
        if not isinstance(clauses, list):
            problems.append({"path": list_key, "message": "Clause list must be present and must be a list."})
            continue

        total_clauses += len(clauses)
        for index, clause in enumerate(clauses):
            path = f"{list_key}[{index}]"
            problems.extend(_validate_clause(clause, allowed_metric_keys, path))

    if total_clauses == 0:
        problems.append(
            {
                "path": "$",
                "message": "Rule set must include at least one BUY or SELL clause.",
            }
        )

    return {"valid": not problems, "problems": problems}


def _validate_clause(clause: Any, allowed_metric_keys: set[str], path: str) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    if not isinstance(clause, dict):
        return [{"path": path, "message": "Clause must be a dict."}]

    missing = REQUIRED_CLAUSE_KEYS - set(clause)
    for key in sorted(missing):
        problems.append({"path": f"{path}.{key}", "message": "Required clause field is missing."})

    user_phrase = clause.get("user_phrase")
    if not isinstance(user_phrase, str) or not user_phrase.strip():
        problems.append({"path": f"{path}.user_phrase", "message": "User phrase must be a non-empty string."})

    bound_metric = clause.get("bound_metric")
    if not isinstance(bound_metric, str) or not bound_metric.strip():
        problems.append({"path": f"{path}.bound_metric", "message": "Bound metric must be a non-empty string."})
    elif bound_metric not in allowed_metric_keys:
        problems.append({"path": f"{path}.bound_metric", "message": f"Unknown metric key: {bound_metric}."})

    operator = clause.get("operator")
    if operator not in ALLOWED_OPERATORS:
        problems.append({"path": f"{path}.operator", "message": f"Unsupported operator: {operator}."})

    threshold = clause.get("threshold")
    if not _is_number(threshold):
        problems.append({"path": f"{path}.threshold", "message": "Threshold must be a numeric int or float."})

    return problems


def _is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)
