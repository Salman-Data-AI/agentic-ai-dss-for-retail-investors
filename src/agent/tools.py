"""
Market data wrapper functions using Financial Modeling Prep (FMP).

The public function signatures and return shapes are part of the agent contract.
Do not change them without updating downstream consumers.
"""

from __future__ import annotations

import json
import os
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_FMP_BASE_URL = "https://financialmodelingprep.com/stable"
_USAGE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "fmp_usage.json")
)
_FMP_RUN_REQUEST_COUNT = 0
_HTTP = requests.Session()
_HTTP.trust_env = False


def _today_key() -> str:
    return date.today().isoformat()


def _read_usage() -> dict:
    try:
        with open(_USAGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_usage(data: dict) -> None:
    os.makedirs(os.path.dirname(_USAGE_PATH), exist_ok=True)
    with open(_USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _increment_fmp_request_count() -> None:
    global _FMP_RUN_REQUEST_COUNT

    _FMP_RUN_REQUEST_COUNT += 1
    today = _today_key()
    usage = _read_usage()
    usage[today] = int(usage.get(today, 0)) + 1
    _write_usage(usage)


def get_fmp_request_count() -> int:
    """Return the persisted FMP request count for today."""
    return int(_read_usage().get(_today_key(), 0))


def get_fmp_run_request_count() -> int:
    """Return the number of FMP requests made by this Python process."""
    return _FMP_RUN_REQUEST_COUNT


def get_fmp_usage_path() -> str:
    """Return the local JSON file used for the daily FMP request tally."""
    return _USAGE_PATH


def _fmp_get(path: str, params: dict) -> list | dict:
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise RuntimeError("FMP_API_KEY is not set")

    query = {**params, "apikey": api_key}
    _increment_fmp_request_count()
    try:
        response = _HTTP.get(f"{_FMP_BASE_URL}{path}", params=query, timeout=20)
    except requests.RequestException as e:
        raise RuntimeError(f"FMP request failed: {e.__class__.__name__}") from e

    if response.status_code in (401, 402, 403):
        raise RuntimeError(f"FMP auth or plan error ({response.status_code}): {response.text[:200]}")
    if response.status_code == 429:
        raise RuntimeError(f"FMP rate limit error (429): {response.text[:200]}")
    if response.status_code >= 400:
        raise RuntimeError(f"FMP HTTP error ({response.status_code}): {response.text[:200]}")

    try:
        payload = response.json()
    except ValueError as e:
        raise RuntimeError(f"FMP returned invalid JSON: {e}") from e

    if isinstance(payload, dict) and payload.get("Error Message"):
        raise RuntimeError(f"FMP error: {payload['Error Message']}")
    if payload in ({}, []):
        raise RuntimeError("FMP returned an empty response")
    return payload


def _first_row(payload: list | dict) -> dict:
    if isinstance(payload, list):
        if not payload:
            raise RuntimeError("FMP returned an empty response")
        row = payload[0]
    else:
        row = payload
    if not isinstance(row, dict) or not row:
        raise RuntimeError("FMP returned an invalid response shape")
    return row


def _round_or_zero(value) -> float:
    return round(value or 0, 2)


def _as_of_date(value) -> str:
    if not value:
        return ""
    return str(value).split()[0]


def get_quote(ticker: str) -> dict:
    """Current price, day change %, 52-week high/low, volume, market cap, company name."""
    try:
        symbol = ticker.upper().strip()
        row = _first_row(_fmp_get("/quote", {"symbol": symbol}))
        return {
            "ticker": ticker,
            "name": row.get("name") or symbol,
            "price": row.get("price"),
            "change_pct": round(row.get("changePercentage", 0), 2),
            "week_52_high": row.get("yearHigh"),
            "week_52_low": row.get("yearLow"),
            "volume": row.get("volume"),
            "market_cap": row.get("marketCap"),
        }
    except Exception as e:
        return {"error": f"Quote fetch failed for {ticker}: {e}"}


def get_rsi(ticker: str, period: int = 14) -> dict:
    """
    RSI fetched from FMP's server-side technical indicator endpoint.
    Below 30 = oversold, above 70 = overbought.
    """
    try:
        symbol = ticker.upper().strip()
        row = _first_row(_fmp_get(
            "/technical-indicators/rsi",
            {"symbol": symbol, "periodLength": period, "timeframe": "1day"},
        ))
        if row.get("rsi") is None:
            return {"error": f"RSI unavailable for {ticker}"}
        return {
            "ticker": ticker,
            "rsi": round(row.get("rsi"), 2),
            "period": period,
            "as_of": _as_of_date(row.get("date")),
        }
    except Exception as e:
        return {"error": f"RSI calculation failed for {ticker}: {e}"}


def get_sma(ticker: str, period: int = 50) -> dict:
    """
    Simple Moving Average fetched from FMP's server-side technical indicator endpoint.
    Common periods: 50-day (medium-term trend), 200-day (long-term trend).
    """
    try:
        symbol = ticker.upper().strip()
        row = _first_row(_fmp_get(
            "/technical-indicators/sma",
            {"symbol": symbol, "periodLength": period, "timeframe": "1day"},
        ))
        if row.get("sma") is None:
            return {"error": f"SMA unavailable for {ticker}"}
        return {
            "ticker": ticker,
            "sma": round(row.get("sma"), 2),
            "period": period,
            "as_of": _as_of_date(row.get("date")),
        }
    except Exception as e:
        return {"error": f"SMA calculation failed for {ticker}: {e}"}


def get_key_metrics(ticker: str) -> dict:
    """PE ratio and EPS (trailing twelve months) from FMP."""
    try:
        symbol = ticker.upper().strip()
        row = _first_row(_fmp_get("/ratios-ttm", {"symbol": symbol}))
        return {
            "ticker": ticker,
            "pe_ratio": _round_or_zero(row.get("priceToEarningsRatioTTM")),
            "eps_ttm": _round_or_zero(row.get("netIncomePerShareTTM")),
        }
    except Exception as e:
        return {"error": f"Key metrics fetch failed for {ticker}: {e}"}
