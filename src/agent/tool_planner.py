"""Rule-level tool planning for repeated ticker evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class PlannedTool:
    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PlannedToolsDiagnostics:
    tools: list[PlannedTool]
    fallback_only: bool


def plan_tools_for_rules(rules: str) -> list[PlannedTool]:
    """Return the fixed tool set needed to evaluate these rules for any ticker."""
    return plan_tools_with_diagnostics(rules).tools


def plan_tools_with_diagnostics(rules: str) -> PlannedToolsDiagnostics:
    """Return planned tools plus whether the default quote fallback was the only match."""
    text = _normalize(rules)
    planned: list[PlannedTool] = []

    def add(name: str, **args) -> None:
        if not any(tool.name == name and tool.args == args for tool in planned):
            planned.append(PlannedTool(name, args))

    if _mentions_any(text, "current price", "price", "52 week", "52-week", "week high", "week low", "volume", "market cap", "large cap"):
        add("get_quote")
    if _mentions_any(text, "rsi", "oversold", "overbought"):
        add("get_rsi", period=_period_near(text, "rsi", default=14))
    if _mentions_any(text, "sma", "simple moving average", "moving average"):
        add("get_sma", period=_period_near(text, "sma", default=50))
    if _mentions_any(text, "pe ", "pe ratio", "p/e", "price to earnings", "price-to-earnings", "eps"):
        add("get_key_metrics")
    if _mentions_any(
        text,
        "valuation",
        "p/b",
        "price to book",
        "price-to-book",
        "p/s",
        "price to sales",
        "price-to-sales",
        "peg",
        "debt to equity",
        "debt-to-equity",
        "current ratio",
        "quick ratio",
        "interest coverage",
        "gross margin",
        "operating margin",
        "net margin",
        "leverage",
        "liquidity",
    ):
        add("get_valuation_ratios")
    if _mentions_any(
        text,
        "roe",
        "return on equity",
        "roa",
        "return on assets",
        "roic",
        "return on invested capital",
        "ev/ebitda",
        "free cash flow yield",
        "earnings yield",
        "net debt",
        "graham",
        "financial health",
    ):
        add("get_financial_health")
    if _mentions_any(text, "revenue", "gross profit", "ebitda", "operating income", "net income", "income statement"):
        add("get_income_statement")
    if _mentions_any(text, "balance sheet", "assets", "liabilities", "long term debt", "long-term debt", "cash position", "inventory"):
        add("get_balance_sheet")
    if _mentions_any(text, "cash flow", "free cash flow", "capex", "capital expenditure", "dividend", "buyback", "cash burn"):
        add("get_cash_flow")
    if _mentions_any(text, "performance", "momentum", "relative strength", "return", "returns", "drawdown", "rebound", "underperformance"):
        add("get_performance")
    if _mentions_any(text, "profile", "beta", "sector", "industry", "exchange", "etf", "fund", "adr", "ipo", "average volume", "last dividend", "large cap"):
        add("get_profile")
    if "volume" in text and "average" in text:
        add("get_profile")
    if _mentions_any(text, "ema", "exponential moving average"):
        add("get_technical_indicator", indicator="ema", period=_period_near(text, "ema", default=14))
    if _mentions_any(text, "adx", "trend strength"):
        add("get_technical_indicator", indicator="adx", period=_period_near(text, "adx", default=14))
    if _mentions_any(text, "williams"):
        add("get_technical_indicator", indicator="williams", period=_period_near(text, "williams", default=14))
    if _mentions_any(text, "standard deviation", "volatility"):
        add("get_technical_indicator", indicator="standarddeviation", period=_period_near(text, "standard deviation", default=14))
    if _mentions_any(text, "price target", "target price", "consensus target", "median target", "analyst upside", "analyst downside"):
        add("get_price_target")
    if _mentions_any(text, "analyst rating", "rating", "scorecard", "quality score", "valuation score", "overall score", "analyst score"):
        add("get_analyst_rating")
    if _mentions_any(text, "analyst estimate", "analyst estimates", "forward estimate", "expected eps", "expected revenue"):
        add("get_analyst_estimates")
    if _mentions_any(text, "earnings date", "earnings surprise", "upcoming earnings", "eps beat", "eps miss"):
        add("get_earnings")

    if planned:
        return PlannedToolsDiagnostics(tools=planned, fallback_only=False)
    return PlannedToolsDiagnostics(tools=[PlannedTool("get_quote")], fallback_only=True)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("_", " ").replace("-", " ")).strip()


def _mentions_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _period_near(text: str, term: str, *, default: int) -> int:
    term = term.lower().replace("-", " ")
    patterns = (
        rf"(\d+)\s*(?:day|period)?\s+{re.escape(term)}",
        rf"{re.escape(term)}\s*\(?\s*(\d+)",
        rf"{re.escape(term)}.*?(\d+)\s*(?:day|period)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return default
