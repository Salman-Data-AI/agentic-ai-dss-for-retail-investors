"""Canonical metric registry shared by compile, validation, and runtime."""

from __future__ import annotations

from typing import Any


METRIC_REGISTRY: dict[str, dict[str, Any]] = {
    "price": {
        "label": "Current price",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.price",),
        "unit": "currency",
        "aliases": ("current price", "stock price", "market price"),
        "examples": ("current price above 100 -> price > 100",),
    },
    "change_pct": {
        "label": "Day change percent",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.change_pct",),
        "unit": "percent",
        "aliases": ("day change", "daily change", "price change today"),
        "examples": ("price dropped more than 3% today -> change_pct < -3",),
    },
    "week_52_high": {
        "label": "52-week high",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.week_52_high",),
        "unit": "currency",
        "aliases": ("52-week high", "year high"),
        "examples": ("price below 52-week high -> price_below_52_week_high_pct > 0",),
    },
    "week_52_low": {
        "label": "52-week low",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.week_52_low",),
        "unit": "currency",
        "aliases": ("52-week low", "year low"),
        "examples": ("price near 52-week low -> price_above_52_week_low_pct <= threshold",),
    },
    "volume": {
        "label": "Volume",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.volume",),
        "unit": "shares",
        "aliases": ("volume", "shares traded"),
        "examples": ("volume above 1000000 -> volume > 1000000",),
    },
    "volume_vs_average_pct": {
        "label": "Volume versus average volume",
        "kind": "derived",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote", "get_profile"),
        "requires_all_sources": True,
        "source_fields": ("get_quote.volume", "get_profile.average_volume"),
        "unit": "percent",
        "aliases": ("volume above average", "volume below average", "relative volume"),
        "examples": ("volume above average -> volume_vs_average_pct > 0",),
    },
    "market_cap": {
        "label": "Market cap",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote", "get_profile"),
        "source_fields": ("get_quote.market_cap", "get_profile.market_cap"),
        "unit": "currency",
        "aliases": ("market cap", "market capitalization"),
        "examples": ("market cap above 10 billion -> market_cap > 10000000000",),
    },
    "rsi": {
        "label": "RSI",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_rsi",),
        "source_fields": ("get_rsi.rsi",),
        "unit": "index",
        "aliases": ("rsi", "relative strength index", "overbought", "oversold"),
        "examples": ("RSI below 35 -> rsi < 35", "RSI above 70 -> rsi > 70"),
    },
    "sma": {
        "label": "Simple moving average",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_sma",),
        "source_fields": ("get_sma.sma",),
        "unit": "currency",
        "aliases": ("sma", "simple moving average", "moving average"),
        "examples": ("price above SMA -> price > sma",),
    },
    "pe_ratio": {
        "label": "PE ratio",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_key_metrics",),
        "source_fields": ("get_key_metrics.pe_ratio",),
        "unit": "ratio",
        "aliases": ("pe ratio", "p/e", "price to earnings", "price-to-earnings"),
        "examples": ("PE ratio below 20 -> pe_ratio < 20", "PE ratio above 39 -> pe_ratio > 39"),
    },
    "eps_ttm": {
        "label": "EPS TTM",
        "kind": "tool",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_key_metrics",),
        "source_fields": ("get_key_metrics.eps_ttm",),
        "unit": "currency",
        "aliases": ("eps", "earnings per share", "trailing eps", "positive eps"),
        "examples": ("EPS should be positive -> eps_ttm > 0",),
    },
    "price_above_52_week_low_pct": {
        "label": "Price above 52-week low",
        "kind": "derived",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.price", "get_quote.week_52_low"),
        "unit": "percent",
        "aliases": ("within above 52-week low", "near 52-week low", "above the 52-week low"),
        "examples": ("current price within 25% above the 52-week low -> price_above_52_week_low_pct <= 25",),
    },
    "price_below_52_week_high_pct": {
        "label": "Price below 52-week high",
        "kind": "derived",
        "evaluation_types": ("BUY_EVAL", "SELL_EVAL"),
        "produced_by": ("get_quote",),
        "source_fields": ("get_quote.price", "get_quote.week_52_high"),
        "unit": "percent",
        "aliases": ("within below 52-week high", "near 52-week high", "below the 52-week high"),
        "examples": ("current price within 5% of the 52-week high -> price_below_52_week_high_pct <= 5",),
    },
    "gain_loss_pct": {
        "label": "Gain/loss from entry price",
        "kind": "derived",
        "evaluation_types": ("SELL_EVAL",),
        "produced_by": ("get_quote", "holding"),
        "source_fields": ("get_quote.price", "holding.entry_price"),
        "unit": "percent",
        "aliases": ("return from entry", "price vs entry price", "take profit", "stop loss"),
        "examples": (
            "price more than 25% above my entry price -> gain_loss_pct > 25",
            "price more than 15% below my entry price -> gain_loss_pct < -15",
        ),
    },
}

_ADDITIONAL_TOOL_METRICS = {
    "pe_ratio_ttm",
    "price_to_book_ttm",
    "price_to_sales_ttm",
    "peg_ratio_ttm",
    "debt_to_equity_ttm",
    "current_ratio_ttm",
    "quick_ratio_ttm",
    "interest_coverage_ttm",
    "gross_profit_margin_ttm",
    "net_profit_margin_ttm",
    "operating_profit_margin_ttm",
    "return_on_equity_ttm",
    "return_on_assets_ttm",
    "return_on_invested_capital_ttm",
    "ev_to_ebitda_ttm",
    "free_cash_flow_yield_ttm",
    "earnings_yield_ttm",
    "net_debt_to_ebitda_ttm",
    "graham_number_ttm",
    "revenue",
    "gross_profit",
    "ebitda",
    "operating_income",
    "net_income",
    "eps",
    "eps_diluted",
    "total_assets",
    "total_current_assets",
    "total_current_liabilities",
    "long_term_debt",
    "short_term_debt",
    "cash_and_short_term_investments",
    "inventory",
    "operating_cash_flow",
    "capital_expenditures",
    "net_dividends_paid",
    "common_stock_repurchased",
    "net_change_in_cash",
    "return_1d",
    "return_5d",
    "return_1m",
    "return_3m",
    "return_6m",
    "return_ytd",
    "return_1y",
    "return_3y",
    "return_5y",
    "beta",
    "average_volume",
    "last_dividend",
    "ema",
    "adx",
    "williams",
    "standard_deviation",
    "target_high",
    "target_low",
    "target_consensus",
    "target_median",
    "overall_score",
    "discounted_cash_flow_score",
    "return_on_equity_score",
    "return_on_assets_score",
    "debt_to_equity_score",
    "price_to_earnings_score",
    "price_to_book_score",
    "revenue_avg",
    "eps_avg",
    "ebitda_avg",
    "num_analysts_eps",
}

SUPPORTED_METRIC_KEYS = frozenset(set(METRIC_REGISTRY) | _ADDITIONAL_TOOL_METRICS)
METRIC_ALIASES = {
    "eps": "eps_ttm",
}


def canonical_metric_key(metric_key: str) -> str:
    return METRIC_ALIASES.get(metric_key, metric_key)


def metric_prompt_menu() -> str:
    lines = []
    for key, metric in sorted(METRIC_REGISTRY.items()):
        examples = "; ".join(metric.get("examples", ()))
        aliases = ", ".join(metric.get("aliases", ()))
        lines.append(
            f"- {key}: {metric['label']}. Kind: {metric['kind']}. "
            f"Valid for: {', '.join(metric['evaluation_types'])}. "
            f"Produced by: {', '.join(metric['produced_by'])}. "
            f"Unit: {metric['unit']}. Aliases: {aliases}. Examples: {examples}"
        )
    extras = sorted(_ADDITIONAL_TOOL_METRICS - set(METRIC_ALIASES))
    lines.append("- Other supported raw tool metrics: " + ", ".join(extras))
    return "\n".join(lines)
