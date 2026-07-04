"""
Core agent loop.
One call to run_agent() per stock ticker.
The agent fetches only what it needs, evaluates against rules, returns a signal.
"""

import json
from dotenv import load_dotenv
from paths import executable_env_path, user_env_path

import config
from settings import load_settings
from .tools import (
    get_analyst_estimates,
    get_analyst_rating,
    get_balance_sheet,
    get_cash_flow,
    get_earnings,
    get_financial_health,
    get_income_statement,
    get_key_metrics,
    get_performance,
    get_price_target,
    get_profile,
    get_quote,
    get_rsi,
    get_sma,
    get_technical_indicator,
    get_valuation_ratios,
)
from .llm import create_llm_client

load_dotenv()
load_dotenv(user_env_path(), override=False)
exe_env = executable_env_path()
if exe_env:
    load_dotenv(exe_env, override=False)

_TOOL_DISPATCH = {
    "get_quote": get_quote,
    "get_rsi": get_rsi,
    "get_sma": get_sma,
    "get_key_metrics": get_key_metrics,
    "get_valuation_ratios": get_valuation_ratios,
    "get_financial_health": get_financial_health,
    "get_income_statement": get_income_statement,
    "get_balance_sheet": get_balance_sheet,
    "get_cash_flow": get_cash_flow,
    "get_performance": get_performance,
    "get_profile": get_profile,
    "get_technical_indicator": get_technical_indicator,
    "get_price_target": get_price_target,
    "get_analyst_rating": get_analyst_rating,
    "get_analyst_estimates": get_analyst_estimates,
    "get_earnings": get_earnings,
}

_SYSTEM_PROMPT = """You are a rule-based investment decision support system for retail investors.

Your job is to evaluate a single stock against the user's stated rules and return a structured signal.

INSTRUCTIONS:
1. Read the user's rules carefully and identify every data point they reference.
2. Use the available tools to fetch ONLY those data points. Do not fetch data not required by the rules.
3. Evaluate each fetched value against the relevant rule.
4. Return your result as a JSON object with exactly these three fields:

{{
  "signal": "<BUY | SELL | HOLD>",
  "rationale": "<Explain what the key metric value means in market terms — why it is or isn't significant right now — and connect it to the signal. Three to four plain-English sentences. Do not just report pass/fail; explain what the number is telling the investor about the stock's current condition.>",
  "data_fetched": {{ "<metric_name>": <value>, ... }}
}}

Rules:
- BUY   : the stock meets the entry criteria
- SELL  : the stock meets the exit criteria
- HOLD  : the stock does not clearly meet entry or exit criteria

CRITICAL: Your entire response must be ONLY the JSON object. 
No preamble, no explanation, no markdown, no bullet points, no text before or after the JSON.
Start your response with {{ and end with }}. Nothing else.

USER RULES:
{rules}
"""


def run_agent(ticker: str, rules: str, model: str = "claude-sonnet-4-6") -> dict:
    """
    Run the agent for a single ticker.

    Args:
        ticker : stock symbol, e.g. "AAPL"
        rules  : plain-English rules string from config.py (BUY or SELL)
        model  : selected provider model string from config.py

    Returns:
        dict with keys: ticker, signal, rationale, data_fetched
    """
    system = _SYSTEM_PROMPT.format(rules=rules)
    settings = load_settings()
    provider = settings.get("provider") or getattr(config, "PROVIDER", "anthropic")
    if model == "claude-sonnet-4-6":
        model = settings.get("model") or model
    provider_settings = getattr(config, "PROVIDER_SETTINGS", {}).get(provider)
    if not provider_settings:
        return _error(
            ticker,
            f"Unsupported PROVIDER={provider!r}. Choose one of: anthropic, openai, grok, groq, deepseek.",
        )

    try:
        client = create_llm_client(
            provider=provider,
            model=model,
            system=system,
            user_content=f"Evaluate stock: {ticker}",
            provider_settings=provider_settings,
        )
    except RuntimeError as exc:
        return _error(ticker, str(exc))

    while True:
        response = client.next_step()

        if response.tool_calls is not None:
            tool_results = []
            for call in response.tool_calls:
                fn = _TOOL_DISPATCH.get(call.name)
                result = fn(**call.arguments) if fn else {"error": f"Unknown tool: {call.name}"}
                tool_results.append({"id": call.id, "result": result})
            client.append_tool_results(tool_results)
            continue

        if response.final_text is not None:
            text = response.final_text.strip()
            # Find the JSON object anywhere in the response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    result = json.loads(text[start:end])
                    result["ticker"] = ticker
                    return result
                except json.JSONDecodeError:
                    return _error(ticker, f"Could not parse agent response: {text[:300]}")
            return _error(ticker, "Agent returned no text content")

        return _error(ticker, response.error or "Agent returned no response")


def _error(ticker: str, msg: str) -> dict:
    return {
        "ticker": ticker,
        "signal": "ERROR",
        "rationale": msg,
        "data_fetched": {},
    }
