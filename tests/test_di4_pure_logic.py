from __future__ import annotations

import pytest

from agent.deterministic_evaluator import BUY_EVALUATION, SELL_EVALUATION, evaluate_rule_set
from agent.rule_fingerprint import fingerprint_rule_inputs
from agent.rule_sets import validate_rule_set


ALLOWED_METRICS = {"pe_ratio", "rsi", "debt_to_equity"}


def buy_clause(**overrides):
    clause = {
        "user_phrase": "PE is under 20",
        "bound_metric": "pe_ratio",
        "operator": "<",
        "threshold": 20,
    }
    clause.update(overrides)
    return clause


def sell_clause(**overrides):
    clause = {
        "user_phrase": "RSI is over 70",
        "bound_metric": "rsi",
        "operator": ">",
        "threshold": 70,
    }
    clause.update(overrides)
    return clause


def rule_set(buy_clauses=None, sell_clauses=None):
    return {
        "buy_clauses": [] if buy_clauses is None else buy_clauses,
        "sell_clauses": [] if sell_clauses is None else sell_clauses,
    }


def test_valid_rule_set_passes_validation():
    result = validate_rule_set(
        rule_set(
            buy_clauses=[buy_clause()],
            sell_clauses=[sell_clause()],
        ),
        ALLOWED_METRICS,
    )

    assert result == {"valid": True, "problems": []}


def test_validation_rejects_unknown_metric():
    result = validate_rule_set(rule_set(buy_clauses=[buy_clause(bound_metric="unknown_metric")]), ALLOWED_METRICS)

    assert result["valid"] is False
    assert any(problem["path"] == "buy_clauses[0].bound_metric" for problem in result["problems"])


@pytest.mark.parametrize(
    "operator, threshold",
    [
        ("between", 20),
        ("<", "20"),
        ("==", True),
    ],
)
def test_validation_rejects_operator_threshold_mismatch(operator, threshold):
    result = validate_rule_set(rule_set(buy_clauses=[buy_clause(operator=operator, threshold=threshold)]), ALLOWED_METRICS)

    assert result["valid"] is False


def test_validation_rejects_empty_rule_set():
    result = validate_rule_set(rule_set(), ALLOWED_METRICS)

    assert result["valid"] is False
    assert any(problem["path"] == "$" for problem in result["problems"])


def test_fingerprint_is_deterministic_for_identical_inputs():
    first = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")
    second = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")

    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    "rule_text, tool_schema_version, prompt_version",
    [
        ("buy when PE < 21", "tools-v1", "prompt-v1"),
        ("buy when PE < 20", "tools-v2", "prompt-v1"),
        ("buy when PE < 20", "tools-v1", "prompt-v2"),
    ],
)
def test_fingerprint_changes_when_any_compile_input_changes(rule_text, tool_schema_version, prompt_version):
    baseline = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")

    assert fingerprint_rule_inputs(rule_text, tool_schema_version, prompt_version) != baseline


def test_fingerprint_has_no_model_or_provider_input():
    openai_digest = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")
    anthropic_digest = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")

    assert openai_digest == anthropic_digest


def test_fingerprint_ignores_trailing_whitespace_and_outer_blank_lines():
    compact = fingerprint_rule_inputs("buy when PE < 20", "tools-v1", "prompt-v1")
    noisy = fingerprint_rule_inputs("\n\nbuy when PE < 20   \r\n\n", "tools-v1", "prompt-v1")

    assert noisy == compact


def test_fingerprint_preserves_interior_blank_line_changes():
    one_line = fingerprint_rule_inputs("buy when PE < 20\nand RSI < 35", "tools-v1", "prompt-v1")
    with_blank = fingerprint_rule_inputs("buy when PE < 20\n\nand RSI < 35", "tools-v1", "prompt-v1")

    assert with_blank != one_line


def test_buy_evaluation_returns_buy_when_all_clauses_true():
    result = evaluate_rule_set(
        rule_set(buy_clauses=[buy_clause(), buy_clause(user_phrase="RSI is under 35", bound_metric="rsi", threshold=35)]),
        {"pe_ratio": 18, "rsi": 30},
        BUY_EVALUATION,
    )

    assert result["signal"] == "BUY"
    assert result["triggering_rule"] == "PE is under 20; RSI is under 35"
    assert [outcome["status"] for outcome in result["clause_outcomes"]] == ["true", "true"]


def test_buy_evaluation_returns_skip_with_failing_clause():
    result = evaluate_rule_set(rule_set(buy_clauses=[buy_clause(), buy_clause(bound_metric="rsi", threshold=35)]), {
        "pe_ratio": 18,
        "rsi": 50,
    }, BUY_EVALUATION)

    assert result["signal"] == "SKIP"
    assert len(result["triggering_clauses"]) == 1
    assert result["triggering_clauses"][0]["bound_metric"] == "rsi"


def test_sell_evaluation_returns_sell_when_any_clause_true_and_reports_all_firing_clauses():
    result = evaluate_rule_set(
        rule_set(sell_clauses=[
            sell_clause(),
            sell_clause(user_phrase="Debt is high", bound_metric="debt_to_equity", operator=">", threshold=2),
            sell_clause(user_phrase="PE is expensive", bound_metric="pe_ratio", operator=">", threshold=40),
        ]),
        {"rsi": 72, "debt_to_equity": 2.5, "pe_ratio": 28},
        SELL_EVALUATION,
    )

    assert result["signal"] == "SELL"
    assert result["triggering_rule"] == "RSI is over 70; Debt is high"
    assert [clause["bound_metric"] for clause in result["triggering_clauses"]] == ["rsi", "debt_to_equity"]


def test_sell_evaluation_returns_hold_when_no_clause_is_true():
    result = evaluate_rule_set(rule_set(sell_clauses=[sell_clause()]), {"rsi": 55}, SELL_EVALUATION)

    assert result["signal"] == "HOLD"
    assert result["triggering_rule"] == "No SELL clause fired."
    assert result["triggering_clauses"] == []


@pytest.mark.parametrize(
    "metrics, reason",
    [
        ({}, "Metric is missing."),
        ({"pe_ratio": {"error": "provider failed"}}, "Metric value is an error dict."),
        ({"pe_ratio": "18"}, "Metric value is not numeric."),
    ],
)
def test_missing_or_unevaluable_metric_returns_error(metrics, reason):
    result = evaluate_rule_set(rule_set(buy_clauses=[buy_clause()]), metrics, BUY_EVALUATION)

    assert result["signal"] == "ERROR"
    assert result["error"] == "One or more clauses could not be evaluated."
    assert result["clause_outcomes"][0]["reason"] == reason
