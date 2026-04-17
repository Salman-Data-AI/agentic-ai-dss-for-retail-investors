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
import yfinance as yf

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Allow running from project root or from src/
sys.path.insert(0, os.path.dirname(__file__))
sys.stdout.reconfigure(encoding="utf-8")

import config
from agent import run_agent
from database import write_signals

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_watchlist() -> list[str]:
    path = os.path.join(_DATA_DIR, "watchlist.csv")
    df = pd.read_csv(path)
    return df["ticker"].str.upper().str.strip().tolist()


def _load_portfolio() -> list[dict]:
    path = os.path.join(_DATA_DIR, "portfolio.csv")
    df = pd.read_csv(path)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df.to_dict(orient="records")


def main() -> None:
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_signals: list[dict] = []

    # ------------------------------------------------------------------ BUY --
    print("\n-- BUY evaluation (watchlist) ----------------------------------")
    for ticker in _load_watchlist():
        print(f"  {ticker:<8}", end=" ", flush=True)
        signal = run_agent(ticker=ticker, rules=config.BUY_RULES, model=config.MODEL)
        signal["data_fetched"]["name"] = yf.Ticker(ticker).info.get("longName") or ticker
        signal.update({"signal_type": "BUY_EVAL", "run_date": run_date})
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
            + config.SELL_RULES
        )
        print(f"  {ticker:<8}", end=" ", flush=True)
        signal = run_agent(ticker=ticker, rules=rules_with_context, model=config.MODEL)
        signal["data_fetched"]["name"] = yf.Ticker(ticker).info.get("longName") or ticker
        signal.update({
            "signal_type": "SELL_EVAL",
            "run_date": run_date,
            "entry_price": holding["entry_price"],
        })
        all_signals.append(signal)
        print(f"→ {signal['signal']:4}  {signal.get('rationale', '')[:80]}")

    # -------------------------------------------------------- write to DB ---
    write_signals(all_signals)
    print(f"\n✓ {len(all_signals)} signals saved  ·  run: {run_date}")
    print("  Launch dashboard:  streamlit run src/dashboard/app.py\n")


if __name__ == "__main__":
    main()
