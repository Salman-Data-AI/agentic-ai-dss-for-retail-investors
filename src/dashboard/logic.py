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
            "Duration": _format_duration(s.get("run_elapsed_seconds")),
            "Ticker": s["ticker"],
            "Company": name,
            "Type": "BUY eval" if s["signal_type"] == "BUY_EVAL" else "SELL eval",
            "Signal": s["signal"],
            "Provider": s.get("provider") or "",
            "Model": s.get("model") or "",
            "Rationale": s.get("rationale") or "",
        })
    return rows


def build_rule_clause_rows(rule_set: dict | None, clause_key: str) -> list[dict]:
    """Build Streamlit-friendly rows for compiled rule clauses."""
    if not isinstance(rule_set, dict):
        return []
    clauses = rule_set.get(clause_key)
    if not isinstance(clauses, list):
        return []

    rows = []
    for index, clause in enumerate(clauses, start=1):
        if not isinstance(clause, dict):
            continue
        operator = clause.get("operator", "")
        threshold = clause.get("threshold", "")
        rows.append({
            "#": index,
            "User phrase": clause.get("user_phrase", ""),
            "Bound metric": clause.get("bound_metric", ""),
            "Enforced check": f"{operator} {threshold}".strip(),
        })
    return rows


def describe_rule_gate(settings: dict, active_fingerprint: str) -> dict:
    """Return the current dashboard approval/gate state for edited rule text."""
    saved_fingerprint = settings.get("compiled_rule_fingerprint") or ""
    saved_rule_set = settings.get("compiled_rule_set")
    persisted_state = settings.get("rule_approval_state") or "unvalidated"
    is_current = saved_fingerprint == active_fingerprint and isinstance(saved_rule_set, dict)
    is_approved = is_current and persisted_state == "approved"
    is_compiled = is_current and persisted_state == "compiled"

    if is_approved:
        message = "Validated and approved - ready to run."
        state = "approved"
    elif is_compiled:
        message = "Validated - review thresholds and approve before running."
        state = "compiled"
    elif saved_fingerprint and saved_fingerprint != active_fingerprint:
        message = "Rules changed - validate before running."
        state = "stale"
    elif persisted_state == "invalidated":
        message = "Validation failed - fix the highlighted rule clauses and validate again."
        state = "invalidated"
    else:
        message = "Rules are unvalidated - validate before running."
        state = "unvalidated"

    return {
        "state": state,
        "message": message,
        "run_enabled": is_approved,
        "approval_enabled": is_compiled,
        "current_rule_set": saved_rule_set if is_current else None,
    }


def escape_markdown_math(text: str) -> str:
    """Escape dollar signs so Streamlit does not render prices as LaTeX."""
    return text.replace("$", r"\$")


def format_metric_value(value) -> str:
    """Render a data-used value compactly so metric cards don't truncate.

    Floats are rounded to two decimals with trailing zeros trimmed; bools,
    ints, and other types fall back to their plain string form.
    """
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        rounded = round(value, 2)
        text = f"{rounded:.2f}".rstrip("0").rstrip(".")
        return text or "0"
    return str(value)


def chunk_metrics(data: dict, per_row: int = 4) -> list[list[tuple[str, str]]]:
    """Group data-used items into rows of at most ``per_row`` metric cards.

    Each item becomes a ``(label, formatted_value)`` pair. Wrapping keeps
    columns wide enough that labels and values stay readable.
    """
    if per_row < 1:
        raise ValueError("per_row must be at least 1")
    items = [
        (key.replace("_", " ").title(), format_metric_value(value))
        for key, value in data.items()
    ]
    return [items[i:i + per_row] for i in range(0, len(items), per_row)]


def _format_duration(seconds) -> str:
    if seconds is None:
        return ""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return ""
    return f"{value:.1f}s"
