"""Pure dashboard data-prep helpers."""

from __future__ import annotations


def split_signal_groups(signals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split latest-run records into watchlist BUY and portfolio SELL groups."""
    buy_signals = [s for s in signals if s["signal_type"] == "BUY_EVAL"]
    sell_signals = [s for s in signals if s["signal_type"] == "SELL_EVAL"]
    return buy_signals, sell_signals


def build_history_rows(results: list[dict]) -> list[dict]:
    """Build rows for the history dataframe without depending on Streamlit."""
    rows = []
    for s in results:
        name = s.get("data_fetched", {}).get("name") or s["ticker"]
        rows.append({
            "Run date": s["run_date"],
            "Ticker": s["ticker"],
            "Company": name,
            "Type": "BUY eval" if s["signal_type"] == "BUY_EVAL" else "SELL eval",
            "Signal": s["signal"],
            "Rationale": s.get("rationale") or "",
        })
    return rows
