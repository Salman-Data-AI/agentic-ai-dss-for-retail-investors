"""
Market data wrapper functions using Financial Modeling Prep (FMP).

The public function signatures and return shapes are part of the agent contract.
Do not change them without updating downstream consumers.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date

import requests
from dotenv import load_dotenv

from paths import executable_env_path, fmp_usage_path, user_env_path

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_FMP_BASE_URL = "https://financialmodelingprep.com/stable"
_USAGE_PATH = fmp_usage_path()
_FMP_RUN_REQUEST_COUNT = 0
_FMP_RUN_CACHE = {}
_FMP_LOCK = threading.Lock()
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

    with _FMP_LOCK:
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


def _cache_key(path: str, params: dict) -> tuple:
    symbol = str(params.get("symbol", "")).upper().strip()
    normalized_params = tuple(sorted((key, str(value)) for key, value in params.items() if key != "apikey"))
    return (path, symbol, normalized_params)


def _fmp_get(path: str, params: dict) -> list | dict:
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        raise RuntimeError("FMP_API_KEY is not set")

    key = _cache_key(path, params)
    with _FMP_LOCK:
        cached = _FMP_RUN_CACHE.get(key)
    if cached is not None:
        return cached

    query = {**params, "apikey": api_key}
    _increment_fmp_request_count()
    try:
        response = _HTTP.get(f"{_FMP_BASE_URL}{path}", params=query, timeout=20)
    except requests.RequestException as e:
        raise RuntimeError(f"FMP request failed: {e.__class__.__name__}") from e

    if response.status_code in (401, 402, 403):
        raise RuntimeError(f"FMP auth, permission, or plan error ({response.status_code}): {response.text[:200]}")
    if response.status_code == 404:
        raise RuntimeError(f"FMP not found error (404): bad endpoint path or ticker; {response.text[:200]}")
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
    with _FMP_LOCK:
        _FMP_RUN_CACHE[key] = payload
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


def _round_or_none(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(value, 2)


def _as_of_date(value) -> str:
    if not value:
        return ""
    return str(value).split()[0]


def _clean_symbol(ticker: str) -> str:
    symbol = ticker.upper().strip()
    if not symbol:
        raise RuntimeError("Ticker is blank")
    return symbol


def _select(row: dict, fields: dict[str, str]) -> dict:
    return {return_key: row.get(fmp_key) for fmp_key, return_key in fields.items()}


def _bundle_row(ticker: str, path: str, params: dict, fields: dict[str, str]) -> dict:
    symbol = _clean_symbol(ticker)
    row = _first_row(_fmp_get(path, {"symbol": symbol, **params}))
    return {"ticker": ticker, **_select(row, fields)}


def _bundle_rows(ticker: str, path: str, params: dict, fields: dict[str, str], list_key: str) -> dict:
    symbol = _clean_symbol(ticker)
    payload = _fmp_get(path, {"symbol": symbol, **params})
    if not isinstance(payload, list):
        payload = [payload]
    rows = []
    for row in payload:
        if isinstance(row, dict):
            rows.append(_select(row, fields))
    if not rows:
        raise RuntimeError("FMP returned an invalid response shape")
    return {"ticker": ticker, list_key: rows}


def get_quote(ticker: str) -> dict:
    """Current price, day change %, 52-week high/low, volume, market cap, company name."""
    try:
        symbol = ticker.upper().strip()
        row = _first_row(_fmp_get("/quote", {"symbol": symbol}))
        return {
            "ticker": ticker,
            "name": row.get("name") or symbol,
            "price": row.get("price"),
            "change_pct": _round_or_none(row.get("changePercentage")),
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
        row = _first_row(
            _fmp_get(
                "/technical-indicators/rsi",
                {"symbol": symbol, "periodLength": period, "timeframe": "1day"},
            )
        )
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
        row = _first_row(
            _fmp_get(
                "/technical-indicators/sma",
                {"symbol": symbol, "periodLength": period, "timeframe": "1day"},
            )
        )
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
        payload = _fmp_get("/ratios-ttm", {"symbol": symbol})
        if isinstance(payload, list):
            if not payload:
                raise RuntimeError("FMP returned an empty response")
            row = payload[0]
        else:
            row = payload
        if not isinstance(row, dict):
            raise RuntimeError("FMP returned an invalid response shape")
        return {
            "ticker": ticker,
            "pe_ratio": _round_or_none(row.get("priceToEarningsRatioTTM")),
            "eps_ttm": _round_or_none(row.get("netIncomePerShareTTM")),
        }
    except Exception as e:
        return {"error": f"Key metrics fetch failed for {ticker}: {e}"}


def get_valuation_ratios(ticker: str) -> dict:
    """Valuation, leverage, liquidity, and margin ratios from ratios TTM."""
    try:
        return _bundle_row(
            ticker,
            "/ratios-ttm",
            {},
            {
                "priceToEarningsRatioTTM": "pe_ratio_ttm",
                "priceToBookRatioTTM": "price_to_book_ttm",
                "priceToSalesRatioTTM": "price_to_sales_ttm",
                "priceToEarningsGrowthRatioTTM": "peg_ratio_ttm",
                "debtToEquityRatioTTM": "debt_to_equity_ttm",
                "currentRatioTTM": "current_ratio_ttm",
                "quickRatioTTM": "quick_ratio_ttm",
                "interestCoverageRatioTTM": "interest_coverage_ttm",
                "grossProfitMarginTTM": "gross_profit_margin_ttm",
                "netProfitMarginTTM": "net_profit_margin_ttm",
                "operatingProfitMarginTTM": "operating_profit_margin_ttm",
            },
        )
    except Exception as e:
        return {"error": f"Valuation ratios fetch failed for {ticker}: {e}"}


def get_financial_health(ticker: str) -> dict:
    """Profitability, capital efficiency, and debt coverage from key metrics TTM."""
    try:
        return _bundle_row(
            ticker,
            "/key-metrics-ttm",
            {},
            {
                "returnOnEquityTTM": "return_on_equity_ttm",
                "returnOnAssetsTTM": "return_on_assets_ttm",
                "returnOnInvestedCapitalTTM": "return_on_invested_capital_ttm",
                "evToEBITDATTM": "ev_to_ebitda_ttm",
                "freeCashFlowYieldTTM": "free_cash_flow_yield_ttm",
                "earningsYieldTTM": "earnings_yield_ttm",
                "netDebtToEBITDATTM": "net_debt_to_ebitda_ttm",
                "grahamNumberTTM": "graham_number_ttm",
            },
        )
    except Exception as e:
        return {"error": f"Financial health fetch failed for {ticker}: {e}"}


def get_income_statement(ticker: str) -> dict:
    """Latest annual income statement metrics."""
    try:
        return _bundle_row(
            ticker,
            "/income-statement",
            {"period": "annual", "limit": 1},
            {
                "revenue": "revenue",
                "grossProfit": "gross_profit",
                "ebitda": "ebitda",
                "operatingIncome": "operating_income",
                "netIncome": "net_income",
                "eps": "eps",
                "epsDiluted": "eps_diluted",
                "fiscalYear": "fiscal_year",
            },
        )
    except Exception as e:
        return {"error": f"Income statement fetch failed for {ticker}: {e}"}


def get_balance_sheet(ticker: str) -> dict:
    """Latest annual balance sheet metrics."""
    try:
        return _bundle_row(
            ticker,
            "/balance-sheet-statement",
            {"period": "annual", "limit": 1},
            {
                "totalAssets": "total_assets",
                "totalCurrentAssets": "total_current_assets",
                "totalCurrentLiabilities": "total_current_liabilities",
                "longTermDebt": "long_term_debt",
                "shortTermDebt": "short_term_debt",
                "cashAndShortTermInvestments": "cash_and_short_term_investments",
                "inventory": "inventory",
            },
        )
    except Exception as e:
        return {"error": f"Balance sheet fetch failed for {ticker}: {e}"}


def get_cash_flow(ticker: str) -> dict:
    """Latest annual cash flow metrics."""
    try:
        return _bundle_row(
            ticker,
            "/cash-flow-statement",
            {"period": "annual", "limit": 1},
            {
                "netCashProvidedByOperatingActivities": "operating_cash_flow",
                "investmentsInPropertyPlantAndEquipment": "capital_expenditures",
                "netDividendsPaid": "net_dividends_paid",
                "commonStockRepurchased": "common_stock_repurchased",
                "netChangeInCash": "net_change_in_cash",
            },
        )
    except Exception as e:
        return {"error": f"Cash flow fetch failed for {ticker}: {e}"}


def get_performance(ticker: str) -> dict:
    """Trailing stock returns over common horizons."""
    try:
        return _bundle_row(
            ticker,
            "/stock-price-change",
            {},
            {
                "1D": "return_1d",
                "5D": "return_5d",
                "1M": "return_1m",
                "3M": "return_3m",
                "6M": "return_6m",
                "ytd": "return_ytd",
                "1Y": "return_1y",
                "3Y": "return_3y",
                "5Y": "return_5y",
            },
        )
    except Exception as e:
        return {"error": f"Performance fetch failed for {ticker}: {e}"}


def get_profile(ticker: str) -> dict:
    """Company profile, risk, market cap, volume, and listing classification."""
    try:
        return _bundle_row(
            ticker,
            "/profile",
            {},
            {
                "beta": "beta",
                "sector": "sector",
                "industry": "industry",
                "exchange": "exchange",
                "marketCap": "market_cap",
                "averageVolume": "average_volume",
                "isEtf": "is_etf",
                "isFund": "is_fund",
                "isAdr": "is_adr",
                "ipoDate": "ipo_date",
                "lastDividend": "last_dividend",
            },
        )
    except Exception as e:
        return {"error": f"Profile fetch failed for {ticker}: {e}"}


def get_technical_indicator(ticker: str, indicator: str, period: int = 14) -> dict:
    """Fetch the latest supported technical indicator value."""
    indicator_fields = {
        "ema": "ema",
        "adx": "adx",
        "williams": "williams",
        "standarddeviation": "standardDeviation",
    }
    try:
        normalized = indicator.lower().replace("_", "").replace("-", "").strip()
        if normalized not in indicator_fields:
            return {"error": f"Unsupported technical indicator: {indicator}"}
        symbol = _clean_symbol(ticker)
        row = _first_row(
            _fmp_get(
                f"/technical-indicators/{normalized}",
                {"symbol": symbol, "periodLength": period, "timeframe": "1day"},
            )
        )
        value = row.get(indicator_fields[normalized])
        if value is None:
            return {"error": f"{indicator} unavailable for {ticker}"}
        return {
            "ticker": ticker,
            "indicator": normalized,
            "value": round(value, 2),
            "period": period,
            "as_of": _as_of_date(row.get("date")),
        }
    except Exception as e:
        return {"error": f"Technical indicator fetch failed for {ticker}: {e}"}


def get_price_target(ticker: str) -> dict:
    """Analyst price target consensus range."""
    try:
        return _bundle_row(
            ticker,
            "/price-target-consensus",
            {},
            {
                "targetHigh": "target_high",
                "targetLow": "target_low",
                "targetConsensus": "target_consensus",
                "targetMedian": "target_median",
            },
        )
    except Exception as e:
        return {"error": f"Price target fetch failed for {ticker}: {e}"}


def get_analyst_rating(ticker: str) -> dict:
    """Analyst rating snapshot and component scores."""
    try:
        return _bundle_row(
            ticker,
            "/ratings-snapshot",
            {},
            {
                "rating": "rating",
                "overallScore": "overall_score",
                "discountedCashFlowScore": "discounted_cash_flow_score",
                "returnOnEquityScore": "return_on_equity_score",
                "returnOnAssetsScore": "return_on_assets_score",
                "debtToEquityScore": "debt_to_equity_score",
                "priceToEarningsScore": "price_to_earnings_score",
                "priceToBookScore": "price_to_book_score",
            },
        )
    except Exception as e:
        return {"error": f"Analyst rating fetch failed for {ticker}: {e}"}


def get_analyst_estimates(ticker: str) -> dict:
    """Latest annual analyst estimates."""
    try:
        return _bundle_row(
            ticker,
            "/analyst-estimates",
            {"period": "annual"},
            {
                "date": "date",
                "revenueAvg": "revenue_avg",
                "epsAvg": "eps_avg",
                "ebitdaAvg": "ebitda_avg",
                "numAnalystsEps": "num_analysts_eps",
            },
        )
    except Exception as e:
        return {"error": f"Analyst estimates fetch failed for {ticker}: {e}"}


def get_earnings(ticker: str) -> dict:
    """Past and upcoming earnings rows for one ticker."""
    try:
        return _bundle_rows(
            ticker,
            "/earnings",
            {},
            {
                "date": "date",
                "epsEstimated": "eps_estimated",
                "epsActual": "eps_actual",
                "revenueEstimated": "revenue_estimated",
                "revenueActual": "revenue_actual",
            },
            "earnings",
        )
    except Exception as e:
        return {"error": f"Earnings fetch failed for {ticker}: {e}"}
