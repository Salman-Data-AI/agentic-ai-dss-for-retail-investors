"""
SQLite store — audit log only.
The agent never reads from here; it writes results after each run.
The dashboard reads the latest run for display and filtered sets for history.
"""

import json
import os
import sqlite3

from paths import signals_db_path

_DB_PATH = signals_db_path()


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
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
            entry_price REAL,
            provider    TEXT,
            model       TEXT,
            rules_applied TEXT,
            triggering_rule TEXT,
            temperature REAL,
            run_elapsed_seconds REAL
        )
    """)
    _ensure_column(conn, "provider", "TEXT")
    _ensure_column(conn, "model", "TEXT")
    _ensure_column(conn, "rules_applied", "TEXT")
    _ensure_column(conn, "triggering_rule", "TEXT")
    _ensure_column(conn, "temperature", "REAL")
    _ensure_column(conn, "run_elapsed_seconds", "REAL")
    conn.commit()


def _ensure_column(conn: sqlite3.Connection, column: str, column_type: str) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE signals ADD COLUMN {column} {column_type}")


def write_signals(signals: list[dict]) -> None:
    """Persist a list of signal dicts to the database."""
    conn = _connect()
    _init(conn)
    conn.executemany(
        """
        INSERT INTO signals
            (run_date, ticker, signal_type, signal, rationale, data_fetched,
            entry_price, provider, model, rules_applied, triggering_rule,
            temperature, run_elapsed_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                s.get("provider"),
                s.get("model"),
                s.get("rules_applied"),
                s.get("triggering_rule"),
                s.get("temperature"),
                s.get("run_elapsed_seconds"),
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
        SELECT run_date, ticker, signal_type, signal, rationale,
        data_fetched, entry_price, provider, model, rules_applied,
        triggering_rule, temperature, run_elapsed_seconds
        FROM signals
        WHERE run_date = (SELECT MAX(run_date) FROM signals)
        ORDER BY signal_type, ticker
        """
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def read_filtered_signals(
    run_date: str | None = None,
    signal_type: str | None = None,
    ticker: str | None = None,
) -> list[dict]:
    """
    Return signals matching the provided filters.
    At least one filter must be supplied — never fetches unbounded set.
    """
    if not any([run_date, signal_type, ticker]):
        return []

    clauses = []
    params = []

    if run_date:
        clauses.append("run_date = ?")
        params.append(run_date)
    if signal_type:
        clauses.append("signal_type = ?")
        params.append(signal_type)
    if ticker:
        clauses.append("ticker = ?")
        params.append(ticker.upper().strip())

    where = " AND ".join(clauses)
    conn = _connect()
    _init(conn)
    rows = conn.execute(
        f"""
        SELECT run_date, ticker, signal_type, signal, rationale,
        data_fetched, entry_price, provider, model, rules_applied,
        triggering_rule, temperature, run_elapsed_seconds
        FROM signals
        WHERE {where}
        ORDER BY run_date DESC, signal_type, ticker
        """,
        params,
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def read_run_dates() -> list[str]:
    """Return a distinct list of all run timestamps, newest first."""
    conn = _connect()
    _init(conn)
    rows = conn.execute("SELECT DISTINCT run_date FROM signals ORDER BY run_date DESC").fetchall()
    conn.close()
    return [r[0] for r in rows]


def read_tickers() -> list[str]:
    """Return a distinct sorted list of all tickers in the database."""
    conn = _connect()
    _init(conn)
    rows = conn.execute("SELECT DISTINCT ticker FROM signals ORDER BY ticker ASC").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _row_to_dict(r: tuple) -> dict:
    return {
        "run_date": r[0],
        "ticker": r[1],
        "signal_type": r[2],
        "signal": r[3],
        "rationale": r[4],
        "data_fetched": json.loads(r[5]) if r[5] else {},
        "entry_price": r[6],
        "provider": r[7],
        "model": r[8],
        "rules_applied": r[9],
        "triggering_rule": r[10],
        "temperature": r[11],
        "run_elapsed_seconds": r[12],
    }
