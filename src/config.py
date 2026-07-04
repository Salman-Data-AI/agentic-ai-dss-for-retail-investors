# =============================================================================
# DSS CONFIGURATION
# This is the only file you need to edit to customise the system.
# No coding knowledge required — just edit the text between the triple quotes.
# =============================================================================




# --- LLM provider and model ---
# PROVIDER must be one of: "anthropic", "openai", "grok", "groq", "deepseek".
PROVIDER = "anthropic"

# Default to low-cost, tool-capable models for each provider.
MODEL = "claude-haiku-4-5-20251001"

PROVIDER_DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5.4-nano",
    "grok": "grok-4.3",
    "groq": "llama-3.1-8b-instant",
    "deepseek": "deepseek-v4-flash",
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
}


# --- BUY rules ---
# Write your entry criteria in plain English below.
# The agent will figure out which data to fetch and how to evaluate it.
# You can reference: RSI, price, 52-week high/low, PE ratio, EPS, SMA, volume.

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
