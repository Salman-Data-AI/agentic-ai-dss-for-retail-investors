# =============================================================================
# DSS CONFIGURATION
# This is the only file you need to edit to customise the system.
# No coding knowledge required — just edit the text between the triple quotes.
# =============================================================================




# --- Model ---
# "claude-sonnet-4-6" : faster, cost-efficient (recommended)
# "claude-opus-4-6"   : slower, more thorough reasoning
MODEL = "claude-sonnet-4-6"


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