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
