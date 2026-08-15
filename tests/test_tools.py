from __future__ import annotations

import json
from datetime import date

import pytest
import requests

from agent import tools


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="response", json_error=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise self._json_error
        return self._payload


class FakeHTTP:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self.exc:
            raise self.exc
        return self.response


def set_http(monkeypatch, response=None, exc=None):
    fake_http = FakeHTTP(response=response, exc=exc)
    monkeypatch.setattr(tools, "_HTTP", fake_http)
    return fake_http


def assert_error(result):
    assert set(result) == {"error"}
    assert isinstance(result["error"], str)


def test_get_quote_happy_path_contract(monkeypatch, isolated_fmp_usage):
    payload = [{
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "price": 195.21,
        "changePercentage": 1.234,
        "yearHigh": 237.49,
        "yearLow": 164.08,
        "volume": 51234567,
        "marketCap": 2999000000000,
    }]
    set_http(monkeypatch, FakeResponse(payload=payload))

    result = tools.get_quote("aapl")

    assert set(result) == {
        "ticker", "name", "price", "change_pct", "week_52_high",
        "week_52_low", "volume", "market_cap",
    }
    assert result == {
        "ticker": "aapl",
        "name": "Apple Inc.",
        "price": 195.21,
        "change_pct": 1.23,
        "week_52_high": 237.49,
        "week_52_low": 164.08,
        "volume": 51234567,
        "market_cap": 2999000000000,
    }
    assert isinstance(result["ticker"], str)
    assert isinstance(result["name"], str)
    assert isinstance(result["price"], float)
    assert isinstance(result["change_pct"], float)
    assert isinstance(result["week_52_high"], float)
    assert isinstance(result["week_52_low"], float)
    assert isinstance(result["volume"], int)
    assert isinstance(result["market_cap"], int)


@pytest.mark.parametrize(
    ("func", "payload", "expected"),
    [
        (
            tools.get_rsi,
            [{"date": "2026-07-02 00:00:00", "rsi": 31.456}],
            {"ticker": "msft", "rsi": 31.46, "period": 14, "as_of": "2026-07-02"},
        ),
        (
            tools.get_sma,
            [{"date": "2026-07-02", "sma": 420.678}],
            {"ticker": "msft", "sma": 420.68, "period": 50, "as_of": "2026-07-02"},
        ),
    ],
)
def test_indicator_happy_path_contract_and_period_param(monkeypatch, isolated_fmp_usage, func, payload, expected):
    fake_http = set_http(monkeypatch, FakeResponse(payload=payload))

    result = func("msft")

    assert result == expected
    assert set(result) == set(expected)
    assert isinstance(result["ticker"], str)
    assert isinstance(result["period"], int)
    assert isinstance(result["as_of"], str)
    metric_key = "rsi" if "rsi" in result else "sma"
    assert isinstance(result[metric_key], float)
    assert fake_http.calls[0]["params"]["periodLength"] == expected["period"]
    assert fake_http.calls[0]["params"]["timeframe"] == "1day"


def test_indicator_custom_period_is_passed_through(monkeypatch, isolated_fmp_usage):
    fake_http = set_http(monkeypatch, FakeResponse(payload=[{"date": "2026-07-02", "rsi": 55.0}]))

    result = tools.get_rsi("nvda", period=21)

    assert result["period"] == 21
    assert fake_http.calls[0]["params"]["periodLength"] == 21


def test_get_key_metrics_happy_path_contract(monkeypatch, isolated_fmp_usage):
    set_http(monkeypatch, FakeResponse(payload=[{
        "priceToEarningsRatioTTM": 24.991,
        "netIncomePerShareTTM": 6.123,
    }]))

    result = tools.get_key_metrics("googl")

    assert set(result) == {"ticker", "pe_ratio", "eps_ttm"}
    assert result == {"ticker": "googl", "pe_ratio": 24.99, "eps_ttm": 6.12}
    assert isinstance(result["ticker"], str)
    assert isinstance(result["pe_ratio"], float)
    assert isinstance(result["eps_ttm"], float)


@pytest.mark.parametrize(
    "payload",
    [
        [{}],
        [{"priceToEarningsRatioTTM": None, "netIncomePerShareTTM": None}],
        [{"priceToEarningsRatioTTM": "18", "netIncomePerShareTTM": "4.2"}],
    ],
)
def test_get_key_metrics_preserves_missing_or_non_numeric_values_as_none(monkeypatch, isolated_fmp_usage, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    result = tools.get_key_metrics("googl")

    assert result == {"ticker": "googl", "pe_ratio": None, "eps_ttm": None}


@pytest.mark.parametrize(
    "payload",
    [
        [{"name": "Apple Inc.", "price": 195.21}],
        [{"name": "Apple Inc.", "price": 195.21, "changePercentage": None}],
        [{"name": "Apple Inc.", "price": 195.21, "changePercentage": "1.2"}],
    ],
)
def test_get_quote_preserves_missing_or_non_numeric_change_pct_as_none(monkeypatch, isolated_fmp_usage, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    result = tools.get_quote("aapl")

    assert result["change_pct"] is None


@pytest.mark.parametrize("status_code", [404, 401, 402, 403, 429])
@pytest.mark.parametrize("func", [tools.get_quote, tools.get_rsi, tools.get_sma, tools.get_key_metrics])
def test_tools_return_error_dict_for_http_failures(monkeypatch, isolated_fmp_usage, func, status_code):
    set_http(monkeypatch, FakeResponse(status_code=status_code, payload={"error": "bad"}, text="bad request"))

    assert_error(func("bad"))


@pytest.mark.parametrize("payload", [[], {}, [{"rsi": None}], [{"sma": None}], [None]])
def test_get_rsi_returns_error_for_empty_or_malformed_payload(monkeypatch, isolated_fmp_usage, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    assert_error(tools.get_rsi("bad"))


@pytest.mark.parametrize("payload", [[], {}, [{"rsi": None}], [{"sma": None}], [None]])
def test_get_sma_returns_error_for_empty_or_malformed_payload(monkeypatch, isolated_fmp_usage, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    assert_error(tools.get_sma("bad"))


@pytest.mark.parametrize("func", [tools.get_quote, tools.get_key_metrics])
@pytest.mark.parametrize("payload", [[], {}, [None]])
def test_tools_return_error_for_empty_or_malformed_payload(monkeypatch, isolated_fmp_usage, func, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    assert_error(func("bad"))


@pytest.mark.parametrize("func", [tools.get_quote, tools.get_rsi, tools.get_sma, tools.get_key_metrics])
def test_tools_return_error_for_invalid_json(monkeypatch, isolated_fmp_usage, func):
    set_http(monkeypatch, FakeResponse(json_error=ValueError("no json")))

    assert_error(func("bad"))


@pytest.mark.parametrize("func", [tools.get_quote, tools.get_rsi, tools.get_sma, tools.get_key_metrics])
def test_tools_return_error_for_network_exception(monkeypatch, isolated_fmp_usage, func):
    set_http(monkeypatch, exc=requests.RequestException("offline"))

    assert_error(func("bad"))


def test_fmp_request_counter_and_daily_tally(monkeypatch, isolated_fmp_usage):
    set_http(monkeypatch, FakeResponse(payload=[{"name": "Apple Inc.", "price": 1.0}]))

    assert tools.get_fmp_request_count() == 0
    assert tools.get_fmp_run_request_count() == 0

    tools.get_quote("AAPL")
    tools.get_quote("MSFT")

    today = date.today().isoformat()
    assert tools.get_fmp_request_count() == 2
    assert tools.get_fmp_run_request_count() == 2
    assert json.loads(isolated_fmp_usage.read_text(encoding="utf-8")) == {today: 2}

    monkeypatch.setattr(tools, "_today_key", lambda: "2099-01-01")
    tools.get_quote("GOOGL")

    usage = json.loads(isolated_fmp_usage.read_text(encoding="utf-8"))
    assert usage[today] == 2
    assert usage["2099-01-01"] == 1
    assert tools.get_fmp_request_count() == 1


@pytest.mark.parametrize(
    ("func", "path", "payload", "expected", "expected_params"),
    [
        (
            tools.get_valuation_ratios,
            "/ratios-ttm",
            [{
                "priceToEarningsRatioTTM": 25.1,
                "priceToBookRatioTTM": 8.2,
                "priceToSalesRatioTTM": 6.3,
                "priceToEarningsGrowthRatioTTM": 1.4,
                "debtToEquityRatioTTM": 1.1,
                "currentRatioTTM": 1.8,
                "quickRatioTTM": 1.2,
                "interestCoverageRatioTTM": 22.0,
                "grossProfitMarginTTM": 0.44,
                "netProfitMarginTTM": 0.21,
                "operatingProfitMarginTTM": 0.29,
            }],
            {"pe_ratio_ttm": 25.1, "peg_ratio_ttm": 1.4, "net_profit_margin_ttm": 0.21},
            {},
        ),
        (
            tools.get_financial_health,
            "/key-metrics-ttm",
            [{
                "returnOnEquityTTM": 0.31,
                "returnOnAssetsTTM": 0.18,
                "returnOnInvestedCapitalTTM": 0.24,
                "evToEBITDATTM": 19.2,
                "freeCashFlowYieldTTM": 0.03,
                "earningsYieldTTM": 0.04,
                "netDebtToEBITDATTM": 0.7,
                "grahamNumberTTM": 88.5,
            }],
            {"return_on_equity_ttm": 0.31, "ev_to_ebitda_ttm": 19.2, "graham_number_ttm": 88.5},
            {},
        ),
        (
            tools.get_income_statement,
            "/income-statement",
            [{
                "revenue": 1000,
                "grossProfit": 600,
                "ebitda": 300,
                "operatingIncome": 250,
                "netIncome": 200,
                "eps": 5.2,
                "epsDiluted": 5.0,
                "fiscalYear": "2025",
            }],
            {"revenue": 1000, "gross_profit": 600, "eps_diluted": 5.0, "fiscal_year": "2025"},
            {"period": "annual", "limit": 1},
        ),
        (
            tools.get_balance_sheet,
            "/balance-sheet-statement",
            [{
                "totalAssets": 5000,
                "totalCurrentAssets": 1800,
                "totalCurrentLiabilities": 900,
                "longTermDebt": 700,
                "shortTermDebt": 80,
                "cashAndShortTermInvestments": 650,
                "inventory": 120,
            }],
            {"total_assets": 5000, "long_term_debt": 700, "cash_and_short_term_investments": 650},
            {"period": "annual", "limit": 1},
        ),
        (
            tools.get_cash_flow,
            "/cash-flow-statement",
            [{
                "netCashProvidedByOperatingActivities": 400,
                "investmentsInPropertyPlantAndEquipment": -90,
                "netDividendsPaid": -40,
                "commonStockRepurchased": -75,
                "netChangeInCash": 20,
            }],
            {"operating_cash_flow": 400, "capital_expenditures": -90, "net_change_in_cash": 20},
            {"period": "annual", "limit": 1},
        ),
        (
            tools.get_performance,
            "/stock-price-change",
            [{"1D": 0.5, "5D": 1.1, "1M": -2.0, "3M": 6.0, "6M": 9.0, "ytd": 12.0, "1Y": 15.0, "3Y": 55.0, "5Y": 80.0}],
            {"return_1d": 0.5, "return_1m": -2.0, "return_ytd": 12.0, "return_5y": 80.0},
            {},
        ),
        (
            tools.get_profile,
            "/profile",
            [{
                "beta": 1.2,
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "exchange": "NASDAQ",
                "marketCap": 3000,
                "averageVolume": 500,
                "isEtf": False,
                "isFund": False,
                "isAdr": False,
                "ipoDate": "1980-12-12",
                "lastDividend": 0.25,
            }],
            {"beta": 1.2, "sector": "Technology", "market_cap": 3000, "is_etf": False},
            {},
        ),
        (
            tools.get_price_target,
            "/price-target-consensus",
            [{"targetHigh": 250, "targetLow": 160, "targetConsensus": 210, "targetMedian": 215}],
            {"target_high": 250, "target_low": 160, "target_consensus": 210, "target_median": 215},
            {},
        ),
        (
            tools.get_analyst_rating,
            "/ratings-snapshot",
            [{
                "rating": "B+",
                "overallScore": 4,
                "discountedCashFlowScore": 5,
                "returnOnEquityScore": 4,
                "returnOnAssetsScore": 3,
                "debtToEquityScore": 4,
                "priceToEarningsScore": 2,
                "priceToBookScore": 3,
            }],
            {"rating": "B+", "overall_score": 4, "debt_to_equity_score": 4},
            {},
        ),
        (
            tools.get_analyst_estimates,
            "/analyst-estimates",
            [{"date": "2026", "revenueAvg": 1200, "epsAvg": 6.1, "ebitdaAvg": 360, "numAnalystsEps": 22}],
            {"date": "2026", "revenue_avg": 1200, "eps_avg": 6.1, "num_analysts_eps": 22},
            {"period": "annual"},
        ),
        (
            tools.get_earnings,
            "/earnings",
            [{
                "date": "2026-08-01",
                "epsEstimated": 1.5,
                "epsActual": None,
                "revenueEstimated": 100,
                "revenueActual": None,
            }],
            {"earnings": [{"date": "2026-08-01", "eps_estimated": 1.5, "eps_actual": None, "revenue_estimated": 100, "revenue_actual": None}]},
            {},
        ),
    ],
)
def test_new_bundle_tools_happy_paths(monkeypatch, isolated_fmp_usage, func, path, payload, expected, expected_params):
    fake_http = set_http(monkeypatch, FakeResponse(payload=payload))

    result = func("aapl")

    assert result["ticker"] == "aapl"
    for key, value in expected.items():
        assert result[key] == value
    assert fake_http.calls[0]["url"].endswith(path)
    assert fake_http.calls[0]["params"]["symbol"] == "AAPL"
    for key, value in expected_params.items():
        assert fake_http.calls[0]["params"][key] == value
    assert tools.get_fmp_request_count() == 1
    assert tools.get_fmp_run_request_count() == 1


def test_get_technical_indicator_extracts_latest_row_and_period(monkeypatch, isolated_fmp_usage):
    fake_http = set_http(monkeypatch, FakeResponse(payload=[
        {"date": "2026-07-02 00:00:00", "ema": 198.456},
        {"date": "2026-07-01 00:00:00", "ema": 197.111},
    ]))

    result = tools.get_technical_indicator("msft", "ema", period=21)

    assert result == {
        "ticker": "msft",
        "indicator": "ema",
        "value": 198.46,
        "period": 21,
        "as_of": "2026-07-02",
    }
    assert fake_http.calls[0]["url"].endswith("/technical-indicators/ema")
    assert fake_http.calls[0]["params"]["periodLength"] == 21
    assert fake_http.calls[0]["params"]["timeframe"] == "1day"


def test_get_technical_indicator_standarddeviation_field(monkeypatch, isolated_fmp_usage):
    set_http(monkeypatch, FakeResponse(payload=[{
        "date": "2026-07-02",
        "standardDeviation": 3.456,
    }]))

    result = tools.get_technical_indicator("msft", "standarddeviation")

    assert result["value"] == 3.46
    assert result["indicator"] == "standarddeviation"


def test_get_technical_indicator_rejects_unverified_indicator(isolated_fmp_usage):
    result = tools.get_technical_indicator("msft", "wma")

    assert_error(result)
    assert "Unsupported" in result["error"]
    assert tools.get_fmp_request_count() == 0


@pytest.mark.parametrize("status_code", [402, 403, 404, 429])
@pytest.mark.parametrize(
    "func",
    [
        tools.get_valuation_ratios,
        tools.get_financial_health,
        tools.get_income_statement,
        tools.get_balance_sheet,
        tools.get_cash_flow,
        tools.get_performance,
        tools.get_profile,
        tools.get_price_target,
        tools.get_analyst_rating,
        tools.get_analyst_estimates,
        tools.get_earnings,
    ],
)
def test_new_bundle_tools_return_error_dict_for_http_failures(monkeypatch, isolated_fmp_usage, func, status_code):
    set_http(monkeypatch, FakeResponse(status_code=status_code, payload={"error": "bad"}, text="bad request"))

    assert_error(func("bad"))


@pytest.mark.parametrize("payload", [[], {}, [None]])
@pytest.mark.parametrize(
    "func",
    [
        tools.get_valuation_ratios,
        tools.get_financial_health,
        tools.get_income_statement,
        tools.get_balance_sheet,
        tools.get_cash_flow,
        tools.get_performance,
        tools.get_profile,
        tools.get_price_target,
        tools.get_analyst_rating,
        tools.get_analyst_estimates,
        tools.get_earnings,
    ],
)
def test_new_bundle_tools_return_error_for_empty_or_malformed_payload(monkeypatch, isolated_fmp_usage, func, payload):
    set_http(monkeypatch, FakeResponse(payload=payload))

    assert_error(func("bad"))


@pytest.mark.parametrize(
    "func",
    [
        tools.get_valuation_ratios,
        tools.get_financial_health,
        tools.get_income_statement,
        tools.get_balance_sheet,
        tools.get_cash_flow,
        tools.get_performance,
        tools.get_profile,
        tools.get_technical_indicator,
        tools.get_price_target,
        tools.get_analyst_rating,
        tools.get_analyst_estimates,
        tools.get_earnings,
    ],
)
def test_new_tools_return_error_for_network_exception(monkeypatch, isolated_fmp_usage, func):
    set_http(monkeypatch, exc=requests.RequestException("offline"))

    if func is tools.get_technical_indicator:
        result = func("bad", "ema")
    else:
        result = func("bad")
    assert_error(result)


def test_fmp_get_cache_prevents_duplicate_real_request(monkeypatch, isolated_fmp_usage):
    fake_http = set_http(monkeypatch, FakeResponse(payload=[{
        "priceToEarningsRatioTTM": 25.0,
        "priceToBookRatioTTM": 8.0,
    }]))

    first = tools.get_valuation_ratios("aapl")
    second = tools.get_valuation_ratios("AAPL")

    assert first["pe_ratio_ttm"] == 25.0
    assert second["pe_ratio_ttm"] == 25.0
    assert len(fake_http.calls) == 1
    assert tools.get_fmp_request_count() == 1
    assert tools.get_fmp_run_request_count() == 1
