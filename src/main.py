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
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from paths import (
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

from settings import load_settings
from agent import run_agent
from agent.tools import get_fmp_request_count, get_fmp_run_request_count, get_quote
from database import write_signals

_USER_DATA_DIR = user_data_dir()
_DATA_DIR = _USER_DATA_DIR


def _ensure_data_files() -> None:
    if os.path.abspath(_DATA_DIR) == os.path.abspath(_USER_DATA_DIR):
        seed_user_csv_defaults()


def _load_watchlist() -> list[str]:
    _ensure_data_files()
    path = os.path.join(_DATA_DIR, "watchlist.csv")
    df = pd.read_csv(path)
    return df["ticker"].str.upper().str.strip().tolist()


def _load_portfolio() -> list[dict]:
    _ensure_data_files()
    path = os.path.join(_DATA_DIR, "portfolio.csv")
    df = pd.read_csv(path)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df.to_dict(orient="records")


def _ensure_name(signal: dict, ticker: str) -> None:
    if signal["data_fetched"].get("name"):
        return
    quote = get_quote(ticker)
    signal["data_fetched"]["name"] = quote.get("name", ticker)


def run_analysis() -> dict:
    settings = load_settings()
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_signals: list[dict] = []
    run_metadata = {
        "provider": settings["provider"],
        "model": settings["model"],
    }

    # ------------------------------------------------------------------ BUY --
    print("\n-- BUY evaluation (watchlist) ----------------------------------")
    for ticker in _load_watchlist():
        print(f"  {ticker:<8}", end=" ", flush=True)
        signal = run_agent(ticker=ticker, rules=settings["buy_rules"], model=settings["model"])
        _ensure_name(signal, ticker)
        signal.update({"signal_type": "BUY_EVAL", "run_date": run_date, **run_metadata})
        all_signals.append(signal)
        print(f"→ {signal['signal']:4}  {signal.get('rationale', '')[:80]}")

    # ----------------------------------------------------------------- SELL --
    print("\n-- SELL evaluation (portfolio) ---------------------------------")
    for holding in _load_portfolio():
        ticker = holding["ticker"]
        # Inject entry context so the agent can evaluate % gain/loss rules
        rules_with_context = (
            f"My entry price for {ticker} is ${holding['entry_price']}. "
            f"I bought {holding['qty']} shares on {holding['entry_date']}.\n\n"
            + settings["sell_rules"]
        )
        print(f"  {ticker:<8}", end=" ", flush=True)
        signal = run_agent(ticker=ticker, rules=rules_with_context, model=settings["model"])
        _ensure_name(signal, ticker)
        signal.update({
            "signal_type": "SELL_EVAL",
            "run_date": run_date,
            "entry_price": holding["entry_price"],
            **run_metadata,
        })
        all_signals.append(signal)
        print(f"→ {signal['signal']:4}  {signal.get('rationale', '')[:80]}")

    # -------------------------------------------------------- write to DB ---
    write_signals(all_signals)
    print(f"\n✓ {len(all_signals)} signals saved  ·  run: {run_date}")
    print(f"FMP requests this run: {get_fmp_run_request_count()}")
    print(f"FMP requests today:    {get_fmp_request_count()}")
    print("  Launch dashboard:  streamlit run src/dashboard/app.py\n")
    return {
        "run_date": run_date,
        "signal_count": len(all_signals),
        "fmp_requests_this_run": get_fmp_run_request_count(),
        "fmp_requests_today": get_fmp_request_count(),
    }


def main() -> None:
    run_analysis()


if __name__ == "__main__":
    main()
