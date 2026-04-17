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
]
