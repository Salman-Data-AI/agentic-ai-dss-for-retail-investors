from __future__ import annotations

import importlib.util

import pytest

from dashboard.logic import (
    build_history_rows,
    build_rule_clause_rows,
    chunk_metrics,
    describe_rule_gate,
    escape_markdown_math,
    format_metric_value,
    split_signal_groups,
)


def test_split_signal_groups():
    signals = [
        {"ticker": "AAPL", "signal_type": "BUY_EVAL"},
        {"ticker": "JPM", "signal_type": "SELL_EVAL"},
        {"ticker": "MSFT", "signal_type": "BUY_EVAL"},
    ]

    buy, sell = split_signal_groups(signals)

    assert [s["ticker"] for s in buy] == ["AAPL", "MSFT"]
    assert [s["ticker"] for s in sell] == ["JPM"]


def test_split_signal_groups_normalizes_legacy_signals_for_display():
    signals = [
        {
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "SELL",
            "rationale": "legacy watchlist sell",
        },
        {
            "ticker": "JPM",
            "signal_type": "SELL_EVAL",
            "signal": "BUY",
            "rationale": "legacy portfolio buy",
        },
    ]

    buy, sell = split_signal_groups(signals)

    assert buy[0]["signal"] == "SKIP"
    assert "Legacy stored signal 'SELL' is shown as 'SKIP'" in buy[0]["rationale"]
    assert sell[0]["signal"] == "HOLD"
    assert "Legacy stored signal 'BUY' is shown as 'HOLD'" in sell[0]["rationale"]


def test_build_history_rows():
    rows = build_history_rows([
        {
            "run_date": "2026-07-02",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "BUY",
            "rationale": None,
            "data_fetched": {"name": "Apple Inc."},
            "provider": "anthropic",
            "model": "claude-test",
            "run_elapsed_seconds": 12.345,
        },
        {
            "run_date": "2026-07-02",
            "ticker": "JPM",
            "signal_type": "SELL_EVAL",
            "signal": "HOLD",
            "rationale": "steady",
            "data_fetched": {},
            "provider": None,
            "model": None,
            "run_elapsed_seconds": None,
        },
    ])

    assert rows == [
        {
            "Run date": "2026-07-02",
            "Duration": "12.3s",
            "Ticker": "AAPL",
            "Company": "Apple Inc.",
            "Type": "BUY eval",
            "Signal": "BUY",
            "Provider": "anthropic",
            "Model": "claude-test",
            "Rationale": "",
        },
        {
            "Run date": "2026-07-02",
            "Duration": "",
            "Ticker": "JPM",
            "Company": "JPM",
            "Type": "SELL eval",
            "Signal": "HOLD",
            "Provider": "",
            "Model": "",
            "Rationale": "steady",
        },
    ]


def test_build_history_rows_normalizes_legacy_watchlist_sell():
    rows = build_history_rows([
        {
            "run_date": "2026-07-05",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "SELL",
            "rationale": "legacy rationale",
            "data_fetched": {"name": "Apple Inc."},
            "provider": "openai",
            "model": "gpt-test",
        },
    ])

    assert rows[0]["Signal"] == "SKIP"
    assert "Legacy stored signal 'SELL' is shown as 'SKIP'" in rows[0]["Rationale"]


def test_escape_markdown_math_preserves_dollar_prices_as_text():
    text = "Price $359.91 is far above the $251.72 cutoff."

    assert escape_markdown_math(text) == "Price \\$359.91 is far above the \\$251.72 cutoff."


def test_format_metric_value_rounds_and_trims_floats():
    assert format_metric_value(33.71428571) == "33.71"
    assert format_metric_value(112.0) == "112"
    assert format_metric_value(-18.70) == "-18.7"
    assert format_metric_value(0.0) == "0"


def test_format_metric_value_handles_non_floats():
    assert format_metric_value(None) == "-"
    assert format_metric_value(None) not in {"0", "None", ""}
    assert format_metric_value(True) == "True"
    assert format_metric_value(42) == "42"
    assert format_metric_value("BUY") == "BUY"


def test_chunk_metrics_wraps_and_formats():
    data = {
        "rsi_14": 73.855,
        "price_above_52w": 33.71428,
        "pe_ratio": 14.64,
        "eps_ttm": 4.37,
        "missing_metric": None,
        "volume_vs_average": -18.72,
    }

    rows = chunk_metrics(data, per_row=4)

    assert [len(row) for row in rows] == [4, 2]
    assert rows[0][0] == ("Rsi 14", "73.86")
    assert rows[0][1] == ("Price Above 52W", "33.71")
    assert rows[1][0] == ("Missing Metric", "-")
    assert rows[1][1] == ("Volume Vs Average", "-18.72")


def test_chunk_metrics_rejects_invalid_per_row():
    with pytest.raises(ValueError):
        chunk_metrics({"a": 1}, per_row=0)


def test_build_rule_clause_rows_surfaces_thresholds():
    rule_set = {
        "buy_clauses": [
            {
                "user_phrase": "PE ratio is below 20",
                "bound_metric": "pe_ratio",
                "operator": "<",
                "threshold": 20,
            },
        ],
        "sell_clauses": [],
    }

    rows = build_rule_clause_rows(rule_set, "buy_clauses")

    assert rows == [
        {
            "#": 1,
            "User phrase": "PE ratio is below 20",
            "Bound metric": "pe_ratio",
            "Enforced check": "< 20",
        },
    ]


def test_describe_rule_gate_blocks_unvalidated_rules():
    gate = describe_rule_gate(
        {
            "compiled_rule_fingerprint": "",
            "compiled_rule_set": None,
            "rule_approval_state": "unvalidated",
        },
        "current",
    )

    assert gate["state"] == "unvalidated"
    assert gate["run_enabled"] is False
    assert gate["approval_enabled"] is False
    assert "validate before running" in gate["message"]


def test_describe_rule_gate_allows_only_current_approved_rules():
    settings = {
        "compiled_rule_fingerprint": "abc",
        "compiled_rule_set": {"buy_clauses": [], "sell_clauses": []},
        "rule_approval_state": "approved",
    }

    approved_gate = describe_rule_gate(settings, "abc")
    stale_gate = describe_rule_gate(settings, "changed")

    assert approved_gate["run_enabled"] is True
    assert approved_gate["state"] == "approved"
    assert stale_gate["run_enabled"] is False
    assert stale_gate["state"] == "stale"


def test_describe_rule_gate_enables_approval_for_current_compiled_rules():
    gate = describe_rule_gate(
        {
            "compiled_rule_fingerprint": "abc",
            "compiled_rule_set": {"buy_clauses": [], "sell_clauses": []},
            "rule_approval_state": "compiled",
        },
        "abc",
    )

    assert gate["state"] == "compiled"
    assert gate["approval_enabled"] is True
    assert gate["run_enabled"] is False


def test_streamlit_apptest_import_path_is_available():
    assert importlib.util.find_spec("streamlit.testing.v1") is not None
