"""
Core agent loop.
One call to run_agent() per stock ticker.
The agent fetches only what it needs, evaluates against rules, returns a signal.
"""

import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

from .tools import get_quote, get_rsi, get_sma, get_key_metrics
from .tool_schemas import TOOL_SCHEMAS

load_dotenv()

_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

_TOOL_DISPATCH = {
    "get_quote": get_quote,
    "get_rsi": get_rsi,
    "get_sma": get_sma,
    "get_key_metrics": get_key_metrics,
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
        model  : Anthropic model string from config.py

    Returns:
        dict with keys: ticker, signal, rationale, data_fetched
    """
    system = _SYSTEM_PROMPT.format(rules=rules)
    messages = [{"role": "user", "content": f"Evaluate stock: {ticker}"}]

    while True:
        response = _client.messages.create(
            model=model,
            max_tokens=1024,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Append assistant turn and execute every tool call
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    fn = _TOOL_DISPATCH.get(block.name)
                    result = fn(**block.input) if fn else {"error": f"Unknown tool: {block.name}"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})

        elif response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    text = block.text.strip()
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

        else:
            return _error(ticker, f"Unexpected stop reason: {response.stop_reason}")


def _error(ticker: str, msg: str) -> dict:
    return {
        "ticker": ticker,
        "signal": "ERROR",
        "rationale": msg,
        "data_fetched": {},
    }
