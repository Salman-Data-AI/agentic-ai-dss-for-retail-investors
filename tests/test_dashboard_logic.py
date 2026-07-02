from __future__ import annotations

import importlib.util

from dashboard.logic import build_history_rows, split_signal_groups


def test_split_signal_groups():
    signals = [
        {"ticker": "AAPL", "signal_type": "BUY_EVAL"},
        {"ticker": "JPM", "signal_type": "SELL_EVAL"},
        {"ticker": "MSFT", "signal_type": "BUY_EVAL"},
    ]

    buy, sell = split_signal_groups(signals)

    assert [s["ticker"] for s in buy] == ["AAPL", "MSFT"]
    assert [s["ticker"] for s in sell] == ["JPM"]


def test_build_history_rows():
    rows = build_history_rows([
        {
            "run_date": "2026-07-02",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "BUY",
            "rationale": None,
            "data_fetched": {"name": "Apple Inc."},
        },
        {
            "run_date": "2026-07-02",
            "ticker": "JPM",
            "signal_type": "SELL_EVAL",
            "signal": "HOLD",
            "rationale": "steady",
            "data_fetched": {},
        },
    ])

    assert rows == [
        {
            "Run date": "2026-07-02",
            "Ticker": "AAPL",
            "Company": "Apple Inc.",
            "Type": "BUY eval",
            "Signal": "BUY",
            "Rationale": "",
        },
        {
            "Run date": "2026-07-02",
            "Ticker": "JPM",
            "Company": "JPM",
            "Type": "SELL eval",
            "Signal": "HOLD",
            "Rationale": "steady",
        },
    ]


def test_streamlit_apptest_import_path_is_available():
    assert importlib.util.find_spec("streamlit.testing.v1") is not None
