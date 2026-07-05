from __future__ import annotations

import importlib.util

from dashboard.logic import build_history_rows, escape_markdown_math, split_signal_groups


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


def test_streamlit_apptest_import_path_is_available():
    assert importlib.util.find_spec("streamlit.testing.v1") is not None
