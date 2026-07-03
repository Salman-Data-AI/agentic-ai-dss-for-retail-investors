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
        "provider": "anthropic",
        "model": "claude-test",
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
            "provider": "anthropic",
            "model": "claude-test",
        },
        {
            "run_date": "2026-07-02 09:00:00",
            "ticker": "MSFT",
            "signal_type": "SELL_EVAL",
            "signal": "SELL",
            "rationale": "sell",
            "data_fetched": {"name": "Microsoft", "nested": {"ok": True}},
            "entry_price": 300.0,
            "provider": "openai",
            "model": "gpt-test",
        },
        {
            "run_date": "2026-07-02 09:00:00",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "BUY",
            "rationale": "buy",
            "data_fetched": {"name": "Apple", "rsi": 29.0},
            "entry_price": None,
            "provider": "groq",
            "model": "llama-test",
        },
    ])

    latest = store.read_latest_signals()

    assert [row["ticker"] for row in latest] == ["AAPL", "MSFT"]
    assert [row["signal_type"] for row in latest] == ["BUY_EVAL", "SELL_EVAL"]
    assert latest[0]["data_fetched"] == {"name": "Apple", "rsi": 29.0}
    assert latest[1]["data_fetched"] == {"name": "Microsoft", "nested": {"ok": True}}
    assert latest[0]["provider"] == "groq"
    assert latest[1]["model"] == "gpt-test"


def test_init_migrates_legacy_table_and_preserves_old_rows(temp_db_path):
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute("""
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_date TEXT NOT NULL,
                ticker TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal TEXT NOT NULL,
                rationale TEXT,
                data_fetched TEXT,
                entry_price REAL
            )
        """)
        conn.execute(
            """
            INSERT INTO signals
                (run_date, ticker, signal_type, signal, rationale, data_fetched, entry_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("2026-07-01 09:00:00", "AAPL", "BUY_EVAL", "HOLD", "legacy", "{}", None),
        )

    store.write_signals([{
        "run_date": "2026-07-02 09:00:00",
        "ticker": "MSFT",
        "signal_type": "BUY_EVAL",
        "signal": "BUY",
        "rationale": "new",
        "data_fetched": {"price": 300},
        "entry_price": None,
        "provider": "openai",
        "model": "gpt-test",
    }])

    with sqlite3.connect(temp_db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}

    assert {"provider", "model"}.issubset(columns)

    old_rows = store.read_filtered_signals(run_date="2026-07-01 09:00:00")
    latest = store.read_latest_signals()

    assert old_rows[0]["provider"] is None
    assert old_rows[0]["model"] is None
    assert latest[0]["provider"] == "openai"
    assert latest[0]["model"] == "gpt-test"
