from __future__ import annotations

import sqlite3

from database import store


def test_write_signals_initializes_table_and_round_trips(temp_db_path):
    signals = [{
        "run_date": "2026-07-02 10:00:00",
        "ticker": "AAPL",
        "signal_type": "BUY_EVAL",
        "signal": "BUY",
        "rationale": "Looks attractive.",
        "data_fetched": {"name": "Apple Inc.", "rsi": 31.2},
        "entry_price": None,
    }]

    store.write_signals(signals)

    with sqlite3.connect(temp_db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'signals'"
        ).fetchone()
    assert table == ("signals",)
    assert store.read_latest_signals() == signals


def test_read_latest_signals_returns_only_latest_run_ordered_by_type_then_ticker(temp_db_path):
    store.write_signals([
        {
            "run_date": "2026-07-01 09:00:00",
            "ticker": "ZZZ",
            "signal_type": "BUY_EVAL",
            "signal": "HOLD",
            "rationale": "old",
            "data_fetched": {"old": True},
            "entry_price": None,
        },
        {
            "run_date": "2026-07-02 09:00:00",
            "ticker": "MSFT",
            "signal_type": "SELL_EVAL",
            "signal": "SELL",
            "rationale": "sell",
            "data_fetched": {"name": "Microsoft", "nested": {"ok": True}},
            "entry_price": 300.0,
        },
        {
            "run_date": "2026-07-02 09:00:00",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "BUY",
            "rationale": "buy",
            "data_fetched": {"name": "Apple", "rsi": 29.0},
            "entry_price": None,
        },
    ])

    latest = store.read_latest_signals()

    assert [row["ticker"] for row in latest] == ["AAPL", "MSFT"]
    assert [row["signal_type"] for row in latest] == ["BUY_EVAL", "SELL_EVAL"]
    assert latest[0]["data_fetched"] == {"name": "Apple", "rsi": 29.0}
    assert latest[1]["data_fetched"] == {"name": "Microsoft", "nested": {"ok": True}}
