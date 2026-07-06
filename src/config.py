# =============================================================================
# DSS CONFIGURATION
# This is the only file you need to edit to customise the system.
# No coding knowledge required — just edit the text between the triple quotes.
# =============================================================================




# --- LLM provider and model ---
# PROVIDER must be one of: "anthropic", "openai", "grok", "groq", "deepseek", "gemini", "cerebras".
PROVIDER = "anthropic"

# Default to low-cost, tool-capable models for each provider.
MODEL = "claude-haiku-4-5-20251001"

# None uses the provider default and sends no temperature parameter. A float such
# as 0.0 requests reduced variation but does not guarantee reproducibility.
TEMPERATURE = None

PROVIDER_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5.4-nano",
    "grok": "grok-4.3",
    "groq": "llama-3.1-8b-instant",
    "deepseek": "deepseek-v4-flash",
    "gemini": "gemini-2.5-flash",   # model ID present on test account; generation UNTESTED (403 project-access)
    "cerebras": "gpt-oss-120b",     # VALIDATED via live tool-calling smoke test
}

PROVIDER_SETTINGS = {
    "anthropic": {
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": None,
    },
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": "https://api.openai.com/v1",
    },
    "grok": {
        "api_key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
    },
    "groq": {
        "api_key_env": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
    },
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url": "https://api.deepseek.com",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
    },
    "cerebras": {
        "api_key_env": "CEREBRAS_API_KEY",
        "base_url": "https://api.cerebras.ai/v1",
    },
}


# --- BUY rules ---
# Write your entry criteria in plain English below.
# The agent will figure out which data to fetch and how to evaluate it.
# You can reference recognized planner terms such as price, 52-week high/low,
# volume, RSI, SMA, PE ratio, EPS, valuation ratios, financial health,
# income statement, balance sheet, cash flow, performance/momentum, profile,
# beta, EMA, ADX, Williams, volatility, price targets, analyst ratings,
# analyst estimates, and earnings.

BUY_RULES = """
Consider buying a stock if ALL of the following are true:
- RSI (14-day) is below 35, suggesting the stock is oversold
- The current price is within 15% above the 52-week low
- PE ratio is below 25
"""


# --- SELL rules ---
# Write your exit criteria in plain English below.
# The agent automatically has access to your entry price from portfolio.csv.
# You can reference: RSI, current price vs entry price (% gain/loss),
#                    PE ratio, EPS, SMA, 52-week high/low.

SELL_RULES = """
Consider selling a stock if ANY of the following are true:
- RSI (14-day) is above 70, suggesting the stock is overbought
- The current price is more than 25% above my entry price (take profit)
- The current price is more than 15% below my entry price (stop loss)
- PE ratio has expanded above 40
"""
