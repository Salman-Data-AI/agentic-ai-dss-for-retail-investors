"""
SQLite store — audit log only.
The agent never reads from here; it writes results after each run.
The dashboard reads the latest run for display.
"""

import os
import json
import sqlite3

_DB_PATH = os.path.join(os.path.dirname(__file__), "signals.db")


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(_DB_PATH)


def _init(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date    TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            signal      TEXT NOT NULL,
            rationale   TEXT,
            data_fetched TEXT,
            entry_price REAL
        )
    """)
    conn.commit()


def write_signals(signals: list[dict]) -> None:
    """Persist a list of signal dicts to the database."""
    conn = _connect()
    _init(conn)
    conn.executemany(
        """
        INSERT INTO signals
            (run_date, ticker, signal_type, signal, rationale, data_fetched, entry_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                s.get("run_date"),
                s.get("ticker"),
                s.get("signal_type"),
                s.get("signal"),
                s.get("rationale"),
                json.dumps(s.get("data_fetched", {})),
                s.get("entry_price"),
            )
            for s in signals
        ],
    )
    conn.commit()
    conn.close()


def read_latest_signals() -> list[dict]:
    """Return all signals from the most recent run, ordered by type then ticker."""
    conn = _connect()
    _init(conn)
    rows = conn.execute(
        """
        SELECT run_date, ticker, signal_type, signal, rationale, data_fetched, entry_price
        FROM signals
        WHERE run_date = (SELECT MAX(run_date) FROM signals)
        ORDER BY signal_type, ticker
        """
    ).fetchall()
    conn.close()
    return [
        {
            "run_date": r[0],
            "ticker": r[1],
            "signal_type": r[2],
            "signal": r[3],
            "rationale": r[4],
            "data_fetched": json.loads(r[5]) if r[5] else {},
            "entry_price": r[6],
        }
        for r in rows
    ]
