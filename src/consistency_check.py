"""Developer tool for measuring signal stability on identical fetched inputs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

from dotenv import load_dotenv

import config
from agent.agent import _TOOL_DISPATCH, evaluate_signals_from_data_batch
from agent.tool_planner import plan_tools_for_rules
from paths import executable_env_path, user_env_path
from settings import load_settings

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)


def _fetch_once(tickers: list[str], rules: str) -> list[dict]:
    plan = plan_tools_for_rules(rules)
    items = []
    for ticker in tickers:
        fetched_data = {}
        for planned_tool in plan:
            fn = _TOOL_DISPATCH.get(planned_tool.name)
            if not fn:
                fetched_data[planned_tool.name] = {"error": f"Unknown tool: {planned_tool.name}"}
                continue
            fetched_data[planned_tool.name] = fn(ticker=ticker, **planned_tool.args)
        items.append({"ticker": ticker, "fetched_data": fetched_data})
    return items


def measure_consistency(tickers: list[str], runs: int, rules: str, model: str) -> dict:
    items = _fetch_once(tickers, rules)
    evaluations = [
        evaluate_signals_from_data_batch(
            items,
            rules=rules,
            model=model,
            evaluation_type="BUY_EVAL",
        )
        for _ in range(runs)
    ]
    by_ticker = defaultdict(list)
    for run_index, rows in enumerate(evaluations, start=1):
        for row in rows:
            by_ticker[row["ticker"]].append(
                {
                    "run": run_index,
                    "signal": row.get("signal"),
                    "rationale": row.get("rationale"),
                    "triggering_rule": row.get("triggering_rule"),
                }
            )

    per_ticker = {}
    disagreements = {}
    identical_tickers = 0
    for ticker, rows in by_ticker.items():
        signals = [row["signal"] for row in rows]
        majority_count = max(signals.count(signal) for signal in set(signals))
        agreement_rate = majority_count / len(signals) if signals else 0.0
        per_ticker[ticker] = {
            "agreement_rate": agreement_rate,
            "signals": signals,
        }
        if len(set(signals)) == 1:
            identical_tickers += 1
        else:
            disagreements[ticker] = rows

    return {
        "runs": runs,
        "tickers": tickers,
        "per_ticker": per_ticker,
        "identical_ticker_count": identical_tickers,
        "disagreements": disagreements,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure signal stability on identical fetched inputs.")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--tickers", default="AAPL,MSFT")
    args = parser.parse_args()
    if args.runs < 2:
        raise SystemExit("--runs must be at least 2")

    settings = load_settings()
    tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    result = measure_consistency(
        tickers=tickers,
        runs=args.runs,
        rules=settings.get("buy_rules") or config.BUY_RULES,
        model=settings.get("model") or config.MODEL,
    )
    comparable_runs = len(tickers) * args.runs
    identical_runs = result["identical_ticker_count"] * args.runs
    print(
        f"identical inputs produced identical signals in {identical_runs} of "
        f"{comparable_runs} ticker-runs; disagreements: "
        f"{json.dumps(result['disagreements'], indent=2, sort_keys=True)}"
    )


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    main()
