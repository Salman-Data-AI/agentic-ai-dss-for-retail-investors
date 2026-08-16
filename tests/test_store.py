from __future__ import annotations

import sqlite3

from database import store


def test_write_signals_initializes_table_and_round_trips(temp_db_path):
    signals = [
        {
            "run_date": "2026-07-02 10:00:00",
            "ticker": "AAPL",
            "signal_type": "BUY_EVAL",
            "signal": "BUY",
            "rationale": "Looks attractive.",
            "data_fetched": {"name": "Apple Inc.", "rsi": 31.2},
            "entry_price": None,
            "provider": "anthropic",
            "model": "claude-test",
            "rules_applied": "Buy when RSI is below 35.",
            "triggering_rule": "RSI is below 35.",
            "temperature": 0.0,
            "run_elapsed_seconds": 12.34,
        }
    ]

    store.write_signals(signals)

    with sqlite3.connect(temp_db_path) as conn:
        table = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'signals'").fetchone()
    assert table == ("signals",)
    assert store.read_latest_signals() == signals


def test_write_signals_preserves_null_metric_values_in_data_fetched(temp_db_path):
    signal = {
        "run_date": "2026-07-02 10:00:00",
        "ticker": "AAPL",
        "signal_type": "BUY_EVAL",
        "signal": "ERROR",
        "rationale": "PE missing.",
        "data_fetched": {"get_key_metrics": {"pe_ratio": None, "eps_ttm": None}},
        "entry_price": None,
        "provider": "anthropic",
        "model": "claude-test",
        "rules_applied": "Buy when PE is below 20.",
        "triggering_rule": "",
        "temperature": 0.0,
        "run_elapsed_seconds": 1.0,
    }

    store.write_signals([signal])

    round_tripped = store.read_latest_signals()[0]["data_fetched"]
    assert round_tripped["get_key_metrics"]["pe_ratio"] is None
    assert round_tripped["get_key_metrics"]["eps_ttm"] is None
    assert round_tripped["get_key_metrics"]["pe_ratio"] != 0
    assert round_tripped["get_key_metrics"]["eps_ttm"] != 0


def test_read_latest_signals_returns_only_latest_run_ordered_by_type_then_ticker(temp_db_path):
    store.write_signals(
        [
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
                "rules_applied": "old rules",
                "triggering_rule": "old rule",
                "temperature": None,
                "run_elapsed_seconds": 5.0,
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
                "rules_applied": "sell rules",
                "triggering_rule": "profit target",
                "temperature": 0.2,
                "run_elapsed_seconds": 7.5,
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
                "rules_applied": "buy rules",
                "triggering_rule": "oversold RSI",
                "temperature": None,
                "run_elapsed_seconds": 7.5,
            },
        ]
    )

    latest = store.read_latest_signals()

    assert [row["ticker"] for row in latest] == ["AAPL", "MSFT"]
    assert [row["signal_type"] for row in latest] == ["BUY_EVAL", "SELL_EVAL"]
    assert latest[0]["data_fetched"] == {"name": "Apple", "rsi": 29.0}
    assert latest[1]["data_fetched"] == {"name": "Microsoft", "nested": {"ok": True}}
    assert latest[0]["provider"] == "groq"
    assert latest[1]["model"] == "gpt-test"
    assert latest[0]["rules_applied"] == "buy rules"
    assert latest[1]["triggering_rule"] == "profit target"
    assert latest[0]["temperature"] is None
    assert latest[1]["temperature"] == 0.2
    assert latest[0]["run_elapsed_seconds"] == 7.5


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

    store.write_signals(
        [
            {
                "run_date": "2026-07-02 09:00:00",
                "ticker": "MSFT",
                "signal_type": "BUY_EVAL",
                "signal": "BUY",
                "rationale": "new",
                "data_fetched": {"price": 300},
                "entry_price": None,
                "provider": "openai",
                "model": "gpt-test",
                "rules_applied": "new rules",
                "triggering_rule": "new rule",
                "temperature": 0.0,
                "run_elapsed_seconds": 3.21,
            }
        ]
    )

    with sqlite3.connect(temp_db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}

    assert {"provider", "model", "rules_applied", "triggering_rule", "temperature", "run_elapsed_seconds"}.issubset(
        columns
    )

    old_rows = store.read_filtered_signals(run_date="2026-07-01 09:00:00")
    latest = store.read_latest_signals()

    assert old_rows[0]["provider"] is None
    assert old_rows[0]["model"] is None
    assert old_rows[0]["rules_applied"] is None
    assert old_rows[0]["triggering_rule"] is None
    assert old_rows[0]["temperature"] is None
    assert old_rows[0]["run_elapsed_seconds"] is None
    assert latest[0]["provider"] == "openai"
    assert latest[0]["model"] == "gpt-test"
    assert latest[0]["rules_applied"] == "new rules"
    assert latest[0]["triggering_rule"] == "new rule"
    assert latest[0]["temperature"] == 0.0
    assert latest[0]["run_elapsed_seconds"] == 3.21
