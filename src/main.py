"""
Entry point for the DSS agent pipeline.
Run this file to evaluate your watchlist and portfolio against your rules.
Results are written to db/signals.db and displayed in the dashboard.

Usage:
    python src/main.py
    streamlit run src/dashboard/app.py
"""

import os
import sys
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from time import perf_counter

import pandas as pd
from dotenv import load_dotenv
from paths import (
    analysis_summary_path,
    executable_env_path,
    seed_user_csv_defaults,
    user_data_dir,
    user_env_path,
)

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)

# Allow running from project root or from src/
sys.path.insert(0, os.path.dirname(__file__))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from settings import clean_portfolio_frame, clean_watchlist_frame, load_settings
from agent.agent import _TOOL_DISPATCH, evaluate_signals_from_data_batch
from agent.tool_planner import PlannedTool, plan_tools_with_diagnostics
from agent.tools import get_fmp_request_count, get_fmp_run_request_count
from database import write_signals

_USER_DATA_DIR = user_data_dir()
_DATA_DIR = _USER_DATA_DIR
MAX_WORKERS = 3


def _ensure_data_files() -> None:
    if os.path.abspath(_DATA_DIR) == os.path.abspath(_USER_DATA_DIR):
        seed_user_csv_defaults()


def _load_watchlist() -> list[str]:
    _ensure_data_files()
    path = os.path.join(_DATA_DIR, "watchlist.csv")
    df = pd.read_csv(path)
    return clean_watchlist_frame(df)["ticker"].tolist()


def _load_portfolio() -> list[dict]:
    _ensure_data_files()
    path = os.path.join(_DATA_DIR, "portfolio.csv")
    df = pd.read_csv(path)
    return clean_portfolio_frame(df).to_dict(orient="records")


def _ensure_name(signal: dict, ticker: str, fetched_data: dict | None = None) -> None:
    if signal["data_fetched"].get("name"):
        return
    quote = (fetched_data or {}).get("get_quote") or {}
    signal["data_fetched"]["name"] = quote.get("name", ticker)


def _execute_tool_plan(ticker: str, plan: list[PlannedTool]) -> dict:
    fetched = {}
    for planned_tool in plan:
        fn = _TOOL_DISPATCH.get(planned_tool.name)
        if not fn:
            fetched[planned_tool.name] = {"error": f"Unknown tool: {planned_tool.name}"}
            continue
        fetched[planned_tool.name] = fn(ticker=ticker, **planned_tool.args)
    return fetched


def _fetch_job(job: dict) -> dict:
    started = perf_counter()
    fetched_data = _execute_tool_plan(job["ticker"], job["tool_plan"])
    if job.get("context_data"):
        fetched_data.update(job["context_data"])
    return {
        "index": job["index"],
        "elapsed": perf_counter() - started,
        "ticker": job["ticker"],
        "signal_type": job["metadata"]["signal_type"],
        "fetched_data": fetched_data,
        "job": job,
    }


def _fetch_jobs(jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    if not jobs:
        return [], []
    fetched_results = [None] * len(jobs)
    timings = [None] * len(jobs)
    workers = min(MAX_WORKERS, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_job = {
            executor.submit(_fetch_job, job): job
            for job in jobs
        }
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            result = future.result()
            fetched_results[result["index"]] = result
            timings[result["index"]] = {
                "ticker": result["ticker"],
                "signal_type": result["signal_type"],
                "fetch_elapsed_seconds": round(result["elapsed"], 3),
            }
            print(
                f"  {job['ticker']:<8} fetched "
                f"({result['elapsed']:.1f}s)",
                flush=True,
            )
    return fetched_results, timings


def _evaluate_group(fetched_jobs: list[dict], *, rules: str, model: str, evaluation_type: str) -> tuple[list[dict], float]:
    if not fetched_jobs:
        return [], 0.0
    started = perf_counter()
    signals = evaluate_signals_from_data_batch(
        [
            {
                "ticker": item["ticker"],
                "fetched_data": item["fetched_data"],
            }
            for item in fetched_jobs
        ],
        rules=rules,
        model=model,
        evaluation_type=evaluation_type,
    )
    elapsed = perf_counter() - started
    for signal, item in zip(signals, fetched_jobs):
        _ensure_name(signal, item["ticker"], item["fetched_data"])
        signal.update(item["job"]["metadata"])
    return signals, elapsed


def _format_plan(plan: list[PlannedTool]) -> str:
    return ", ".join(
        tool.name if not tool.args else f"{tool.name}{tool.args}"
        for tool in plan
    )


def _write_run_summary(summary: dict) -> None:
    path = analysis_summary_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)


def read_latest_run_summary() -> dict:
    try:
        with open(analysis_summary_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def run_analysis() -> dict:
    started = perf_counter()
    settings = load_settings()
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    jobs: list[dict] = []
    run_metadata = {
        "provider": settings["provider"],
        "model": settings["model"],
        "temperature": settings["temperature"],
    }
    buy_plan_diagnostics = plan_tools_with_diagnostics(settings["buy_rules"])
    sell_plan_diagnostics = plan_tools_with_diagnostics(settings["sell_rules"])
    buy_plan = buy_plan_diagnostics.tools
    sell_plan = sell_plan_diagnostics.tools

    print("\n-- BUY evaluation (watchlist) ----------------------------------")
    print(f"  plan: {_format_plan(buy_plan)}")
    if buy_plan_diagnostics.fallback_only:
        print("  WARNING: BUY rules matched no specific data tools; using quote fallback only. TODO: surface this warning in the dashboard.")
    for ticker in _load_watchlist():
        jobs.append({
            "index": len(jobs),
            "ticker": ticker,
            "rules": settings["buy_rules"],
            "model": settings["model"],
            "evaluation_type": "BUY_EVAL",
            "tool_plan": buy_plan,
            "metadata": {
                "signal_type": "BUY_EVAL",
                "run_date": run_date,
                "rules_applied": settings["buy_rules"],
                **run_metadata,
            },
        })

    print("\n-- SELL evaluation (portfolio) ---------------------------------")
    print(f"  plan: {_format_plan(sell_plan)}")
    if sell_plan_diagnostics.fallback_only:
        print("  WARNING: SELL rules matched no specific data tools; using quote fallback only. TODO: surface this warning in the dashboard.")
    for holding in _load_portfolio():
        ticker = holding["ticker"]
        jobs.append({
            "index": len(jobs),
            "ticker": ticker,
            "rules": settings["sell_rules"],
            "model": settings["model"],
            "evaluation_type": "SELL_EVAL",
            "tool_plan": sell_plan,
            "context_data": {
                "holding": {
                    "entry_price": holding["entry_price"],
                    "qty": holding["qty"],
                    "entry_date": holding["entry_date"],
                }
            },
            "metadata": {
                "signal_type": "SELL_EVAL",
                "run_date": run_date,
                "entry_price": holding["entry_price"],
                "rules_applied": settings["sell_rules"],
                **run_metadata,
            },
        })

    fetched_jobs, timings = _fetch_jobs(jobs)
    buy_fetched = [item for item in fetched_jobs if item["signal_type"] == "BUY_EVAL"]
    sell_fetched = [item for item in fetched_jobs if item["signal_type"] == "SELL_EVAL"]
    print("\n-- LLM evaluation ------------------------------------------------")
    buy_signals, buy_eval_elapsed = _evaluate_group(
        buy_fetched,
        rules=settings["buy_rules"],
        model=settings["model"],
        evaluation_type="BUY_EVAL",
    )
    print(f"  BUY_EVAL batch:  {len(buy_signals)} signals ({buy_eval_elapsed:.1f}s)", flush=True)
    sell_signals, sell_eval_elapsed = _evaluate_group(
        sell_fetched,
        rules=settings["sell_rules"],
        model=settings["model"],
        evaluation_type="SELL_EVAL",
    )
    print(f"  SELL_EVAL batch: {len(sell_signals)} signals ({sell_eval_elapsed:.1f}s)", flush=True)
    all_signals = buy_signals + sell_signals

    total_elapsed = perf_counter() - started
    for signal in all_signals:
        signal["run_elapsed_seconds"] = round(total_elapsed, 3)
    write_signals(all_signals)
    summary = {
        "run_date": run_date,
        "provider": settings["provider"],
        "model": settings["model"],
        "signal_count": len(all_signals),
        "max_workers": min(MAX_WORKERS, len(jobs)) if jobs else 0,
        "elapsed_seconds": round(total_elapsed, 3),
        "fmp_requests_this_run": get_fmp_run_request_count(),
        "fmp_requests_today": get_fmp_request_count(),
        "buy_plan": _format_plan(buy_plan),
        "sell_plan": _format_plan(sell_plan),
        "batch_timings": {
            "BUY_EVAL": round(buy_eval_elapsed, 3),
            "SELL_EVAL": round(sell_eval_elapsed, 3),
        },
        "ticker_timings": timings,
    }
    _write_run_summary(summary)
    print(f"\nOK {len(all_signals)} signals saved  -  run: {run_date}")
    print(f"FMP requests this run: {get_fmp_run_request_count()}")
    print(f"FMP requests today:    {get_fmp_request_count()}")
    print("  Launch dashboard:  streamlit run src/dashboard/app.py\n")
    return summary


def main() -> None:
    run_analysis()


if __name__ == "__main__":
    main()
