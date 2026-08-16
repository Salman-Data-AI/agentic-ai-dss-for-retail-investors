"""Fetch a one-time metric snapshot for the static dashboard reference tab."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from agent import tools  # noqa: E402


def _call(name: str, *args, **kwargs) -> dict:
    func = getattr(tools, name)
    try:
        result = func(*args, **kwargs)
    except Exception as exc:
        result = {"error": f"{name} failed unexpectedly: {exc}"}
    return result if isinstance(result, dict) else {"value": result}


def fetch_snapshot(ticker: str) -> dict:
    ticker = ticker.upper().strip()
    before = tools.get_fmp_request_count()
    calls = {
        "get_quote": _call("get_quote", ticker),
        "get_rsi": _call("get_rsi", ticker),
        "get_sma": _call("get_sma", ticker),
        "get_key_metrics": _call("get_key_metrics", ticker),
        "get_valuation_ratios": _call("get_valuation_ratios", ticker),
        "get_financial_health": _call("get_financial_health", ticker),
        "get_income_statement": _call("get_income_statement", ticker),
        "get_balance_sheet": _call("get_balance_sheet", ticker),
        "get_cash_flow": _call("get_cash_flow", ticker),
        "get_performance": _call("get_performance", ticker),
        "get_profile": _call("get_profile", ticker),
        "get_technical_indicator_ema": _call("get_technical_indicator", ticker, "ema", period=20),
        "get_technical_indicator_adx": _call("get_technical_indicator", ticker, "adx", period=14),
        "get_technical_indicator_williams": _call("get_technical_indicator", ticker, "williams", period=14),
        "get_technical_indicator_standarddeviation": _call(
            "get_technical_indicator",
            ticker,
            "standarddeviation",
            period=14,
        ),
        "get_price_target": _call("get_price_target", ticker),
        "get_analyst_rating": _call("get_analyst_rating", ticker),
        "get_analyst_estimates": _call("get_analyst_estimates", ticker),
        "get_earnings": _call("get_earnings", ticker),
    }
    after = tools.get_fmp_request_count()
    return {
        "ticker": ticker,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fmp_requests_used": after - before,
        "fmp_request_count_before": before,
        "fmp_request_count_after": after,
        "calls": calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker", nargs="?", default="AAPL")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "docs" / "misc" / "metrics_reference_snapshot.json"),
    )
    args = parser.parse_args()

    snapshot = fetch_snapshot(args.ticker)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(
        json.dumps(
            {
                "ticker": snapshot["ticker"],
                "fetched_at_utc": snapshot["fetched_at_utc"],
                "fmp_requests_used": snapshot["fmp_requests_used"],
                "output": os.fspath(output_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
