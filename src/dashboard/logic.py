"""Pure dashboard data-prep helpers."""

from __future__ import annotations


_LEGACY_SIGNAL_MAP = {
    "BUY_EVAL": {
        "BUY": "BUY",
        "SKIP": "SKIP",
        "HOLD": "SKIP",
        "SELL": "SKIP",
        "ERROR": "ERROR",
    },
    "SELL_EVAL": {
        "SELL": "SELL",
        "HOLD": "HOLD",
        "BUY": "HOLD",
        "SKIP": "HOLD",
        "ERROR": "ERROR",
    },
}


def normalize_signal_for_display(signal: dict) -> dict:
    """Return a display-safe copy using the current signal vocabulary."""
    signal_type = signal.get("signal_type")
    raw_signal = signal.get("signal")
    mapped_signal = _LEGACY_SIGNAL_MAP.get(signal_type, {}).get(raw_signal)

    if mapped_signal is None:
        normalized = dict(signal)
        normalized["signal"] = "ERROR"
        normalized["rationale"] = _prefix_rationale(
            signal,
            f"Stored signal {raw_signal!r} is not valid for {signal_type}.",
        )
        return normalized

    if mapped_signal == raw_signal:
        return signal

    normalized = dict(signal)
    normalized["signal"] = mapped_signal
    normalized["rationale"] = _prefix_rationale(
        signal,
        f"Legacy stored signal {raw_signal!r} is shown as {mapped_signal!r} for {signal_type}.",
    )
    return normalized


def _prefix_rationale(signal: dict, prefix: str) -> str:
    rationale = signal.get("rationale") or ""
    return f"{prefix} {rationale}".strip()


def split_signal_groups(signals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split latest-run records into watchlist BUY and portfolio SELL groups."""
    normalized = [normalize_signal_for_display(s) for s in signals]
    buy_signals = [s for s in normalized if s["signal_type"] == "BUY_EVAL"]
    sell_signals = [s for s in normalized if s["signal_type"] == "SELL_EVAL"]
    return buy_signals, sell_signals


def build_history_rows(results: list[dict]) -> list[dict]:
    """Build rows for the history dataframe without depending on Streamlit."""
    rows = []
    for s in [normalize_signal_for_display(signal) for signal in results]:
        name = s.get("data_fetched", {}).get("name") or s["ticker"]
        rows.append({
            "Run date": s["run_date"],
            "Ticker": s["ticker"],
            "Company": name,
            "Type": "BUY eval" if s["signal_type"] == "BUY_EVAL" else "SELL eval",
            "Signal": s["signal"],
            "Provider": s.get("provider") or "",
            "Model": s.get("model") or "",
            "Rationale": s.get("rationale") or "",
        })
    return rows
