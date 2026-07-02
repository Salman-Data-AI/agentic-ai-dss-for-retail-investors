"""
Tool schemas for the Claude API.
Each entry tells Claude what a tool does and what arguments it accepts.
Keep descriptions precise — Claude uses them to decide when to call each tool.
"""

TOOL_SCHEMAS = [
    {
        "name": "get_quote",
        "description": (
            "Fetch current stock quote data: price, day change %, "
            "52-week high, 52-week low, volume, and market cap. "
            "Use this whenever the rules reference current price, price range, "
            "or proximity to 52-week high/low."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, e.g. AAPL",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_rsi",
        "description": (
            "Fetch the RSI (Relative Strength Index) for a stock. "
            "RSI below 30 indicates oversold conditions (potential buy signal). "
            "RSI above 70 indicates overbought conditions (potential sell signal). "
            "Use this whenever the rules mention RSI or overbought/oversold."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
                "period": {
                    "type": "integer",
                    "description": "RSI lookback period in days. Default is 14.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sma",
        "description": (
            "Fetch the Simple Moving Average (SMA) for a stock. "
            "Use this when the rules mention SMA, moving average, or trend direction. "
            "Common periods: 50-day (medium-term trend), 200-day (long-term trend)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                },
                "period": {
                    "type": "integer",
                    "description": "SMA period in days, e.g. 50 or 200. Default is 50.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_key_metrics",
        "description": (
            "Fetch fundamental key metrics: PE ratio and EPS (trailing twelve months). "
            "Use this whenever the rules reference valuation, PE ratio, or earnings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_valuation_ratios",
        "description": (
            "Fetch a valuation and ratio bundle: P/E, P/B, P/S, PEG, debt-to-equity, "
            "current ratio, quick ratio, interest coverage, gross margin, operating "
            "margin, and net margin. Use for rules about valuation multiples, leverage, "
            "liquidity, solvency, profitability margins, cheap/expensive stocks, or "
            "balance-sheet risk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_financial_health",
        "description": (
            "Fetch a financial-health bundle: ROE, ROA, return on invested capital, "
            "EV/EBITDA, free-cash-flow yield, earnings yield, net debt to EBITDA, "
            "and Graham number. Use for rules about quality, capital efficiency, "
            "cash-flow yield, debt coverage, financial strength, or value investing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_income_statement",
        "description": (
            "Fetch the latest annual income statement bundle: revenue, gross profit, "
            "EBITDA, operating income, net income, EPS, diluted EPS, and fiscal year. "
            "Use for rules about sales, earnings, profitability, income growth, EPS, "
            "or annual fundamentals."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_balance_sheet",
        "description": (
            "Fetch the latest annual balance sheet bundle: total assets, current assets, "
            "current liabilities, long-term debt, short-term debt, cash and short-term "
            "investments, and inventory. Use for rules about assets, liquidity, debt, "
            "cash position, working capital, or inventory."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_cash_flow",
        "description": (
            "Fetch the latest annual cash-flow bundle: operating cash flow, capital "
            "expenditures, dividends paid, share repurchases, and net change in cash. "
            "Use for rules about free cash flow, capex, dividends, buybacks, cash "
            "generation, or cash burn."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_performance",
        "description": (
            "Fetch trailing stock performance: 1D, 5D, 1M, 3M, 6M, year-to-date, "
            "1Y, 3Y, and 5Y returns. Use for momentum, relative strength, trend, "
            "recent gains/losses, drawdown/rebound, or underperformance rules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_profile",
        "description": (
            "Fetch company profile data: beta, sector, industry, exchange, market cap, "
            "average volume, ETF/fund/ADR flags, IPO date, and last dividend. Use for "
            "rules about risk/beta, sector or industry filters, liquidity, market size, "
            "dividends, IPO age, exchange, or excluding ETFs, funds, and ADRs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technical_indicator",
        "description": (
            "Fetch one latest technical indicator value for EMA, ADX, Williams %R, "
            "or standard deviation. Use for rules about exponential moving average, "
            "trend strength, directional movement, Williams overbought/oversold, "
            "volatility, or standard deviation. Do not use this for RSI or SMA; "
            "use the dedicated RSI and SMA tools instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "indicator": {
                    "type": "string",
                    "enum": ["ema", "adx", "williams", "standarddeviation"],
                    "description": "Indicator endpoint name.",
                },
                "period": {
                    "type": "integer",
                    "description": "Lookback period in trading days. Default is 14.",
                },
            },
            "required": ["ticker", "indicator"],
        },
    },
    {
        "name": "get_price_target",
        "description": (
            "Fetch analyst price target consensus: high target, low target, consensus "
            "target, and median target. Use for rules about analyst upside/downside, "
            "target price, consensus valuation, or Wall Street expectations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_rating",
        "description": (
            "Fetch analyst rating snapshot and component scores: overall rating, "
            "overall score, return-on-equity score, debt-to-equity score, "
            "price-to-earnings score, price-to-book score, and related quality/value "
            "scores. Use for analyst rating, scorecard, quality score, or valuation "
            "score rules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_estimates",
        "description": (
            "Fetch annual analyst estimates: average revenue estimate, average EPS "
            "estimate, average EBITDA estimate, and number of EPS analysts. Use for "
            "rules about forward estimates, expected revenue, expected EPS, expected "
            "EBITDA, analyst coverage, or future growth expectations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_earnings",
        "description": (
            "Fetch past and upcoming earnings rows: report date, estimated EPS, actual "
            "EPS, estimated revenue, and actual revenue. Use for rules about upcoming "
            "earnings, earnings surprises, EPS beats/misses, revenue beats/misses, or "
            "avoiding trades near earnings dates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "Stock ticker symbol"}},
            "required": ["ticker"],
        },
    },
]
